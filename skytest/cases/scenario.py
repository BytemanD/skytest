from concurrent import futures
import random

from easy2use.globals import cfg
from easy2use.common import colorstr

from skytest.common import exceptions
from skytest.common import utils
from skytest.common import log
from skytest.managers.openstack import manager

CONF = cfg.CONF
LOG = log.getLogger()


class ECScenarioTest(object):

    def __init__(self, vm, api: manager.OpenstackManager) -> None:
        self.api = api or get_manager()
        self.vm = vm

    def tear_up(self):
        pass

    def tear_down(self):
        pass

    def run(self):
        self.tear_up()
        try: 
            self.start()
            self.varify()
        finally:
            LOG.info('tear down')
            self.tear_down()

    def start(self):
        pass

    def varify(self):
        pass

    def assert_vm_state_is_active(self):
        vm_state = self.api.get_vm_state(self.vm, refresh=True)
        if vm_state.upper() != 'ACTIVE':
            raise exceptions.VMTestFailed(vm=self.vm.id,
                                          action='attach_interface',
                                          reason=f'vm state is {vm_state}')


class VMStopScenarioTest(ECScenarioTest):

    def start(self):
        self.vm.stop()
        LOG.info('stopping')
        self.api.wait_for_vm_task_finished(self.vm)

    def varify(self):
        vm_state = self.api.get_vm_state(self.vm, refresh=True)
        LOG.info('vm state is {}', vm_state)
        if vm_state.upper() != 'STOPPED':
            raise exceptions.VMTestFailed(vm=self.vm.id, action='stop',
                                            reason=f'vm state is {vm_state}')
        LOG.success('test stop success', vm=self.vm.id)


