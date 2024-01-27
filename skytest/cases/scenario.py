import random

from easy2use.globals import cfg

from skytest.common import exceptions
from skytest.common import utils
from skytest.common import log
# from skytest.common import libvirt_guest
from skytest.common import model
from skytest.managers import base

from . import vm_actions

CONF = cfg.CONF
LOG = log.getLogger()

VM_TEST_SCENARIOS = vm_actions.VM_TEST_SCENARIOS


class ECSScenarioTest(object):

    def __init__(self, mgr=None) -> None:
        self._manager = mgr
        self.ecs: model.ECS = None

    @property
    def manager(self) -> base.BaseManager:
        if not self._manager:
            self._manager = base.get_manager()
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
                    reason=f'compute service of {host} is not available')
            elif az:
                raise exceptions.NotAvailableServices(
                    reason=f'no available compute service for az "{az}"')
        elif len(services) == 1:
            if 'migrate' in CONF.scenario_test.scenarios:
                raise exceptions.NotAvailableServices(
                    reason='migrate test require available services >= 2')
        else:
            LOG.info('available services num is {}', len(services))

    def before_run(self):
        LOG.info('==== Check before test ====')

        test_scenarios = self.get_scenarios()
        if not test_scenarios:
            raise exceptions.InvalidConfig(reason="test action is empty")

        if 'create' not in test_scenarios and not CONF.scenario_test.ecs_id:
            raise exceptions.InvalidConfig(
                reason="test action 'create' is required if 'ecs_id' is empty")

        for scenario in test_scenarios:
            if scenario not in VM_TEST_SCENARIOS:
                raise exceptions.InvalidScenario(scenario)

        if not self._manager:
            utils.load_env(CONF.openstack.env)
            self._manager = base.get_manager()

        self._check_flavor()
        self._check_image()
        self._check_services()

    def domain_must_has_all_ipaddress(self):
        guest = self.manager.get_libvirt_guest(self.ecs)
        result = guest.ip_a()
        vm_ipaddresses = self.manager.get_ecs_ip_address(self.ecs)

        for ipaddress in vm_ipaddresses:
            if f'inet {ipaddress}/' not in result:
                raise exceptions.GuestDomainIpaddressNotExists(ipaddress)
        LOG.success('domain has all ip address {}', vm_ipaddresses,
                    vm=self.ecs.id)

    def run(self, pre_check=True):
        if pre_check:
            self.before_run()
        actions = self.get_scenarios()
        try:
            if CONF.scenario_test.ecs_id and 'create' not in actions:
                LOG.warning('test with ecs {}', CONF.scenario_test.ecs_id)
                self.ecs = self.manager.get_ecs(CONF.scenario_test.ecs_id)
            else:
                self.ecs = None

            # guest = self.manager.get_libvirt_guest(self.ecs)
            # if not guest.is_exists():
            #     raise Exception('domain is not exists')
            # LOG.info('domain info {}', guest.info(), vm=self.ecs.id)

            # self.domain_must_has_all_ipaddress()
            LOG.info('==== Start ECS action test ====')
            jobs = []
            for action in actions:
                test_cls = vm_actions.VM_TEST_SCENARIOS.get(action)
                job = test_cls(self.ecs, self.manager)
                try:
                    job.run()
                except exceptions.SkipActionException as e:
                    LOG.warning('{}', e, ecs=(self.ecs and self.ecs.id))
                else:
                    self.ecs = job.ecs
                    jobs.append(job)

            LOG.info('==== Tear Down ECS action test ====')
            for job in reversed(jobs):
                job.tear_down()
        except Exception as e:
            if not CONF.scenario_test.ecs_id and self.ecs and \
               CONF.scenario_test.cleanup_error_vms:
                LOG.info('cleanup', ecs=self.ecs.id)
                self.manager.delete_ecs(self.ecs)
            raise e
        else:
            LOG.success('==== test success ====', ecs=self.ecs.id)
        finally:
            if self.ecs:
                self.manager.report_ecs_actions(self.ecs)


def do_test_vm():
    test_task = ECSScenarioTest()
    try:
        test_task.run(pre_check=False)
        return 'ok'
    except Exception as e:
        LOG.error('test failed, {}', e)
        return 'ng'


def test_with_process():
    try:
        test_checker = ECSScenarioTest()
        test_checker.before_run()
    except Exception as e:
        LOG.error('pre check failed: {}', e)
        return
    LOG.info('worker: {}, total: {}, scenarios: {}',
             CONF.scenario_test.worker, CONF.scenario_test.total,
             CONF.scenario_test.scenarios)

    ng = 0
    for result in utils.run_processes(do_test_vm,
                                      nums=CONF.scenario_test.total,
                                      max_workers=CONF.scenario_test.worker):
        if result == 'ng':
            ng += 1

    utils.report_results(CONF.scenario_test.total, ng)
    if ng:
        raise exceptions.TestFailed()


def test_without_process():
    ng = 0
    for _ in range(CONF.scenario_test.total):
        test_task = ECSScenarioTest()
        try:
            test_task.before_run()
            test_task.run(pre_check=False)
        except Exception as e:
            LOG.exception('test failed, {}', e)
            ng += 1
    utils.report_results(CONF.scenario_test.total, ng)
    if ng:
        raise exceptions.TestFailed()
