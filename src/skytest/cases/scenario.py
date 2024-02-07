import random

from skytest.common import conf
from skytest.common import exceptions
from skytest.common import utils
from skytest.common import log

# from skytest.common import libvirt_guest
from skytest.common import model
from skytest.managers import base as base_manager

from . import base
from . import ecs_actions

CONF = conf.CONF
LOG = log.getLogger()

VM_TEST_SCENARIOS = ecs_actions.VM_TEST_SCENARIOS


class ECSScenarioTest(object):

    def __init__(self, actions, mgr=None) -> None:
        self.actions = actions
        self._manager = mgr
        self.ecs: model.ECS = None

    @property
    def manager(self) -> base_manager.BaseManager:
        if not self._manager:
            self._manager = base_manager.get_manager()
        return self._manager

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
            if 'migrate' in CONF.ecs_test.scenarios:
                raise exceptions.NotAvailableServices(
                    reason='migrate test require available services >= 2')
        else:
            LOG.info('available services num is {}', len(services))

    def before_run(self):
        LOG.info('==== Check before test ====')

        if not self._manager:
            utils.load_env(CONF.openstack.env)
            self._manager = base_manager.get_manager()

        self._check_flavor()
        self._check_image()
        self._check_services()

    def _test_actions(self, pre_check=True):
        if pre_check:
            self.before_run()
        LOG.info('==== Start ECS action test ====')
        action_count = [
            f'{ac["word"]} ✖ {ac["count"]}'
            for ac in utils.count_repeat_words(self.actions)
        ]
        LOG.info('test actions: {}', ' -> '.join(action_count))

        if CONF.ecs_test.ecs_id and 'create' not in self.actions[:1]:
            LOG.warning('test with ecs {}', CONF.ecs_test.ecs_id)
            self.ecs = self.manager.get_ecs(CONF.ecs_test.ecs_id)
        else:
            self.ecs = None

        jobs: list[base.EcsActionTestBase] = []
        for action in self.actions:
            LOG.info('== Test {}', action,
                     ecs='{:36}'.format(self.ecs and self.ecs.id or '-'))
            test_cls = ecs_actions.VM_TEST_SCENARIOS.get(action)
            job: base.EcsActionTestBase = test_cls(self.ecs, self.manager)
            try:
                job.run()
                self.ecs = job.ecs
            except exceptions.SkipActionException as e:
                LOG.warning('skip test action "{}": {}', action, e,
                            ecs=(self.ecs and self.ecs.id))
            else:
                LOG.success('== Test {} is ok', action,
                            ecs=(self.ecs and self.ecs.id))
                jobs.append(job)

        LOG.info('==== Tear Down ECS action test ====')
        for job in reversed(jobs):
            job.tear_down()

    def _cleanup(self):
        if not CONF.ecs_test.ecs_id and self.ecs and \
           CONF.ecs_test.cleanup_error_vms:
            LOG.info('cleanup ...', ecs=self.ecs.id)
            self.manager.delete_ecs(self.ecs)

    def run(self, pre_check=True):
        try:
            self._test_actions(pre_check=pre_check)
        except (exceptions.EcsTestFailed):
            self._cleanup()
            raise
        except Exception as e:
            self._cleanup()
            raise exceptions.EcsTestFailed(ecs=self.ecs and self.ecs.id,
                                           action='test', reason=e)
        else:
            LOG.success('==== test success ====', ecs=self.ecs.id)
        finally:
            if self.ecs:
                self.manager.report_ecs_actions(self.ecs)


def do_test_vm():
    test_task = ECSScenarioTest(parse_test_actions())
    try:
        test_task.run(pre_check=False)
        return 'ok'
    except Exception as e:
        LOG.error('test failed, {}', e)
        return 'ng'


def test_with_process():
    try:
        test_checker = ECSScenarioTest(parse_test_actions())
        test_checker.before_run()
    except Exception as e:
        LOG.error('pre check failed: {}', e)
        return

    ng = 0
    for result in utils.run_processes(do_test_vm,
                                      nums=CONF.ecs_test.total,
                                      max_workers=CONF.ecs_test.worker):
        if result == 'ng':
            ng += 1

    utils.report_results(CONF.ecs_test.total, ng)
    if ng:
        raise exceptions.TestFailed()


def test_without_process():
    ng = 0
    for _ in range(CONF.ecs_test.total):
        test_task = ECSScenarioTest(parse_test_actions())
        try:
            test_task.before_run()
            test_task.run(pre_check=False)
        except (exceptions.EcsTestFailed,
                exceptions.VMIsError) as e:
            LOG.error('test failed: {}', e)
            ng += 1
        except Exception as e:
            LOG.exception('test failed: {}', e)
            ng += 1
    utils.report_results(CONF.ecs_test.total, ng)
    if ng:
        raise exceptions.TestFailed()


def parse_test_actions() -> list:
    if CONF.ecs_test.random_order:
        test_scenarios = random.sample(CONF.ecs_test.scenarios,
                                       len(CONF.ecs_test.scenarios))
    else:
        test_scenarios = CONF.ecs_test.scenarios

    actions = []
    for scenario in test_scenarios:
        if ':' not in scenario:
            action, nums = scenario, 1
        else:
            action, nums = scenario.split(":")
        if action not in VM_TEST_SCENARIOS:
            raise exceptions.InvalidScenario(action)
        if action == 'create' and int(nums) > 1:
            raise exceptions.InvalidScenario(scenario)
        actions.extend([action] * int(nums))

    if not actions:
        raise exceptions.InvalidConfig(reason="test action is empty")
    if not CONF.ecs_test.ecs_id and 'create' not in actions[:1]:
        raise exceptions.InvalidConfig(
            reason="test action 'create' is required if 'ecs_id' is empty")

    return actions
