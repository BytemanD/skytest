import os
import pathlib

from easy2use.globals import cfg

from skytest.common import log
from skytest.common import exceptions

CONF = cfg.CONF
LOG = log.getLogger()

default_opts = [
    cfg.BooleanOption('debug', default=False),
    cfg.Option('log_to', default=None),
    cfg.Option('manager', default='openstack'),
]

openstack_opts = [
    cfg.Option('env'),
    cfg.Option('image_id'),
    cfg.Option('flavor'),
    cfg.ListOption('net_ids'),
    cfg.Option('attach_net'),
    cfg.BooleanOption('boot_from_volume', default=False),
    cfg.IntOption('volume_size', default=50),
    cfg.Option('boot_az'),
]

scenario_test_opts = [
    cfg.Option('ecs_id'),
    cfg.IntOption('total', default=1),
    cfg.IntOption('worker', default=1),
    cfg.BooleanOption('attach_net', default=False),


    cfg.IntOption('attach_port_nums', default=1),
    cfg.IntOption('attach_port_times', default=1),

    cfg.IntOption('boot_wait_interval', default=1),
    cfg.IntOption('boot_wait_timeout', default=600),

    cfg.IntOption('detach_interface_wait_interval', default=1),
    cfg.IntOption('detach_interface_wait_timeout', default=60),

    cfg.IntOption('migrate_wait_interval', default=5),
    cfg.IntOption('migrate_wait_timeout', default=60),
    cfg.BooleanOption('cleanup_error_vms', default=True),

    cfg.Option('mode', default='coroutine'),
    cfg.BooleanOption('random_order', default=False),
    cfg.ListOption('scenarios', default=['create']),

    cfg.IntOption('attach_interface_nums_each_time', default=1),
    cfg.IntOption('attach_interface_loop_times', default=2),

    cfg.IntOption('attach_volume_nums_each_time', default=1),
    cfg.IntOption('attach_volume_loop_times', default=2),
    cfg.IntOption('device_toggle_min_interval', default=4),

    cfg.BooleanOption('enable_varify_guest_ip_address', default=False),
    cfg.BooleanOption('enable_varify_guest_block', default=False),
]

boot_opts = [
     cfg.IntOption('timeout', default=60 * 30),
     cfg.BooleanOption('check_console_log', default=False),
     cfg.IntOption('console_log_timeout', default=600),
     cfg.ListOption('console_log_ok_keys', default=[' login:']),
     cfg.ListOption('console_log_error_keys', default=[]),
]

reboot_opts = [
     cfg.IntOption('times', default=1),
     cfg.IntOption('interval', default=10),
]

hard_reboot_opts = [
     cfg.IntOption('times', default=1),
     cfg.IntOption('interval', default=10),
]


def load_configs(conf_file=None):
    if not conf_file:
        conf_file = os.getenv('SKYTEST_CONF_FILE')
    conf_files = [conf_file] if conf_file else [
        '/etc/skytest/ec-nova.conf',
        pathlib.Path('etc', 'skytest.conf').absolute()
    ]
    for file in conf_files:
        if not os.path.exists(file):
            continue
        LOG.debug('Load config file from {}', file)
        CONF.load(file)
        break
    else:
        raise exceptions.ConfileNotExists(
            files=[str(f) for f in conf_files])


CONF.register_opts(default_opts)
CONF.register_opts(openstack_opts, group='openstack')
CONF.register_opts(scenario_test_opts, group='scenario_test')
CONF.register_opts(boot_opts, group='boot')
CONF.register_opts(reboot_opts, group='reboot')
CONF.register_opts(hard_reboot_opts, group='hard_reboot')
