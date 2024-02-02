import os
import pathlib

from easy2use.globals import cfg2

from skytest.common import log
from skytest.common import exceptions

LOG = log.getLogger()


class OpenstackConf(cfg2.OptionGroup):
    env = cfg2.Option('env')
    image_id = cfg2.Option('image_id')
    flavor = cfg2.Option('flavor')
    net_ids = cfg2.ListOption('net_ids')
    attach_net = cfg2.Option('attach_net')
    boot_from_volume = cfg2.BoolOption('boot_from_volume', default=False)
    volume_size = cfg2.IntOption('volume_size', default=50)
    boot_az = cfg2.Option('boot_az')


class ScenarioTestConf(cfg2.OptionGroup):
    ecs_id = cfg2.Option('ecs_id')
    total = cfg2.IntOption('total', default=1)
    worker = cfg2.IntOption('worker', default=1)
    attach_net = cfg2.BoolOption('attach_net', default=False)

    attach_port_nums = cfg2.IntOption('attach_port_nums', default=1)
    attach_port_times = cfg2.IntOption('attach_port_times', default=1)

    boot_wait_interval = cfg2.IntOption('boot_wait_interval', default=1)
    boot_wait_timeout = cfg2.IntOption('boot_wait_timeout', default=600)

    detach_interface_wait_interval = cfg2.IntOption(
        'detach_interface_wait_interval', default=1)
    detach_interface_wait_timeout = cfg2.IntOption(
        'detach_interface_wait_timeout', default=60)

    migrate_wait_interval = cfg2.IntOption('migrate_wait_interval', default=5)
    migrate_wait_timeout = cfg2.IntOption('migrate_wait_timeout', default=60)
    cleanup_error_vms = cfg2.BoolOption('cleanup_error_vms', default=True)

    mode = cfg2.Option('mode', default='coroutine')
    random_order = cfg2.BoolOption('random_order', default=False)
    scenarios = cfg2.ListOption('scenarios', default=['create'])

    attach_interface_nums_each_time = cfg2.IntOption(
        'attach_interface_nums_each_time', default=1)

    attach_volume_nums_each_time = cfg2.IntOption(
        'attach_volume_nums_each_time', default=1)
    device_toggle_min_interval = cfg2.IntOption(
        'device_toggle_min_interval', default=4)

    enable_varify_console_log = cfg2.BoolOption('enable_varify_console_log',
                                                default=False)
    enable_guest_qga_command = cfg2.BoolOption('enable_guest_qga_command',
                                               default=False)
    enable_guest_connection = cfg2.BoolOption('enable_guest_connection',
                                              default=False)


class BootConf(cfg2.OptionGroup):
    timeout = cfg2.IntOption('timeout', default=60 * 30)
    check_console_log = cfg2.BoolOption('check_console_log', default=False)
    console_log_timeout = cfg2.IntOption('console_log_timeout', default=600)
    console_log_ok_keys = cfg2.ListOption(
        'console_log_ok_keys', default=[' login:'])
    console_log_error_keys = cfg2.ListOption(
        'console_log_error_keys', default=[])


class RebootConf(cfg2.OptionGroup):
    times = cfg2.IntOption('times', default=1)
    interval = cfg2.IntOption('interval', default=10)


class HardRebootConf(cfg2.OptionGroup):
    times = cfg2.IntOption('times', default=1)
    interval = cfg2.IntOption('interval', default=10)


class AppConf(cfg2.TomlConfig):
    debug = cfg2.BoolOption('debug', default=False)
    log_to = cfg2.Option('log_to', default=None)
    manager = cfg2.Option('manager', default='openstack')

    openstack = OpenstackConf()
    scenario_test = ScenarioTestConf()
    boot = BootConf()
    reboot = RebootConf()
    hard_reboot = HardRebootConf()


def load_configs(conf_file=None):
    if not conf_file:
        conf_file = os.getenv('SKYTEST_CONF_FILE')
    conf_files = [conf_file] if conf_file else [
        '/etc/skytest/skytest.toml',
        pathlib.Path('etc', 'skytest.toml').absolute()
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


CONF: AppConf = AppConf()
