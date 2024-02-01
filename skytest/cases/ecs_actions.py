from concurrent import futures
import re
import time

from easy2use.globals import cfg
from retry import retry

from skytest.common import exceptions
from skytest.common import log
from skytest.common import model
from skytest.common import utils
from skytest.common import libvirt_guest
from skytest.managers import base

CONF = cfg.CONF
LOG = log.getLogger()


class EcsActionTestBase(object):

    def __init__(self, ecs: model.ECS, manager: base.BaseManager) -> None:
        self.ecs = ecs
        self.manager = manager
        self._guest: libvirt_guest.LibvirtGuest = None

    def tear_up(self): pass
    def tear_down(self): pass
    def start(self): pass

    def run(self):
        self.tear_up()
        self.start()

    # def assert_vm_state_is_active(self):
    #     self.ecs = self.manager.get_ecs(self.ecs.id)
    #     if self.ecs.status != 'ACTIVE':
    #         raise exceptions.EcsTestFailed(vm=self.ecs.id,
    #                                       reason
    #                                       reason=f'vm state is {vm_state}')

    @retry(exceptions=exceptions.EcsIsNotCreated,
           tries=CONF.boot.timeout/5, delay=5)
    def wait_for_ecs_created(self):
        if not self.ecs:
            raise Exception(f'{self.__class__}.ecs is None')

        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status: {:10}, task state: {:10}, host: {}',
                  self.ecs.status, self.ecs.task_state, self.ecs.host,
                  ecs=self.ecs.id)
        if self.ecs.is_error():
            raise exceptions.VMIsError(vm=self.ecs.id)
        if self.ecs.is_building() or self.ecs.has_task():
            raise exceptions.EcsIsNotCreated(self.ecs.id)

    @retry(exceptions=exceptions.EcsIsNotDeleted,
           tries=30, delay=1, backoff=2, max_delay=10)
    def wait_for_ecs_deleted(self):
        if not self.ecs:
            raise Exception(f'{self.__class__}.ecs is None')
        try:
            self.ecs = self.manager.get_ecs(self.ecs.id)
            LOG.debug('status: {:10}, stask_state: {:10}',
                      self.ecs.status, self.ecs.task_state, ecs=self.ecs.id)
        except exceptions.ECSNotFound:
            return
        if self.ecs.is_error():
            raise exceptions.VMIsError(vm=self.ecs.id)
        raise exceptions.EcsIsNotDeleted(self.ecs.id)

    @retry(exceptions=exceptions.EcsHasTask,
           tries=30, delay=1, backoff=2, max_delay=10)
    def wait_for_ecs_task_finished(self):
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status={}, task state={}',
                  self.ecs.status, self.ecs.task_state, ecs=self.ecs.id)
        if self.ecs.has_task():
            raise exceptions.EcsHasTask(self.ecs.id)

    def wait_for_ecs_console_log(self, timeout=None, interval=5):
        def check_vm_console_log():
            output = self.manager.get_ecs_console_log(self.ecs)
            LOG.debug('console log: {}', output, ecs=self.ecs.id)
            for key in CONF.boot.console_log_error_keys:
                if key not in output:
                    continue
                LOG.error('found "{}" in conosole log', key, ecs=self.ecs.id)
                raise exceptions.BootFailed(vm=self.ecs.id)

            match_ok = sum(
                key in output for key in CONF.boot.console_log_ok_keys)
            return match_ok == len(CONF.boot.console_log_ok_keys)

        retry.retry_untile_true(check_vm_console_log,
                                interval=interval, timeout=timeout)

    @retry(exceptions=exceptions.VolumeIsNotAvailable,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_created(self, volume: model.Volume):
        LOG.info('waiting volume {} created', volume.id, ecs=self.ecs.id)
        volume = self.manager.get_volume(volume.id)
        LOG.debug('volume {} status: {}', volume.id, volume.status,
                  ecs=self.ecs.id)
        if volume.is_error():
            raise exceptions.VolumeIsError(volume.id)
        if volume.is_creating():
            raise exceptions.VolumeIsNotAvailable(volume.id)
        LOG.debug('volume {} created', volume.id, ecs=self.ecs.id)
        return volume

    @retry(exceptions=exceptions.VolumeIsNotDeleted,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_deleted(self, volume: model.Volume):
        try:
            self.manager.get_volume(volume)
            LOG.info('volume {} status: {}', volume.id, volume.status,
                     ecs=self.ecs.id)
        except exceptions.VolumeNotFound:
            LOG.info("deleted volume {} ", volume.id, ecs=self.ecs.id)
            return
        else:
            if volume.is_error():
                raise exceptions.VolumeIsError(volume.id)
            raise exceptions.VolumeIsNotDeleted(volume.id)

    @retry(exceptions=exceptions.VolumeIsNotAvailable,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_is_available(self, volume: model.Volume):
        vol = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', vol.id, vol.status,
                 ecs=self.ecs.id)
        if not vol.is_available():
            raise exceptions.VolumeIsNotAvailable(volume.id)
        return vol

    @retry(exceptions=exceptions.VolumeIsNotInuse,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_is_inuse(self, volume: model.Volume):
        vol = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', vol.id, vol.status, ecs=self.ecs.id)
        if not vol.is_inuse():
            raise exceptions.VolumeIsNotInuse(volume.id)
        return vol

    def get_libvirt_guest(self):
        ecs_host_ip = self.manager.get_host_ip(self.ecs.host)
        if not self._guest or self._guest.host != ecs_host_ip:
            self._guest = libvirt_guest.LibvirtGuest(self.ecs.id,
                                                     host=ecs_host_ip)
        return self._guest

    @retry(exceptions=exceptions.EcsDoseNotHaveIpAddress,
           tries=60, delay=1, backoff=2, max_delay=10)
    def guest_must_have_all_ipaddress(self):
        if not CONF.scenario_test.enable_varify_guest_ip_address:
            return
        ecs_ip_address = set(self.manager.get_ecs_ip_address(self.ecs))
        LOG.info("ecs has ip address: {}", ecs_ip_address, ecs=self.ecs.id)
        found = set(
            re.findall(r'inet ([0-9.]+)/', self.get_libvirt_guest().ip_a()))
        LOG.debug('found ip address: {}', found, ecs=self.ecs.id)
        if '127.0.0.1' in found:
            found.remove('127.0.0.1')
        if set(ecs_ip_address) != set(found):
            raise exceptions.EcsDoseNotHaveIpAddress(self.ecs.id,
                                                     ecs_ip_address - found)
        LOG.info('domain has all ip address {}', ecs_ip_address,
                 ecs=self.ecs.id)

    @retry(exceptions=exceptions.EcsDoseNotHaveBlock,
           tries=60, delay=1, backoff=2, max_delay=10)
    def guest_must_have_all_block(self):
        if not CONF.scenario_test.enable_varify_guest_block:
            return
        ecs_blocks = set(self.manager.get_ecs_blocks(self.ecs))
        LOG.info("ecs has blocks: {}", ecs_blocks, ecs=self.ecs.id)
        found = set(re.findall(r'NAME="([a-zA-Z/]+)"',
                               self.get_libvirt_guest().lsblk()))
        LOG.debug('found blocks: {}', found, ecs=self.ecs.id)
        if set(ecs_blocks) != set(found):
            raise exceptions.EcsDoseNotHaveBlock(self.ecs.id,
                                                 ecs_blocks - found)
        LOG.info('domain has all blocks {}', ecs_blocks, ecs=self.ecs.id)


class EcsCreateTest(EcsActionTestBase):

    def start(self):
        self.ecs = self.manager.create_ecs()
        LOG.info('boot success', ecs=self.ecs.id)
        try:
            self.wait_for_ecs_created()
        except Exception as e:
            LOG.exception(e)
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='create',
                reason=f'{e}')
        LOG.info('ecs status is {}', self.ecs.status, ecs=self.ecs.id)
        self.guest_must_have_all_ipaddress()

    def tear_down(self):
        self.manager.delete_ecs(self.ecs)
        self.wait_for_ecs_deleted()


class EcsStopTest(EcsActionTestBase):

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
                vm=self.ecs.id, action='stop',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('stop success', ecs=self.ecs.id)


class EcsStartTest(EcsActionTestBase):

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
                vm=self.ecs.id, action='start',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('start success', ecs=self.ecs.id)


class EcsRebootTest(EcsActionTestBase):

    def start(self):
        if not self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is not active')

        self.manager.reboot_ecs(self.ecs)
        LOG.info('rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='reboot',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('reboot success', ecs=self.ecs.id)


class EcsHardRebootTest(EcsActionTestBase):
    def start(self):
        self.manager.hard_reboot_ecs(self.ecs)
        LOG.info('hard rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        LOG.info('hard reboot success', ecs=self.ecs.id)


class EcsAttachInterfaceTest(EcsActionTestBase):

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


class EcsAttachInterfaceLoopTest(EcsActionTestBase):

    def start(self):
        for index in range(CONF.scenario_test.attach_interface_loop_times):
            attached_ports = []
            for j in range(CONF.scenario_test.attach_interface_nums_each_time):
                LOG.info('attaching interface {}-{}', index + 1, j + 1,
                         ecs=self.ecs.id)
                attached = self.ecs.interface_attach(
                    None, CONF.openstack.attach_net, None)
                attached_ports.append(attached.port_id)

            vifs = self.manager.get_vm_interfaces(self.ecs)
            LOG.debug('vm ip interfaces: {}', vifs, vm=self.ecs.id)
            for port_id in attached_ports:
                if port_id not in vifs:
                    raise exceptions.EcsTestFailed(
                        vm=self.ecs.id, action='attach_interface',
                        reason=f'port {port_id} not in vm interfaces {vifs}')

            for port_id in attached_ports:
                LOG.info('detaching interface {} {}',
                         index + 1, port_id, vm=self.ecs.id)
                self.ecs.interface_detach(port_id)
        LOG.info('test attach volume loop success', vm=self.ecs.id)


class EcsAttachVolumeTest(EcsActionTestBase):

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
                vm=self.ecs.id, action='attach_volume',
                reason=f'volume {volume.id} not in use')
        self.attached_volumes.append(volume)
        self.guest_must_have_all_block()
        LOG.info('attach volumes success', ecs=self.ecs.id)

    def tear_down(self):
        for i in range(self.attached_volumes):
            volume = self.attached_volumes[i]
            self.manager.detach_volume(self.ecs, volume.id)
            LOG.info('detaching volume {}', volume.id, ecs=self.ecs.id)
            self.wait_for_ecs_task_finished()
            self.attached_volumes[i] = self.wait_volume_is_available(volume)

        for volume in self.volumes:
            self.manager.delete_volume(volume)
            LOG.info('deleting volume {}', volume.id, ecs=self.ecs.id)
        for volume in self.volumes:
            self.wait_volume_deleted(volume)


class EcsAttachVolumeLoopTest(EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.created_volumes = []

    def create_volumes(self, size, name=None, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None):
        LOG.debug('try to create {} volume(s), name={}, image={}, snapshot={}',
                  num, name, image, snapshot, ecs=self.ecs.id)
        self.created_volumes = []
        if not name:
            name = utils.generate_name('vol')

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.manager.create_volume,
                                     size_gb=size, name=f'{name}-{index}',
                                     image=image, snapshot=snapshot,
                                     volume_type=volume_type)
                     for index in range(1, num + 1)]
            LOG.info('creating {} volume(s) ...', num, ecs=self.ecs.id)
            for task in futures.as_completed(tasks):
                vol = task.result()
                if not vol:
                    continue
                self.created_volumes.append(vol)

        for volume in self.created_volumes:
            self.wait_volume_created(volume)
        return self.created_volumes

    def start(self):
        self.create_volumes(
            10, num=CONF.scenario_test.attach_volume_nums_each_time)

        for (i, volume) in enumerate(self.created_volumes):
            LOG.info('attach volume {}', i + 1, ecs=self.ecs.id)
            self.manager.attach_volume(self.ecs, volume.id)
            self.wait_for_ecs_task_finished()
            self.created_volumes[i] = self.wait_volume_is_inuse(volume)
        self.guest_must_have_all_block()

        LOG.debug('sleep {} seconds before detach volume',
                  CONF.scenario_test.device_toggle_min_interval,
                  ecs=self.ecs.id)
        time.sleep(CONF.scenario_test.device_toggle_min_interval)

        for (i, volume) in enumerate(self.created_volumes):
            self.manager.detach_volume(self.ecs, volume.id)
            self.wait_for_ecs_task_finished()
            self.created_volumes[i] = self.wait_volume_is_available(volume)

        self.guest_must_have_all_block()

    def tear_down(self):
        for volume in self.created_volumes:
            self.manager.delete_volume(volume)
        super().tear_down()


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
}
