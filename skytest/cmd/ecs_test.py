import click
import sys

from skytest.common import log
from skytest.common import conf
from skytest.common import exceptions
from skytest.cases import scenario

CONF = conf.CONF


@click.group(context_settings={'help_option_names': ['-h', '--help']})
def main():
    pass


@main.command()
@click.option('-c', '--conf', 'conf_file')
@click.option('--log-file')
@click.option('-v', '--verbose', type=bool, multiple='count', is_flag=True)
def action_test(verbose, log_file, conf_file):
    """ECS scenario test
    """
    global LOG

    log.basic_config(verbose_count=len(verbose), log_file=log_file)
    LOG = log.getLogger()

    try:
        conf.load_configs(conf_file=conf_file)
        # import pdb; pdb.set_trace()
    except exceptions.ConfileNotExists as e:
        LOG.error('load config failed, {}', e)
        sys.exit(1)

    LOG.info('worker: {}, total: {}, scenarios: {}',
             CONF.ecs_test.worker, CONF.ecs_test.total,
             CONF.ecs_test.scenarios)

    try:
        if CONF.ecs_test.worker == 1:
            scenario.test_without_process()
        else:
            scenario.test_with_process()
    except (exceptions.InvalidConfig, exceptions.InvalidScenario,
            exceptions.TestFailed, exceptions.EcsTestFailed) as e:
        LOG.error('{}', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
