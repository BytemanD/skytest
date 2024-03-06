import time
from concurrent import futures

from skytest.common import conf
from skytest.common import exceptions
from skytest.common import log
from skytest.common import model
from skytest.common import utils

from . import base

CONF = conf.CONF
LOG = log.getLogger()

FLAVRS = None
NETWORKS = None


def init():
    global FLAVRS, NETWORKS

    FLAVRS = utils.CircularQueue(CONF.openstack.flavors)
    NETWORKS = utils.CircularQueue(CONF.openstack.networks)
    if NETWORKS.is_empty():
        LOG.warning("networks is empty")


class EcsCreateTest(base.EcsActionTestBase):

    def start(self):
        net_ids = [NETWORKS.current()] if not NETWORKS.is_empty() else None
        self.ecs = self.manager.create_ecs(FLAVRS.current(), networks=net_ids)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_active()
        if CONF.ecs_test.enable_verify_console_log:
            LOG.info('varify console log matched', ecs=self.ecs.id)
            self.ecs_must_have_ok_console_log()
        self.wait_ecs_qga_connected()
        self.guest_must_have_all_ipaddress()
        self.guest_must_have_all_block()

    def tear_down(self):
        self.manager.delete_ecs(self.ecs)
        self.wait_for_ecs_deleted()


