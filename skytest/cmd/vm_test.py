import click
import logging
import os
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
def vm_scenario_test(verbose, log_file, conf_file):
    """VM scenario test
    """
    global LOG

    log.basic_config(verbose_count=len(verbose), log_file=log_file)
    LOG = log.getLogger()

    try:
        conf.load_configs(conf_file=conf_file)
    except exceptions.ConfileNotExists as e:
        LOG.error('load config failed, {}', e)
        sys.exit(1)

    scenario.test_with_process()


if __name__ == '__main__':
    main()