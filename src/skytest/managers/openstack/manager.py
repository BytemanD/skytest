from concurrent import futures
import functools
import random
import subprocess

import prettytable

from novaclient import exceptions as nova_exc
from cinderclient import exceptions as cinder_exc

from easy2use.common import retry as easy_retry
from easy2use.component import pbr

from skytest.common import exceptions
from skytest.common import conf
from skytest.common import utils
from skytest.common import log
from skytest.common import model
from . import client

CONF = conf.CONF
LOG = log.getLogger()


def create_random_str(length):
    return ''.join(
        random.sample(
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
            length)
    )


def wrap_exceptions(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except nova_exc.ClientException as e:
            raise exceptions.EcsCloudAPIError(e)
    return wrapper


class OpenstackManager:

    def __init__(self):
        self.client = client.OpenstackClient.create_instance()
        self.flavors_cached = {}

    def get_task_state(self, vm, refresh=False):
        if refresh:
            vm = self.client.nova.servers.get(vm.id)
        return getattr(vm, 'OS-EXT-STS:task_state')

    def get_vm_state(self, vm, refresh=False) -> str:
        if refresh:
            vm.get()
        return getattr(vm, 'OS-EXT-STS:vm_state')

    def find_servers(self, name=None, status=None, host=None,
                     all_tenants=False):
        LOG.debug('find servers with name={}, status={}, host={}'
                  'all_tenants={}', name, status, host, all_tenants)
        vms = []
        search_opts = {}
        if all_tenants:
            search_opts['all_tenants'] = 1
        for vm in self.client.nova.servers.list(search_opts=search_opts):
            vm_state = self.get_vm_state(vm)
            LOG.debug('name={}, vm_state={}',
                      vm.id, vm.name, vm_state)
            if name and (name not in vm.name) or \
               status and vm_state != status or\
               host and getattr(vm, 'OS-EXT-SRV-ATTR:host') != host:
                continue
            vms.append(vm)
        return vms

    def _wait_for_vm(self, ecs: model.ECS, status={'active'}, task_states=None,
                     timeout=None, interval=5):
        if isinstance(status, str):
            states = {status}
        else:
            states = status
        task_states = task_states or [None]

        def check_vm_status(ecs):
            ecs = self.get_ecs(ecs.id)
            if ecs.is_error():
                raise exceptions.EcsIsError(ecs.id)
            LOG.debug('status={}, stask state={}',
                      ecs.status, ecs.task_state, ecs=ecs.id)
            return ecs.status in states \
                and ecs.task_state in task_states

        easy_retry.retry_untile_true(check_vm_status, args=(ecs,),
                                     interval=interval, timeout=timeout)

        return ecs

    def clean_vms(self, ecs_list):
        for ecs in ecs_list:
            self.delete_ecs(ecs)

    def delete_ecs(self, ecs: model.ECS, force=False):
        if force and not hasattr(ecs, 'force_delete'):
            raise ValueError('force delete is not support')

        if force:
            self.client.nova.servers.force_delete(ecs.id)
        else:
            self.client.nova.servers.delete(ecs.id)

    def _wait_for_volume_deleted(self, vol, timeout=None, interval=5):

        def is_volume_not_found():
            try:
                self.client.cinder.volumes.get(vol.id)
            except Exception as e:
                LOG.debug(e)
                return True

        easy_retry.retry_untile_true(is_volume_not_found,
                                     interval=interval, timeout=timeout)

    def delete_vms(self, name=None, host=None, status=None, all_tenants=False,
                   workers=None, force=False):
        workers = workers or 1
        servers = self.find_servers(name=name, status=status, host=host,
                                    all_tenants=all_tenants)
        LOG.info('found {} deletable server(s)', len(servers))
        if not servers:
            return

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.delete_vm, vm, force=force)
                     for vm in servers]

            with pbr.progressbar(len(servers), description='delete vm') as bar:
                for _ in futures.as_completed(tasks):
                    bar.update(1)
        bar.close()

    def create_volumes(self, size, name=None, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None):
        name = name or utils.generate_name('vol')
        workers = workers or num
        LOG.info('Try to create {} volume(s), name: {}, image: {}, '
                 'snapshot: {}, workers: {} ', num, name, image, snapshot,
                 workers)
        volumes = []

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.create_volume,
                                     size_gb=size, name=f'{name}-{index}',
                                     image=image, snapshot=snapshot,
                                     volume_type=volume_type, wait=True)
                     for index in range(1, num + 1)]
            LOG.info('Creating, please be patient ...')
            for task in futures.as_completed(tasks):
                vol = task.result()
                if not vol:
                    continue
                LOG.debug('created new volume: {}({})', vol.name, vol.id)
                volumes.append(vol)

        return volumes

    @wrap_exceptions
    def attach_interface(self, ecs: model.ECS, port_id) -> str:
        vif = self.client.nova.servers.interface_attach(ecs.id, port_id, None,
                                                        None)
        return vif.port_id

    @wrap_exceptions
    def attach_net(self, ecs: model.ECS, net_id) -> str:
        vif = self.client.nova.servers.interface_attach(ecs.id, None, net_id,
                                                        None)
        return vif.port_id

    @wrap_exceptions
    def attach_interfaces(self, ecs: model.ECS, net_id, num=1):
        vm = self.client.nova.servers.get(ecs.id)
        for _ in range(num):
            vm.interface_attach(None, net_id, None)

    @wrap_exceptions
    def detach_interface(self, ecs: model.ECS, vif: str):
        self.client.detach_server_interface(ecs.id, vif, wait=True)

    def detach_interfaces(self, server_id, port_ids=None, start=0, end=None):
        if not port_ids:
            port_ids = [
                vif.id for vif in self.client.get_server_interfaces(server_id)
            ]
        port_ids = port_ids[start:(end or len(port_ids))]
        LOG.info('detach interfaces: {}', server_id, port_ids)
        if not port_ids:
            return

        for port_id in port_ids:
            self.client.detach_server_interface(server_id, port_id, wait=True)

    def delete_volumes(self, volumes, workers=None):
        LOG.debug('try to delete volumes: {}', volumes)
        with futures.ThreadPoolExecutor(max_workers=workers or 1) as executor:
            tasks = [executor.submit(self.delete_volume, vol, wait=True)
                     for vol in volumes]
            LOG.info('deleting volumes, please be patient ...')
            completed = 0
            for _ in futures.as_completed(tasks):
                completed += 1
                LOG.info('deleted volume {}', completed)

    def rbd_ls(self, pool):
        status, lines = subprocess.getstatusoutput(f'rbd ls {pool}')
        if status != 0:
            raise RuntimeError(f'Run rbd ls failed, {lines}')
        return lines.split('\n')

    def rbd_rm(self, pool, image):
        cmd = f'rbd remove {pool}/{image}'
        status, output = subprocess.getstatusoutput(cmd)
        if status != 0:
            raise RuntimeError(f'Run rbd rm failed, {output}')

    def cleanup_rbd(self, pool, workers=1):
        volumes = [
            'volume-{}'.format(vol.id) for vol in self.client.list_volumes()]
        lines = self.rbd_ls(pool)
        delete_images = [
            line for line in lines
            if line and line.startswith('volume') and line not in volumes]
        LOG.info('Found {} image(s)', len(delete_images))
        if not delete_images:
            return
        LOG.info('Try to delete {} image(s) with rbd', len(delete_images))

        def delete_image(image):
            return self.rbd_rm(pool, image)

        bar = pbr.factory(len(delete_images), driver='logging')
        with futures.ThreadPoolExecutor(max_workers=workers or 1) as executor:
            LOG.info('Deleting, please be patient ...')
            for _ in executor.map(delete_image, delete_images):
                bar.update(1)
            bar.close()

    @wrap_exceptions
    def get_available_services(self, host=None, zone=None, binary=None):
        services = self.client.nova.services.list(host=host, binary=binary)
        if zone:
            services = [s for s in services if s.zone == zone]
        return [
            s for s in services if s.status == 'enabled' and s.state == 'up'
        ]

    @wrap_exceptions
    def get_flavor_id(self, flavor):
        if not flavor:
            raise exceptions.InvalidConfig(reason='flavor is none')
        flavor_id = None
        flavor_obj = self.get_flavor(flavor)
        flavor_id = flavor_obj.id
        self.flavors_cached[flavor] = flavor_id
        LOG.debug('the id of flavor {} is: {}', flavor, flavor_id)
        return self.flavors_cached[flavor]

    @wrap_exceptions
    def get_flavor(self, id_or_name):
        try:
            return self.client.nova.flavors.get(id_or_name)
        except Exception:
            return self.client.nova.flavors.find(name=id_or_name)

    @wrap_exceptions
    def get_image(self, id_or_name):
        return self.client.glance.images.get(id_or_name)

    def _parse_server_to_ecs(self, server) -> model.ECS:
        return model.ECS(
            id=server.id, name=server.name,
            status=getattr(server, 'OS-EXT-STS:vm_state') or '',
            task_state=getattr(server, 'OS-EXT-STS:task_state') or '',
            host=getattr(server, 'OS-EXT-SRV-ATTR:host') or '',
            progress=getattr(server, 'progress', None),)

    @wrap_exceptions
    def create_ecs(self, flavor, name=None, networks=None) -> model.ECS:
        if not name:
            name = utils.generate_name(
                CONF.openstack.boot_from_volume and 'vol-vm' or 'img-vm')

        image_id = CONF.openstack.image_id
        nics = [
            {'net-id': net_id} for net_id in networks
        ] if networks else 'none'
        if not name:
            name = utils.generate_name(
                CONF.openstack.boot_from_volume and 'vol-vm' or 'img-vm')
        image, bdm_v2 = None, None
        if CONF.openstack.boot_from_volume:
            bdm_v2 = [{
                'source_type': 'image', 'uuid': image_id,
                'volume_size': CONF.openstack.volume_size,
                'destination_type': 'volume', 'boot_index': 0,
                'delete_on_termination': True,
            }]
        else:
            image = image_id
        server = self.client.nova.servers.create(
            name, image, flavor, nics=nics,
            block_device_mapping_v2=bdm_v2,
            availability_zone=CONF.openstack.boot_az)
        LOG.info('booting with {}', 'bdm' if bdm_v2 else 'image',
                 ecs=server.id)

        return self.get_ecs(server.id)

    @wrap_exceptions
    def get_ecs(self, ecs_id):
        try:
            server = self.client.nova.servers.get(ecs_id)
        except nova_exc.NotFound:
            raise exceptions.ECSNotFound(ecs_id)
        return self._parse_server_to_ecs(server)

    @wrap_exceptions
    def stop_ecs(self, ecs):
        self.client.nova.servers.stop(ecs.id)

    @wrap_exceptions
    def start_ecs(self, ecs):
        self.client.nova.servers.start(ecs.id)

    @wrap_exceptions
    def reboot_ecs(self, ecs):
        self.client.nova.servers.reboot(ecs.id)

    @wrap_exceptions
    def hard_reboot_ecs(self, ecs):
        self.client.nova.servers.reboot(ecs.id, reboot_type='HARD')

    @wrap_exceptions
    def live_migrate_ecs(self, ecs):
        self.client.nova.servers.live_migrate(ecs.id, host=None,
                                              block_migration=True)

    @wrap_exceptions
    def migrate_ecs(self, ecs: model.ECS):
        self.client.nova.servers.migrate(ecs.id)

    @wrap_exceptions
    def get_ecs_console_log(self, ecs: model.ECS, length=None):
        return self.client.nova.servers.get_console_output(ecs.id,
                                                           length=length)

    def report_ecs_actions(self, ecs: model.ECS):
        pt = prettytable.PrettyTable(['Action', 'Request Id', 'Event',
                                      'StartTime', 'EndTime', 'Host',
                                      'Result'])
        pt.align['Action'] = 'l'
        pt.align['Event'] = 'l'
        vm_actions = self.client.get_server_events(ecs.id)

        # vm_actions = sorted(vm_actions, key=lambda x: x[1][0]['start_time'])
        for action_name, req_id, events in vm_actions:
            for i, event in enumerate(events or []):
                pt.add_row([action_name if i == 0 else "",
                            req_id if i == 0 else "",
                            event['event'], event['start_time'],
                            event['finish_time'], event.get('host'),
                            event['result']])
        LOG.info('actions:\n{}', pt, ecs=ecs.id)

    def get_server_host(self, server):
        return getattr(server, 'OS-EXT-SRV-ATTR:host')

    def get_server_id(self, server):
        return getattr(server, 'id')

    @wrap_exceptions
    def wait_for_vm_task_finished(self, vm, timeout=None, interval=5):
        def check_vm_status():
            vm.get()
            task_state = self.get_task_state(vm)
            LOG.debug('stask_state={}', vm.id, task_state)
            return not task_state

        easy_retry.retry_untile_true(check_vm_status,
                                     interval=interval, timeout=timeout)
        return vm

    @wrap_exceptions
    def get_ecs_interfaces(self, ecs: model.ECS) -> list:
        return [vif.port_id for vif in self.client.list_interface(ecs.id)]

    @wrap_exceptions
    def get_ecs_ip_address(self, ecs: model.ECS):
        ip_list = []
        for vif in self.client.list_interface(ecs.id):
            ip_list.extend([ip['ip_address'] for ip in vif.fixed_ips])
        return ip_list

    @wrap_exceptions
    def get_host_ip(self, hostname):
        hypervisors = self.client.nova.hypervisors.search(hostname)
        if not hypervisors:
            raise exceptions.HypervisorNotFound(hostname)
        hypervisors[0].get()
        return hypervisors[0].host_ip

    def _parse_volume(self, vol) -> model.Volume:
        return model.Volume(vol.id, vol.size, name=vol.name or '',
                            status=vol.status or '')

    @wrap_exceptions
    def get_volume(self, volume_id) -> model.Volume:
        try:
            volume = self.client.cinder.volumes.get(volume_id)
            return self._parse_volume(volume)
        except cinder_exc.NotFound:
            raise exceptions.VolumeNotFound(volume_id)

    @wrap_exceptions
    def create_volume(self, size_gb=None, name=None, image=None,
                      snapshot=None, volume_type=None) -> model.Volume:
        name = name or utils.generate_name('vol')
        LOG.debug('creating volume {}, image={}, snapshot={}',
                  name, image, snapshot)
        vol = self.client.create_volume(name, size_gb=size_gb,
                                        image_ref=image, snapshot=snapshot,
                                        volume_type=volume_type)
        return self._parse_volume(vol)

    @wrap_exceptions
    def delete_volume(self, volume: model.Volume):
        self.client.delete_volume(volume.id)

    @wrap_exceptions
    def attach_volume(self, ecs: model.ECS, volume_id: str):
        self.client.attach_volume(ecs.id, volume_id)

    @wrap_exceptions
    def detach_volume(self, ecs: model.ECS, volume_id):
        self.client.detach_volume(ecs.id, volume_id)

    @wrap_exceptions
    def get_ecs_blocks(self, ecs: model.ECS) -> list[str]:
        """e.g. ['/dev/sda' '/dev/sdb']"""
        return [vol.device for vol in self.client.get_ecs_volumes(ecs.id)]

    def _parse_volume_attachment(self, attached):
        return model.VolumeAttachment(attached.id, volumeId=attached.volumeId,
                                      device=attached.device)

    @wrap_exceptions
    def get_ecs_volumes(self, ecs: model.ECS) -> list[model.VolumeAttachment]:
        return [self._parse_volume_attachment(vol)
                for vol in self.client.get_ecs_volumes(ecs.id)]

    @wrap_exceptions
    def extend_volume(self, volume: model.Volume, new_size):
        self.client.extend_volume(volume.id, new_size)

    def rebuild_ecs(self, ecs: model.ECS, image=None, password=None):
        if not image:
            server = self.client.nova.servers.get(ecs.id)
            image = server.image.get('id')
        LOG.debug('rebuild with image {}', image, ecs=ecs.id)
        self.client.nova.servers.rebuild(ecs.id, image, password=password)

    @wrap_exceptions
    def resize_ecs(self, ecs: model.ECS, flavor):
        self.client.nova.servers.resize(ecs.id, flavor)

    @wrap_exceptions
    def rename_ecs(self, ecs: model.ECS, name: str):
        self.client.nova.servers._action('rename', ecs.id, {'name': name})

    @wrap_exceptions
    def shelve_ecs(self, ecs: model.ECS):
        self.client.nova.servers.shelve(ecs.id)

    @wrap_exceptions
    def unshelve_ecs(self, ecs: model.ECS):
        self.client.nova.servers.unshelve(ecs.id)

    @wrap_exceptions
    def pause_ecs(self, ecs: model.ECS):
        self.client.nova.servers.pause(ecs.id)

    @wrap_exceptions
    def unpause_ecs(self, ecs: model.ECS):
        self.client.nova.servers.unpause(ecs.id)


    @wrap_exceptions
    def get_ecs_flavor_id(self, ecs: model.ECS):
        server = self.client.nova.servers.get(ecs.id)
        flavor = self.get_flavor(server.flavor['original_name'])
        return flavor.id

    def must_support_action(self, ecs: model.ECS, action):
        if action == 'rename':
            if CONF.openstack.nova_api_version < '2.53':
                raise exceptions.ActionNotSuppport(
                    'rename', reason='nova api version must >= 2.53')
        return True

    def _parse_port(self, port: dict) -> model.Volume:
        return model.Port(port.get('id'), port.get('name'),
                          status=port.get('status'),
                          host=port.get('binding:host_id'))

    @wrap_exceptions
    def create_port(self, network_id) -> model.Port:
        data = {'network_id': network_id, 'name': utils.generate_name('port')}
        port = self.client.neutron.create_port(body={'port': data})
        return self._parse_port(port.get('port'))

    @wrap_exceptions
    def get_port(self, port_id) -> model.Port:
        port = self.client.neutron.show_port(port_id)
        return self._parse_port(port.get('port'))

    @wrap_exceptions
    def delete_port(self, port_id) -> model.Port:
        return self.client.neutron.delete_port(port_id)