class VMRebootScenarioTest(ECScenarioTest):

    def start(self):
        self.vm.reboot()
        LOG.info('rebooting', vm=self.vm.id)
        self.api.wait_for_vm_task_finished(self.vm)

    def varify(self):
        self.assert_vm_state_is_active()
        LOG.info('rebooted', vm=self.vm.id)

        try:
            if CONF.boot.check_console_log:
                self.api._wait_for_console_log(self.vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.VMTestFailed(vm=self.vm.id, action='reboot',
                                          reason=e)
        LOG.success('tes rebooted success', vm=self.vm.id)
        return self.vm


class VMHardRebootScenarioTest(ECScenarioTest):

    def start(self):
        self.vm.reboot(reboot_type='HARD')
        LOG.info('hard rebooting', vm=self.vm.id)
        self.api.wait_for_vm_task_finished(self.vm)

    def varify(self):
        self.assert_vm_state_is_active()
        LOG.info('started', vm=self.vm.id)

        try:
            self.api._wait_for_vm(self.vm, timeout=60 * 10, interval=5)
            if CONF.boot.check_console_log:
                self.api._wait_for_console_log(self.vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.RebootFailed(vm=self.vm.id, reason=e)
        LOG.info('test rebooted success', vm=self.vm.id)
        return self.vm


class VMStartScenarioTest(ECScenarioTest):

    def start(self):
        self.vm.start()
        LOG.info('starting')
        self.api.wait_for_vm_task_finished(self.vm)

    def varify(self):
        self.assert_vm_state_is_active()


class VMAttachInterfaceTest(ECScenarioTest):

    def __init__(self, vm, api: manager.OpenstackManager) -> None:
        super().__init__(vm, api)
        self.attached_ports = []

    def start(self):
        for j in range(CONF.scenario_test.attach_interface_nums_each_time):
            LOG.info('attaching interface {}/{}', j+1,
                     CONF.scenario_test.attach_interface_nums_each_time,
                     vm=self.vm.id) 
            attached = self.vm.interface_attach(
                None, CONF.openstack.attach_net, None)
            self.attached_ports.append(attached.port_id)

    def varify(self):
        vifs = self.api.get_vm_interfaces(self.vm)
        LOG.debug('vm ip interfaces: {}', vifs, vm=self.vm.id)
        for port_id in self.attached_ports:
            if port_id not in vifs:
                raise exceptions.VMTestFailed(
                    vm=self.vm.id, action='attach_interface',
                    reason=f'port {port_id} not in vm interfaces {vifs}')

        self.assert_vm_state_is_active()
        LOG.success('test attach volume success', vm=self.vm.id)


class VMAttachInterfaceLoopTest(ECScenarioTest):

    def __init__(self, vm, api: manager.OpenstackManager) -> None:
        super().__init__(vm, api)

    def start(self):
        for index in range(CONF.scenario_test.attach_interface_loop_times):
            attached_ports = []
            for j in range(CONF.scenario_test.attach_interface_nums_each_time):
                LOG.info('attaching interface {}-{}', index + 1, j + 1) 
                attached = self.vm.interface_attach(None,
                                                    CONF.openstack.attach_net,
                                                    None)
                attached_ports.append(attached.port_id)

            vifs = self.api.get_vm_interfaces(self.vm)
            LOG.debug('vm ip interfaces: {}', vifs, vm=self.vm.id)
            for port_id in attached_ports:
                if port_id not in vifs:
                    raise exceptions.VMTestFailed(
                        vm=self.vm.id, action='attach_interface',
                        reason=f'port {port_id} not in vm interfaces {vifs}')

            for port_id in attached_ports:
                LOG.info('detaching interface {} {}',
                         index + 1, port_id, vm=self.vm.id) 
                self.vm.interface_detach(port_id)

    def varify(self):
        self.assert_vm_state_is_active()
        LOG.success('test attach volume loop success', vm=self.vm.id)


class VMAttachVolumeTest(ECScenarioTest):

    def __init__(self, vm, api: manager.OpenstackManager) -> None:
        super().__init__(vm, api)
        self.attached_volumes = []

    def start(self):
        LOG.info('creating volumes', vm=self.vm.id)
        volume_ids = self.api.create_volumes(
            1, num=CONF.scenario_test.attach_volume_nums_each_time)
        LOG.info('test attach volume', vm=self.vm.id)
        for volume_id in volume_ids:
            self.api.attach_volume(self.vm, volume_id)
            LOG.info('attaching volume {}', volume_id, vm=self.vm.id)
            self.api.wait_for_vm_task_finished(self.vm)
            self.attached_volumes.append(volume_id)

    def varify(self):
        # TODO
        # varify vm volume attachments
        self.assert_vm_state_is_active()
        LOG.success('test attach volume success', vm=self.vm.id)


class VMAttachVolumeLoopTest(ECScenarioTest):

    def __init__(self, vm, api: manager.OpenstackManager) -> None:
        super().__init__(vm, api)
        self.created_volumes = []

    def tear_up(self):
        super().tear_up()
        LOG.info('creating volumes', vm=self.vm.id)
        self.created_volumes = self.api.create_volumes(
            10, num=CONF.scenario_test.attach_volume_nums_each_time)

    def start(self):
        for i in range(CONF.scenario_test.attach_volume_loop_times):
            for (j, volume) in enumerate(self.created_volumes):
                LOG.info('test attach volume {}-{}', i+1, j+1, vm=self.vm.id)
                self.api.attach_volume(self.vm, volume.id, wait=True)
                self.api.wait_for_vm_task_finished(self.vm)

            for volume in self.created_volumes:
                self.api.detach_volume(self.vm, volume.id, wait=True)
                self.api.wait_for_vm_task_finished(self.vm)

    def varify(self):
        # TODO
        # varify vm volume attachments
        self.assert_vm_state_is_active()
        LOG.success('test attach volume loop success', vm=self.vm.id)

    def tear_down(self):
        LOG.info('clean up {} volumes', len(self.created_volumes),
                 vm=self.vm.id)
        self.api.delete_volumes(self.created_volumes)
        super().tear_down()


VM_TEST_SCENARIOS = {
    'stop': VMStopScenarioTest,
    'start': VMStartScenarioTest,
    'reboot': VMRebootScenarioTest,
    'attach_interface': VMAttachInterfaceTest,
    'attach_interface_loop': VMAttachInterfaceLoopTest,
    'attach_volume': VMAttachVolumeTest,
    'attach_volume_loop': VMAttachVolumeLoopTest,
}

def get_manager():
    if CONF.manager == 'openstack':
        return manager.OpenstackManager()
    raise exceptions.InvalidManager(CONF.manager)

class VMScenarioTest(object):

    def __init__(self, manager=None) -> None:
        self._manager = manager
        self.server = None

    @property
    def manager(self):
        if not self._manager:
            self._manager = get_manager()
        return self._manager

    @staticmethod
    def get_scenarios():
        if CONF.scenario_test.random_order:
            test_scenarios = random.sample(CONF.scenario_test.scenarios,
                                           len(CONF.scenario_test.scenarios))
        else:
            test_scenarios = CONF.scenario_test.scenarios
        return test_scenarios

    def _check_flavor(self):
        if not CONF.openstack.flavor:
            raise exceptions.InvalidConfig(reason='flavor is not set')
        try:
            self.manager.get_flavor(CONF.openstack.flavor)
        except Exception:
            raise exceptions.InvalidFlavor(
                reason=f'get flavor {CONF.openstack.flavor} failed')

    def _check_image(self):
        """Make sure configed actions are all exists"""
        if not CONF.openstack.image_id:
            raise exceptions.InvalidConfig(reason='image is not set')

        try:
            self.manager.get_image(CONF.openstack.image_id)
        except Exception:
            raise exceptions.InvalidImage(
                reason=f'get image {CONF.openstack.image_id} failed')

    def _check_services(self):
        az, host = None, None
        if CONF.openstack.boot_az:
            if ':' in CONF.openstack.boot_az:
                az, host = CONF.openstack.boot_az.split(':')
            else:
                az = CONF.openstack.boot_az
        services = self.manager.get_available_services(host=host, zone=az,
                                                       binary='nova-compute')
        if not services:
            if host:
                raise exceptions.NotAvailableServices(
                    reason=f'compute service on {host} is not available')
            elif az:
                raise exceptions.NotAvailableServices(
                    reason=f'there is no available compute service for az "{az}"')
        elif len(services) == 1:
            if 'migrate' in CONF.scenario_test.scenarios:
                raise exceptions.NotAvailableServices(
                    reason='migrate test require available services >= 2')
        else:
            LOG.info('available services num is {}', len(services))

    def before_run(self):
        LOG.info('== Check before test ==')

        test_scenarios = self.get_scenarios()
        if not test_scenarios:
            LOG.warning("test scenarions is empty")
        for scenario in test_scenarios:
            if scenario not in VM_TEST_SCENARIOS:
                raise exceptions.InvalidScenario(scenario)

        if not self._manager:
            utils.load_env(CONF.openstack.env)
            self._manager = get_manager()

        self._check_flavor()
        self._check_image()
        self._check_services()

    def run(self, pre_check=True):
        if pre_check:
            self.before_run()

        error, server = False, None
        try:
            server = self.manager.create_server(wait=True,
                                                timeout=CONF.boot.timeout)

            # if CONF.boot.check_console_log:
            #     self._wait_for_console_log(vm, interval=10)
            LOG.success('created, host: {}', self.manager.get_server_host(server),
                        vm=server.id)

            for scenario in self.get_scenarios():
                test_cls = VM_TEST_SCENARIOS.get(scenario)
                test_runner = test_cls(server, self.manager)
                test_runner.run()

        except Exception as e:
            LOG.exception('test failed')
            error = True
            raise e
        else:
            LOG.success('test success', vm=server.id)
        finally:
            if server:
                self.manager.report_server_actions(server)
                if not error or CONF.scenario_test.cleanup_error_vms:
                    LOG.info('cleanup vm', vm=server.id)
                    self.manager.delete_vm(server)


def do_test_vm():
    try:
        test_task = VMScenarioTest()
        test_task.run(pre_check=False)
        return True
    except Exception as e:
        LOG.exception('test failed, {}', e)
    return False


def test_with_process():
    try:
        test_checker = VMScenarioTest()
        test_checker.before_run()
    except Exception as e:
        LOG.error('pre check failed: {}', e)
        return
    LOG.info('== Start scenario test ==')
    LOG.info('worker: {}, total: {}, scenarios: {}',
             CONF.scenario_test.worker, CONF.scenario_test.total,
             CONF.scenario_test.scenarios)

    ng = 0
    for success in utils.run_processes(do_test_vm,
                                       nums=CONF.scenario_test.total,
                                       max_workers=CONF.scenario_test.worker):
        if not success:
            ng += 1
    if ng == 0:
        log_func = LOG.success
    elif ng == CONF.scenario_test.total:
        log_func = LOG.success
    else:
        log_func = LOG.success

    log_func('OK/NG/Total: {}/{}/{}', CONF.scenario_test.total - ng,
             ng, CONF.scenario_test.total)
