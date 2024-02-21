import random
import time

from skytest.common import conf
from skytest.common import exceptions
from skytest.common import utils
from skytest.common import log

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

        self._actions_interval_range = None
        if CONF.ecs_test.actions_interval:
            nums = CONF.ecs_test.actions_interval.split('-')
            if len(nums) == 1:
                self._actions_interval_range = (int(nums[0]), int(nums[0]))
            else:
                self._actions_interval_range = (int(nums[0]), int(nums[1]))

    @property
    def manager(self) -> base_manager.BaseManager:
        if not self._manager:
            self._manager = base_manager.get_manager()
        return self._manager

    def _check_flavor(self):
        if not CONF.openstack.flavors:
            raise exceptions.InvalidConfig(reason='flavors is not set')
        try:
            self.manager.get_flavor(CONF.openstack.flavors[0])
        except Exception as e:
            raise exceptions.InvalidFlavor(reason=e)

    def _check_image(self):
        """Make sure configed actions are all exists"""
        if not CONF.openstack.image_id:
            raise exceptions.InvalidConfig(reason='image is not set')

        try:
            self.manager.get_image(CONF.openstack.image_id)
        except Exception as e:
            raise exceptions.InvalidImage(reason=e)

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
            if 'migrate' in self.actions:
                raise exceptions.NotAvailableServices(
                    reason='migrate test require available services >= 2')
        else:
            LOG.info('available services num is {}', len(services))

    def before_run(self):
        LOG.info('==== Check before test ====')

        if not self._manager:
            self._manager = base_manager.get_manager()

        self._check_flavor()
        self._check_image()
        self._check_services()

    def _test_actions(self, pre_check=True):
        if pre_check:
            self.before_run()
        LOG.info('==== Start ECS action test ====')
        action_count = [
            f'{ac["word"]}({ac["count"]})'
            for ac in utils.count_repeat_words(self.actions)
        ]
        LOG.info('test actions: {}', ' -> '.join(action_count))

        if CONF.ecs_test.ecs_id and 'create' not in self.actions[:1]:
            LOG.warning('test with ecs {}', CONF.ecs_test.ecs_id)
            self.ecs = self.manager.get_ecs(CONF.ecs_test.ecs_id)
        else:
            self.ecs = None

        jobs: list[base.EcsActionTestBase] = []
        for i, action in enumerate(self.actions):
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
            except AssertionError as e:
                raise exceptions.EcsTestFailed(
                    ecs=self.ecs and self.ecs.id or '-',
                    action=action, reason=f'{str(e)}')
            except Exception as e:
                LOG.exception(e)
                raise exceptions.EcsTestFailed(
                    ecs=self.ecs and self.ecs.id or '-',
                    action=action, reason=f'{str(e)}')
            else:
                LOG.success('== Test {} is ok', action,
                            ecs=(self.ecs and self.ecs.id))
                jobs.append(job)

            if i < len(self.actions) - 1:
                interval = self._get_actions_interval()
                if interval:
                    LOG.info('sleep {} seconds', interval, ecs=self.ecs.id)
                    time.sleep(interval)

        LOG.info('==== Tear Down ECS action test ====')
        for job in reversed(jobs):
            job.tear_down()

    def _get_actions_interval(self):
        if not self._actions_interval_range:
            return None
        return random.randint(self._actions_interval_range[0],
                              self._actions_interval_range[1])

    def _cleanup(self):
        if not CONF.ecs_test.ecs_id and self.ecs and \
           CONF.ecs_test.cleanup_error_vms:
            LOG.info('cleanup ...', ecs=self.ecs.id)
            self.manager.delete_ecs(self.ecs)

    def run(self, pre_check=True):
        try:
            self._test_actions(pre_check=pre_check)
        except exceptions.EcsTestFailed:
            self._cleanup()
            raise
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
    ecs_actions.init()
    ng = 0
    for _ in range(CONF.ecs_test.total):
        test_task = ECSScenarioTest(parse_test_actions())
        try:
            test_task.before_run()
            test_task.run(pre_check=False)
        except (exceptions.InvalidConfig, exceptions.InvalidFlavor,
                exceptions.InvalidImage, exceptions.EcsTestFailed,
                exceptions.EcsIsError) as e:
            LOG.error('test failed: {}', e)
            ng += 1
        except Exception as e:
            LOG.exception('test failed: {}', e)
            ng += 1
    utils.report_results(CONF.ecs_test.total, ng)
    if ng:
        raise exceptions.TestFailed()


def parse_test_actions() -> list:
    ecs_actions.init()
    if CONF.ecs_test.random_actions:
        test_actions = random.sample(CONF.ecs_test.actions,
                                     len(CONF.ecs_test.actions))
        if 'create' in test_actions and test_actions.index('create') != 0:
            test_actions.remove('create')
            test_actions.insert(0, 'create')
    else:
        test_actions = CONF.ecs_test.actions

    actions = []
    for action_num in test_actions:
        if ':' not in action_num:
            action, nums = action_num, 1
        else:
            action, nums = action_num.split(":")
        if action not in VM_TEST_SCENARIOS:
            raise exceptions.InvalidScenario(action)
        if action == 'create' and int(nums) > 1:
            raise exceptions.InvalidScenario(action_num)
        actions.extend([action] * int(nums))

    if not actions:
        raise exceptions.InvalidConfig(reason="test action is empty")
    if not CONF.ecs_test.ecs_id and 'create' not in actions[:1]:
        raise exceptions.InvalidConfig(
            reason="test action 'create' is required if 'ecs_id' is empty")

    return actions
