import click
import sys
import os

from skytest.common import log
from skytest.common import conf
from skytest.common import constants
from skytest.common import exceptions
from skytest.cases import scenario

CONF = conf.CONF


@click.group(context_settings={'help_option_names': ['-h', '--help']})
def main():
    pass


@main.command()
@click.option('-a', '--actions', help='Test with specified actions')
@click.option('-c', '--conf', 'conf_file',
              default=os.getenv(constants.ENV_CONF_FILE),
              help=f'Defaults to env["{constants.ENV_CONF_FILE}"]')
@click.option('--log-file')
@click.option('-v', '--verbose', multiple=True, is_flag=True)
def action_test(verbose, log_file, conf_file, actions):
    """ECS scenario test
    """
    global LOG

    try:
        conf.load_configs(conf_file=conf_file)
    except exceptions.ConfileNotExists as e:
        print(f'ERROR: load config failed, {e}')
        sys.exit(1)
    if actions:
        test_actions = actions.split(',')
        object.__getattribute__(CONF.ecs_test, 'actions').set(test_actions)

    log.basic_config(verbose_count=max(len(verbose), CONF.verbose),
                     log_file=log_file or CONF.log_file)
    LOG = log.getLogger()

    LOG.info('worker: {}, total: {}, actions: {}',
             CONF.ecs_test.worker, CONF.ecs_test.total,
             CONF.ecs_test.actions)

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