class EcsStopTest(base.EcsActionTestBase):

    def start(self):
        if self.ecs.is_stopped():
            raise exceptions.SkipActionException('ecs is already stopped')
        self.manager.stop_ecs(self.ecs)
        LOG.info('stopping', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_stopped()
        LOG.info('stop success', ecs=self.ecs.id)


class EcsStartTest(base.EcsActionTestBase):

    def start(self):
        if self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is already active')
        self.manager.start_ecs(self.ecs)
        LOG.info('starting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.ecs = self.manager.get_ecs(self.ecs)
        self.assert_ecs_is_active()
        LOG.info('start success', ecs=self.ecs.id)


class EcsRebootTest(base.EcsActionTestBase):

    def start(self):
        if not self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is not active')

        self.manager.reboot_ecs(self.ecs)
        LOG.info('rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_active()
        LOG.info('reboot success', ecs=self.ecs.id)


class EcsHardRebootTest(base.EcsActionTestBase):
    def start(self):
        self.manager.hard_reboot_ecs(self.ecs)
        LOG.info('hard rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_active()
        LOG.info('hard reboot success', ecs=self.ecs.id)


class EcsAttachInterfaceTest(base.EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tmp_port: model.Port = None

    def start(self):
        if NETWORKS.is_empty():
            raise exceptions.SkipActionException('networks is empty')
        LOG.info('attaching interface', ecs=self.ecs.id)
        network_id = next(NETWORKS)
        LOG.debug('create port with network: {}', network_id, ecs=self.ecs.id)
        self.tmp_port = self.manager.create_port(network_id)
        LOG.debug('created port {}', self.tmp_port.id, ecs=self.ecs.id)

        self.manager.attach_interface(self.ecs, self.tmp_port.id)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_not_error()

        vifs = self.manager.get_ecs_interfaces(self.ecs)
        LOG.debug('ecs interfaces: {}', vifs, ecs=self.ecs.id)
        self.assert_ecs_has_interfaces([self.tmp_port.id])
        self.guest_must_have_all_ipaddress()
        LOG.info('test attach interface success', ecs=self.ecs.id)

    def tear_down(self):
        super().tear_down()
        if not self.tmp_port:
            return
        self.tmp_port = self.manager.get_port(self.tmp_port.id)
        if not self.tmp_port.host:
            LOG.debug('delete port {}', self.tmp_port.id, ecs=self.ecs.id)
            self.manager.delete_port(self.tmp_port.id)


class EcsDetachInterfaceTest(base.EcsActionTestBase):

    def start(self):
        interfaces = self.manager.get_ecs_interfaces(self.ecs)
        if not interfaces:
            raise exceptions.SkipActionException('ecs interface is empty')
        for port_id in reversed(interfaces):
            LOG.info('detaching interface {}', port_id, ecs=self.ecs.id)
            self.manager.detach_interface(self.ecs, port_id)
            self.wait_for_ecs_task_finished()


class EcsAttachInterfaceLoopTest(base.EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_ports: list = []
        self.created_ports: list[model.Port] = []

    def _attach_interface(self, port: model.Port) -> str:
        LOG.info('attaching interface {}', port.id, ecs=self.ecs.id)
        port_id = self.manager.attach_interface(self.ecs, port.id)
        self.attached_ports.append(port)
        self.wait_for_ecs_task_finished()
        return port_id

    def _deattach_interface(self, port: model.Port) -> str:
        LOG.info('detaching interface {}', port.id, ecs=self.ecs.id)
        self.manager.detach_interface(self.ecs, port.id)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_not_error()
        self.assert_ecs_has_no_interfaces([port.id])
        return port.id

    def start(self):
        if NETWORKS.is_empty():
            raise exceptions.SkipActionException('networks is empty')

        LOG.debug("creating {} port(s)",
                  CONF.ecs_test.attach_interface_nums_each_time,
                  ecs=self.ecs.id)
        net_ids = [
            next(NETWORKS)
            for _ in range(CONF.ecs_test.attach_interface_nums_each_time)
        ]
        self.created_ports = self.create_ports(
            net_ids, workers=CONF.ecs_test.attach_interface_loop_workers)

        with futures.ThreadPoolExecutor(
            max_workers=CONF.ecs_test.attach_interface_loop_workers
        ) as pool:
            results = pool.map(self._attach_interface, self.created_ports)
            for result in results:
                LOG.info('attached interface {}', result, ecs=self.ecs.id)
        self.guest_must_have_all_ipaddress()

        with futures.ThreadPoolExecutor(
            max_workers=CONF.ecs_test.attach_interface_loop_workers
        ) as pool:
            results = pool.map(self._deattach_interface, self.attached_ports)
            for result in results:
                LOG.info('detached interface {}', result, ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()

        for port in self.created_ports:
            LOG.debug('delete port {}', port.id, ecs=self.ecs.id)
            self.manager.delete_port(port.id)


class EcsAttachVolumeTest(base.EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.volumes = []
        self.attached_volumes = []

    def start(self):
        volume = self.manager.create_volume()
        self.volumes.append(volume)
        LOG.info('creating volumes', ecs=self.ecs.id)
        self.wait_volume_created(volume)

        self.manager.attach_volume(self.ecs, volume.id)
        LOG.info('attaching volume {}', volume.id, ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        volume = self.wait_volume_is_inuse(volume)

        self.assert_volume_is_inuse(volume)
        self.attached_volumes.append(volume)
        self.guest_must_have_all_block()
        LOG.info('attach volumes success', ecs=self.ecs.id)

    def tear_down(self):
        for volume in self.attached_volumes:
            self.manager.detach_volume(self.ecs, volume.id)
            LOG.info('detaching volume {}', volume.id, ecs=self.ecs.id)
            self.wait_for_ecs_task_finished()
            self.wait_volume_is_available(volume)

        for volume in self.volumes:
            self.manager.delete_volume(volume)
            LOG.info('deleting volume {}', volume.id, ecs=self.ecs.id)
        for volume in self.volumes:
            self.wait_volume_deleted(volume)


class EcsAttachVolumeLoopTest(base.EcsActionTestBase):

    def _attach_volume(self, volume: model.Volume):
        self.manager.attach_volume(self.ecs, volume.id)
        self.wait_for_ecs_task_finished()
        self.wait_volume_is_inuse(volume)
        return volume.id

    def _detach_volume(self, volume: model.Volume):
        self.manager.detach_volume(self.ecs, volume.id)
        self.wait_for_ecs_task_finished()
        self.wait_volume_is_available(volume)
        return volume.id

    def start(self):
        self.created_volumes = self.create_volumes(
            10, num=CONF.ecs_test.attach_volume_nums_each_time)

        with futures.ThreadPoolExecutor(
             max_workers=CONF.ecs_test.attach_volume_loop_workers
        ) as pool:
            results = pool.map(self._attach_volume, self.created_volumes)
            for result in results:
                LOG.info("attached volume {}", result, ecs=self.ecs.id)
        self.guest_must_have_all_block()

        LOG.debug('sleep {} seconds before detach volume',
                  CONF.ecs_test.device_toggle_min_interval,
                  ecs=self.ecs.id)
        time.sleep(CONF.ecs_test.device_toggle_min_interval)

        with futures.ThreadPoolExecutor(
            max_workers=CONF.ecs_test.attach_volume_loop_workers
        ) as pool:
            results = pool.map(self._detach_volume, self.created_volumes)
            for result in results:
                LOG.info("detached volume {}", result, ecs=self.ecs.id)
        self.guest_must_have_all_block()

    def tear_down(self):
        with futures.ThreadPoolExecutor(
            max_workers=CONF.ecs_test.attach_volume_loop_workers
        ) as pool:
            results = pool.map(self.manager.delete_volume,
                               self.created_volumes)
            for result in results:
                LOG.debug("deleted volume {}", result, ecs=self.ecs.id)
        super().tear_down()


class EcsLiveMigrateTest(base.EcsActionTestBase):

    def start(self):
        src_host = self.ecs.host
        LOG.info('source host is {}', src_host, ecs=self.ecs.id)
        self.manager.live_migrate_ecs(self.ecs)
        LOG.info('live migrating ...', ecs=self.ecs.id)

        self.wait_for_ecs_task_finished(show_progress=True)
        self.assert_ecs_is_not_error()
        self.assert_ecs_host_is_not(src_host)
        self.wait_ecs_qga_connected()


class EcsMigrateTest(base.EcsActionTestBase):

    def start(self):
        src_host = self.ecs.host
        LOG.info('source host is {}', src_host, ecs=self.ecs.id)
        self.manager.migrate_ecs(self.ecs)
        LOG.info('migrating ...', ecs=self.ecs.id)

        self.wait_for_ecs_task_finished(show_progress=True)
        self.assert_ecs_is_not_error()
        self.assert_ecs_host_is_not(src_host)
        self.wait_ecs_qga_connected()


class EcsRenameTest(base.EcsActionTestBase):

    def start(self):
        self.manager.must_support_action(self.ecs, 'rename')
        if not CONF.ecs_test.enable_guest_qga_command:
            raise exceptions.SkipActionException(
                'enable_guest_qga_command is false')
        src_name = self.ecs.name
        new_name = f'{self.ecs.name}-newName'.replace(':', '')
        LOG.info('source name is "{}"', src_name, ecs=self.ecs.id)
        self.manager.rename_ecs(self.ecs, new_name)
        LOG.info('change ecs name to "{}"', new_name, ecs=self.ecs.id)

        self.refresh_ecs()
        self.assert_ecs_name_is(new_name)
        self.ecs_guest_must_have_hostname(new_name)


class EcsExtendVolumeTest(base.EcsActionTestBase):

    def start(self):
        volumes = self.manager.get_ecs_volumes(self.ecs)
        if volumes:
            device_name = volumes[-1].device
            volume = self.manager.get_volume(volumes[-1].volumeId)
        else:
            LOG.info('creating volume ...', ecs=self.ecs.id)
            self.create_volumes(10)
            LOG.info('attaching volume ...', ecs=self.ecs.id)
            self.manager.attach_volume(self.ecs, self.created_volumes[0].id)
            self.wait_for_ecs_task_finished()
            self.wait_volume_is_inuse(self.created_volumes[0])
            self.guest_must_have_all_block()

            volume = self.created_volumes[0]
            volumes = self.manager.get_ecs_volumes(self.ecs)
            device_name = volumes[-1].device

        new_size = volume.size + 10
        LOG.info('extending volume size to {}', new_size, ecs=self.ecs.id)
        self.manager.extend_volume(volume, new_size)
        self.wait_for_ecs_task_finished()
        self.guest_block_size_must_be(device_name, f'{new_size}G')


class EcsRebuildTest(base.EcsActionTestBase):

    def start(self):
        self.manager.rebuild_ecs(self.ecs)
        self.wait_for_ecs_task_finished()
        if self.ecs.is_error:
            raise exceptions.EcsIsError(self.ecs.id)
        self.wait_ecs_qga_connected()
        self.guest_must_have_all_ipaddress()
        self.guest_must_have_all_block()


class EcsResizeTest(base.EcsActionTestBase):

    def start(self):
        if FLAVRS.length() <= 1:
            raise exceptions.SkipActionException('the num of flavors <= 1')
        flavor_id = self.manager.get_flavor_id(next(FLAVRS))
        LOG.info('resize flavor to {}', flavor_id, ecs=self.ecs.id)
        self.manager.resize_ecs(self.ecs, flavor_id)

        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_active()
        ecs_flavor_id = self.get_ecs_flavor_id()
        LOG.info('ecs flavor id is {}', ecs_flavor_id, ecs=self.ecs.id)
        self.assert_ecs_flavor_is(flavor_id)

        self.guest_must_have_all_ipaddress()
        self.guest_must_have_all_block()


class EcsShelveTtest(base.EcsActionTestBase):

    def start(self):
        src_host = self.manager.get_host_ip(self.ecs.host)
        self.manager.shelve_ecs(self.ecs)
        self.wait_for_ecs_task_finished()

        self.assert_ecs_is_shelved()
        self.wait_ecs_guest_not_exists(host=src_host)

    def tear_down(self):
        self.manager.unshelve_ecs(self.ecs)
        self.wait_for_ecs_task_finished()
        LOG.info('host is {}', self.ecs.host, ecs=self.ecs.id)


class EcsUnshelveTtest(base.EcsActionTestBase):

    def start(self):
        self.manager.unshelve_ecs(self.ecs)
        self.wait_for_ecs_task_finished()
        self.assert_ecs_is_active()
        self.wait_ecs_guest_active()

    def tear_down(self):
        self.manager.shelve_ecs(self.ecs)
        self.wait_for_ecs_task_finished()


class EcsPauseTtest(base.EcsActionTestBase):

    def start(self):
        self.manager.pause_ecs(self.ecs)
        self.wait_for_ecs_task_finished()


class EcsPauseTest(base.EcsActionTestBase):

    def start(self):
        self.manager.pause_ecs(self.ecs)
        self.wait_for_ecs_task_finished()


class EcsUnpauseTest(base.EcsActionTestBase):

    def start(self):
        self.manager.unpause_ecs(self.ecs)
        self.wait_for_ecs_task_finished()


class EcsTogglePause(base.EcsActionTestBase):

    def start(self):
        self.refresh_ecs()
        self.start_with_paused = self.ecs.is_paused()
        self._toggle_pause()
        self._toggle_pause()

    def _toggle_pause(self):
        if self.ecs.is_active():
            self.manager.pause_ecs(self.ecs)
            self.wait_for_ecs_task_finished()
            assert self.ecs.is_paused(), 'ecs is not paused'
            LOG.info('ecs is paused', ecs=self.ecs.id)
        elif self.ecs.is_paused():
            self.manager.unpause_ecs(self.ecs)
            self.wait_for_ecs_task_finished()
            assert self.ecs.is_active(), 'ecs is not active'
            LOG.info('ecs is active', ecs=self.ecs.id)
        else:
            raise exceptions.SkipActionException(
                f'ecs status is {self.ecs.status}')


VM_TEST_SCENARIOS = {
    'create': EcsCreateTest,
    'stop': EcsStopTest, 'start': EcsStartTest, 'reboot': EcsRebootTest,
    'hard_reboot': EcsHardRebootTest,
    'attach_interface': EcsAttachInterfaceTest,
    'detach_interface': EcsDetachInterfaceTest,
    'attach_interface_loop': EcsAttachInterfaceLoopTest,
    'attach_volume': EcsAttachVolumeTest,
    'attach_volume_loop': EcsAttachVolumeLoopTest,
    'extend_volume': EcsExtendVolumeTest,
    'live_migrate': EcsLiveMigrateTest, 'migrate': EcsMigrateTest,
    'rename': EcsRenameTest,
    'rebuild': EcsRebuildTest, 'resize': EcsResizeTest,
    'shelve': EcsShelveTtest, 'unshelve': EcsUnshelveTtest,
    'pause': EcsPauseTest, 'unpause': EcsUnpauseTest,
    'toggle_pause': EcsTogglePause,
}
