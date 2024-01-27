from easy2use.globals import cfg
from easy2use.common import retry

from skytest.common import exceptions
from skytest.common import log
from skytest.managers import base
from skytest.common import model

CONF = cfg.CONF
LOG = log.getLogger()


class EcsActionTestBase(object):

    def __init__(self, ecs: model.ECS, manager: base.BaseManager) -> None:
        self.ecs = ecs
        self.manager = manager

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

    def wait_for_ecs_created(self, timeout=None, interval=5):
        if not self.ecs:
            raise Exception(f'{self.__class__}.ecs is None')

        def check_vm_status():
            self.ecs = self.manager.get_ecs(self.ecs)
            LOG.debug('status: {}, stask state: {} host: {}',
                      self.ecs.status, self.ecs.task_state, self.ecs.host,
                      ecs=self.ecs.id)
            if self.ecs.is_error():
                raise exceptions.VMIsError(vm=self.ecs.id)

            return self.ecs.is_active() and not self.ecs.has_task()

        retry.retry_untile_true(check_vm_status, interval=interval,
                                timeout=timeout)

    def delete_ecs_and_wait(self, timeout=None, interval=5):

        def check_ecs_status():
            try:
                self.ecs = self.manager.get_ecs(self.ecs.id)
                LOG.debug('status={}, stask_state={}', self.ecs.status,
                          self.ecs.task_state, ecs=self.ecs.id)
            except exceptions.ECSNotFound:
                return True
            else:
                if self.ecs.status == 'error':
                    raise exceptions.VMIsError(vm=self.ecs.id)

        self.manager.delete_ecs(self.ecs)
        LOG.info('deleting', ecs=self.ecs.id)
        retry.retry_untile_true(check_ecs_status,
                                interval=interval, timeout=timeout)
        LOG.info('deleted', ecs=self.ecs.id)

    def wait_for_ecs_task_finished(self, timeout=None, interval=5):

        def check_vm_status():
            self.ecs = self.manager.get_ecs(self.ecs)
            LOG.debug('status={}, stask state={}',
                      self.ecs.status, self.ecs.task_state,
                      ecs=self.ecs.id)
            return not self.ecs.has_task()

        retry.retry_untile_true(check_vm_status,
                                interval=interval, timeout=timeout)

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


class EcsCreateTest(EcsActionTestBase):

    def start(self):
        self.ecs = self.manager.create_ecs()
        LOG.info('creating', ecs=self.ecs.id)
        try:
            self.wait_for_ecs_created(timeout=CONF.boot.timeout)
        except Exception as e:
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='create',
                reason=f'{e}')
        LOG.success('create success', ecs=self.ecs.id)

    def tear_down(self):
        self.delete_ecs_and_wait(timeout=60 * 20)


class EcsStopTest(EcsActionTestBase):

    def start(self):
        if self.ecs.is_stopped():
            raise exceptions.SkipActionException('ecs is already stopped')
        self.manager.stop_ecs(self.ecs)
        LOG.info('== stopping', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status is {}', self.ecs.status, ecs=self.ecs.id)
        if not self.ecs.is_stopped():
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='stop',
                reason=f'vm state is {self.ecs.status}')
        LOG.success('== stop success', ecs=self.ecs.id)


class EcsStartTest(EcsActionTestBase):

    def start(self):
        if self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is already active')
        self.manager.start_ecs(self.ecs)
        LOG.info('== starting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status is {}', self.ecs.status, ecs=self.ecs.id)
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='start',
                reason=f'vm state is {self.ecs.status}')
        LOG.success('== start success', ecs=self.ecs.id)


class EcsRebootTest(EcsActionTestBase):

    def start(self):
        if not self.ecs.is_active():
            raise exceptions.SkipActionException('ecs is not active')

        self.manager.reboot_ecs(self.ecs)
        LOG.info('== rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished(timeout=60 * 10)
        if not self.ecs.is_active():
            raise exceptions.EcsTestFailed(
                vm=self.ecs.id, action='reboot',
                reason=f'vm state is {self.ecs.status}')
        LOG.info('== reboot success', ecs=self.ecs.id)


class EcsHardRebootTest(EcsActionTestBase):

    def start(self):
        self.manager.hard_reboot_ecs(self.ecs)
        LOG.info('== hard rebooting', ecs=self.ecs.id)
        self.wait_for_ecs_task_finished()
        LOG.info('== hard reboot success', ecs=self.ecs.id)


class EcsAttachInterfaceTest(EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_vifs = []

    def start(self):
        for j in range(CONF.scenario_test.attach_interface_nums_each_time):
            LOG.info('attaching interface {}/{}', j+1,
                     CONF.scenario_test.attach_interface_nums_each_time,
                     ecs=self.ecs.id)
            vif = self.manager.attach_net(self.ecs,
                                          CONF.openstack.attach_net)
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
                    reason=f'vif {vif} not in vm interfaces {vifs}')
        LOG.success('test attach volume success', vm=self.ecs.id)

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
        LOG.success('test attach volume loop success', vm=self.ecs.id)


class VMAttachVolumeTest(EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attached_volumes = []

    def start(self):
        LOG.info('== creating volumes', vm=self.ecs.id)
        volume_ids = self.manager.create_volumes(
            1, num=CONF.scenario_test.attach_volume_nums_each_time)
        LOG.info('test attach volume', vm=self.ecs.id)
        for volume_id in volume_ids:
            self.manager.attach_volume(self.ecs, volume_id)
            LOG.info('attaching volume {}', volume_id, vm=self.ecs.id)
            self.manager.wait_for_vm_task_finished(self.ecs)
            self.attached_volumes.append(volume_id)
        LOG.success('== test attach volume success', vm=self.ecs.id)


class VMAttachVolumeLoopTest(EcsActionTestBase):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.created_volumes = []

    def tear_up(self):
        super().tear_up()
        LOG.info('creating volumes', vm=self.ecs.id)
        self.created_volumes = self.manager.create_volumes(
            10, num=CONF.scenario_test.attach_volume_nums_each_time)

    def start(self):
        for i in range(CONF.scenario_test.attach_volume_loop_times):
            for (j, volume) in enumerate(self.created_volumes):
                LOG.info('test attach volume {}-{}', i+1, j+1, vm=self.ecs.id)
                self.manager.attach_volume(self.ecs, volume.id, wait=True)
                self.manager.wait_for_vm_task_finished(self.ecs)

            for volume in self.created_volumes:
                self.manager.detach_volume(self.ecs, volume.id, wait=True)
                self.manager.wait_for_vm_task_finished(self.ecs)

    def varify(self):
        # TODO
        # varify vm volume attachments
        self.assert_vm_state_is_active()
        LOG.success('test attach volume loop success', vm=self.ecs.id)

    def tear_down(self):
        LOG.info('clean up {} volumes', len(self.created_volumes),
                 vm=self.ecs.id)
        self.manager.delete_volumes(self.created_volumes)
        super().tear_down()


VM_TEST_SCENARIOS = {
    'create': EcsCreateTest,
    'stop': EcsStopTest,
    'start': EcsStartTest,
    'reboot': EcsRebootTest,
    'hard_reboot': EcsHardRebootTest,
    'attach_interface': EcsAttachInterfaceTest,
    'attach_interface_loop': EcsAttachInterfaceLoopTest,
    'attach_volume': VMAttachVolumeTest,
    'attach_volume_loop': VMAttachVolumeLoopTest,
}
