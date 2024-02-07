import time

from skytest.common import conf
from skytest.common import exceptions
from skytest.common import log
from . import base

CONF = conf.CONF
LOG = log.getLogger()


class EcsCreateTest(base.EcsActionTestBase):

    def start(self):
        self.ecs = self.manager.create_ecs()
        try:
            self.wait_for_ecs_created()
        except Exception as e:
            LOG.exception(e)
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='create',
                reason=f'{e}')
        LOG.info('ecs status is {}', self.ecs.status, ecs=self.ecs.id)
        if CONF.ecs_test.enable_varify_console_log:
            LOG.info('varify console log matched', ecs=self.ecs.id)
            self.ecs_must_have_ok_console_log()
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
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status is {}', self.ecs.status, ecs=self.ecs.id)
        if not self.ecs.is_stopped():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='stop',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('stop success', ecs=self.ecs.id)


class EcsStartTest(base.EcsActionTestBase):

    def start(self):
        if self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is already active')
        self.manager.start_ecs(self.ecs)
        LOG.info('starting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status is {}', self.ecs.status, ecs=self.ecs.id)
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='start',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('start success', ecs=self.ecs.id)


class EcsRebootTest(base.EcsActionTestBase):

    def start(self):
        if not self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is not active')

        self.manager.reboot_ecs(self.ecs)
        LOG.info('rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='reboot',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('reboot success', ecs=self.ecs.id)


class EcsHardRebootTest(base.EcsActionTestBase):
    def start(self):
        self.manager.hard_reboot_ecs(self.ecs)
        LOG.info('hard rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        LOG.info('hard reboot success', ecs=self.ecs.id)


class EcsAttachInterfaceTest(base.EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_vifs = []

    def start(self):
        LOG.info('attaching interface', ecs=self.ecs.id)
        vif = self.manager.attach_net(self.ecs, CONF.openstack.attach_net)
        self.ecs = self.manager.get_ecs(self.ecs.id)
        if self.ecs.is_error():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='attach_interface',
                reason=f'ecs is error after attach interface {vif}')
        self.attached_vifs.append(vif)

        vifs = self.manager.get_ecs_interfaces(self.ecs)
        LOG.debug('ecs interfaces: {}', vifs, ecs=self.ecs.id)
        for vif_id in self.attached_vifs:
            if vif_id not in vifs:
                raise exceptions.EcsTestFailed(
                    ecs=self.ecs.id, action='attach_interface',
                    reason=f'ecs does not have interface {vif}')
        self.guest_must_have_all_ipaddress()
        LOG.info('test attach interface success', ecs=self.ecs.id)

    def tear_down(self):
        for vif in reversed(self.attached_vifs):
            LOG.info('detaching interface {}', vif, ecs=self.ecs.id)
            self.manager.detach_interface(self.ecs, vif)


class EcsAttachInterfaceLoopTest(base.EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_ports = []

    def start(self):
        self.attached_ports = []
        for i in range(CONF.ecs_test.attach_interface_nums_each_time):
            LOG.info('attaching interface {}', i + 1, ecs=self.ecs.id)
            port_id = self.manager.attach_net(self.ecs,
                                              CONF.openstack.attach_net)
            self.attached_ports.append(port_id)
        self.guest_must_have_all_ipaddress()

        for port_id in self.attached_ports:
            LOG.info('detaching interface {}', port_id, ecs=self.ecs.id)
            self.manager.detach_interface(self.ecs, port_id)


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

        LOG.info('attaching volume', ecs=self.ecs.id)
        self.manager.attach_volume(self.ecs, volume.id)
        LOG.info('attaching volume {}', volume.id, ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        volume = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', volume.id, volume.status,
                 ecs=self.ecs.id)
        if not volume.is_inuse():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='attach_volume',
                reason=f'volume {volume.id} not in use')
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

    def start(self):
        self.create_volumes(
            10, num=CONF.ecs_test.attach_volume_nums_each_time)

        for (i, volume) in enumerate(self.created_volumes):
            LOG.info('attach volume {}', i + 1, ecs=self.ecs.id)
            self.manager.attach_volume(self.ecs, volume.id)
            self.wait_for_ecs_task_finished()
            self.created_volumes[i] = self.wait_volume_is_inuse(volume)
        self.guest_must_have_all_block()

        LOG.debug('sleep {} seconds before detach volume',
                  CONF.ecs_test.device_toggle_min_interval,
                  ecs=self.ecs.id)
        time.sleep(CONF.ecs_test.device_toggle_min_interval)
        for (i, volume) in enumerate(self.created_volumes):
            self.manager.detach_volume(self.ecs, volume.id)
            self.wait_for_ecs_task_finished()
            self.created_volumes[i] = self.wait_volume_is_available(volume)

        self.guest_must_have_all_block()

    def tear_down(self):
        for volume in self.created_volumes:
            self.manager.delete_volume(volume)
        super().tear_down()


class EcsLiveMigrateTest(base.EcsActionTestBase):

    def start(self):
        src_host = self.ecs.host
        LOG.info('source host is {}', src_host, ecs=self.ecs.id)
        self.manager.live_migrate_ecs(self.ecs)
        LOG.info('live migrating ...', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished(show_progress=True)
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='live_migrate',
                reason=f'ecs status is {self.ecs.status}')
        if self.ecs.host == src_host:
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='live_migrate',
                reason=f'ecs host is still {self.ecs.host}')
        LOG.info('host is {}', self.ecs.host, ecs=self.ecs.id)


class EcsMigrateTest(base.EcsActionTestBase):

    def start(self):
        src_host = self.ecs.host
        LOG.info('source host is {}', src_host, ecs=self.ecs.id)
        self.manager.migrate_ecs(self.ecs)
        LOG.info('migrating ...', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished(show_progress=True)
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='live_migrate',
                reason=f'ecs status is {self.ecs.status}')
        if self.ecs.host == src_host:
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='live_migrate',
                reason=f'ecs host is still {self.ecs.host}')
        LOG.info('host is {}', self.ecs.host, ecs=self.ecs.id)


class EcsRenameTest(base.EcsActionTestBase):

    def start(self):
        src_name = self.ecs.name
        new_name = f'{self.__class__.__name__}-newName'
        LOG.info('source name is {}', src_name, ecs=self.ecs.id)
        self.manager.rename_ecs(self.ecs, new_name)
        LOG.info('change ecs name to  {}', new_name, ecs=self.ecs.id)
        self.ecs = self.manager.get_ecs(self.ecs.id)
        if self.ecs.name != new_name:
            raise exceptions.EcsNameNotMatch(self.ecs.id, new_name)
        try:
            self.ecs_must_have_name(new_name)
        except exceptions.EcsNameNotMatch:
            raise exceptions.EcsTestFailed(
                ecs=self.ecs.id, action='rename',
                reason=f'ecs name is not {new_name}')


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


VM_TEST_SCENARIOS = {
    'create': EcsCreateTest,
    'stop': EcsStopTest,
    'start': EcsStartTest,
    'reboot': EcsRebootTest,
    'hard_reboot': EcsHardRebootTest,
    'attach_interface': EcsAttachInterfaceTest,
    'attach_interface_loop': EcsAttachInterfaceLoopTest,
    'attach_volume': EcsAttachVolumeTest,
    'attach_volume_loop': EcsAttachVolumeLoopTest,
    'extend_volume': EcsExtendVolumeTest,
    'live_migrate': EcsLiveMigrateTest,
    'migrate': EcsMigrateTest,
    'rename': EcsRenameTest
}
