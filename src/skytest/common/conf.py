import os
import pathlib

from easy2use.globals import cfg2

from skytest.common import exceptions


class OpenstackConf(cfg2.OptionGroup):
    auth_username = cfg2.Option('auth_username')
    auth_url = cfg2.Option('auth_url')
    auth_user_domain_name = cfg2.Option('auth_user_domain_name',
                                        default='Default')
    auth_password = cfg2.Option('auth_password')
    auth_project_name = cfg2.Option('auth_project_name')
    auth_project_domain_name = cfg2.Option('auth_project_domain_name',
                                           default='Default')
    auth_region_name = cfg2.Option('auth_region_name', default='RegionOne')

    image_id = cfg2.Option('image_id')
    flavors = cfg2.ListOption('flavors')
    # TODO: ListOption has bug
    networks = cfg2.ListOption('networks', default=[])
    boot_from_volume = cfg2.BoolOption('boot_from_volume', default=False)
    volume_size = cfg2.IntOption('volume_size', default=50)
    volume_type = cfg2.Option('volume_type')
    boot_az = cfg2.Option('boot_az')
    nova_api_version = cfg2.Option('nova_api_version', default='2.40')
    connect_retries = cfg2.IntOption('connect_retries', default=1)
    neutron_endpoint = cfg2.Option('neutron_endpoint')


class ECSTestConf(cfg2.OptionGroup):
    ecs_id = cfg2.Option('ecs_id')
    total = cfg2.IntOption('total', default=1)
    worker = cfg2.IntOption('worker', default=1)

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

    random_actions = cfg2.BoolOption('random_actions', default=False)
    actions = cfg2.ListOption('actions', default=['create'])

    attach_interface_nums_each_time = cfg2.IntOption(
        'attach_interface_nums_each_time', default=1)

    attach_volume_nums_each_time = cfg2.IntOption(
        'attach_volume_nums_each_time', default=1)
    device_toggle_min_interval = cfg2.IntOption(
        'device_toggle_min_interval', default=4)

    enable_guest_qga_command = cfg2.BoolOption('enable_guest_qga_command',
                                               default=False)
    enable_guest_connection = cfg2.BoolOption('enable_guest_connection',
                                              default=False)
    # console log options
    enable_verify_console_log = cfg2.BoolOption('enable_verify_console_log',
                                                default=False)
    console_log_timeout = cfg2.IntOption('console_log_timeout', default=600)
    console_log_ok_keys = cfg2.ListOption('console_log_ok_keys',
                                          default=[' login:'])
    console_log_error_keys = cfg2.ListOption('console_log_error_keys',
                                             default=[])
    boot_timeout = cfg2.IntOption('timeout', default=60 * 30)
    actions_interval = cfg2.Option('actions_interval')

    attach_interface_loop_workers = cfg2.IntOption(
        'attach_interface_loop_workers', default=1)
    attach_volume_loop_workers = cfg2.IntOption('attach_volume_loop_workers',
                                                default=1)


class RebootConf(cfg2.OptionGroup):
    times = cfg2.IntOption('times', default=1)
    interval = cfg2.IntOption('interval', default=10)


class HardRebootConf(cfg2.OptionGroup):
    times = cfg2.IntOption('times', default=1)
    interval = cfg2.IntOption('interval', default=10)


class AppConf(cfg2.TomlConfig):
    verbose = cfg2.IntOption('verbose', default=0)
    log_file = cfg2.Option('log_file', default=None)
    manager = cfg2.Option('manager', default='openstack')

    openstack = OpenstackConf()
    ecs_test = ECSTestConf()


def load_configs(conf_file=None):
    conf_files = [conf_file] if conf_file else [
        '/etc/skytest/skytest.toml',
        pathlib.Path('etc', 'skytest.toml').absolute()
    ]
    for file in conf_files:
        if not os.path.exists(file):
            continue
        CONF.load(file)
        break
    else:
        raise exceptions.ConfileNotExists(
            files=[str(f) for f in conf_files])


CONF: AppConf = AppConf()
