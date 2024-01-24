from concurrent import futures
import random
import subprocess
import uuid

from novaclient import exceptions as nova_exc
import prettytable

from easy2use.common import retry
from easy2use.component import pbr
from easy2use.globals import cfg

from . import client
from skytest.common import exceptions
from skytest.common import utils
from skytest.common import log

CONF = cfg.CONF
LOG = log.getLogger()

def create_random_str(length):
    return ''.join(
        random.sample(
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
            length)
    )


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

    def _wait_for_vm(self, vm, status={'active'}, task_states=None, timeout=None,
                     interval=5):
        if isinstance(status, str):
            states = {status}
        else:
            states = status
        task_states = task_states or [None]

        def check_vm_status():
            vm.get()
            vm_state = self.get_vm_state(vm)
            if vm_state == 'error':
                raise exceptions.VMIsError(vm=vm.id)
            task_state = self.get_task_state(vm)
            LOG.debug('vm_state={}, stask_state={}',
                      vm_state, task_state, vm=vm.id)
            return vm_state in states and task_state in task_states

        retry.retry_untile_true(check_vm_status,
                                interval=interval, timeout=timeout)

        return vm

    def clean_vms(self, vms):
        for vm in vms:
            self.delete_vm(vm)

    def delete_vm(self, server, wait=True, force=False):
        if force and not hasattr(server, 'force_delete'):
            raise ValueError('force delete is not support')
        if force:
            server.force_delete()
        else:
            server.delete()
        LOG.debug('deleting', vm=server.id)
        if wait:
            try:
                self._wait_for_vm(server, status='deleted')
            except nova_exc.NotFound:
                LOG.debug('deleted', vm=server.id)
        return server

    def _wait_for_volume_deleted(self, vol, timeout=None, interval=5):

        def is_volume_not_found():
            try:
                self.client.cinder.volumes.get(vol.id)
            except Exception as e:
                LOG.debug(e)
                return True

        retry.retry_untile_true(is_volume_not_found,
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
                       snapshot=None, volume_type=None, pbr_driver=None):
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

    def create_volume(self, size_gb=None, name=None, image=None,
                       snapshot=None, wait=False, interval=1,
                       volume_type=None):
        timeout = 600

        def compute_volume_finished(result):
            LOG.debug('volume {} status: {}', result.id, result.status)
            if result.status == 'error':
                LOG.error('volume {} created failed', result.id)
                return exceptions.VolumeCreateTimeout(volume=result.id,
                                                      timeout=timeout)
            return result.status == 'available'

        name = name or utils.generate_name('vol')
        LOG.debug('creating volume {}, image={}, snapshot={}',
                  name, image, snapshot)
        try:
            vol = self.client.create_volume(name, size_gb=size_gb,
                                            image_ref=image, snapshot=snapshot,
                                            volume_type=volume_type)
        except Exception as e:
            LOG.error(e)
            raise

        if wait:
            # TODO: add timeout argument
            retry.retry_for(self.client.get_volume, args=(vol.id,),
                            interval=interval, timeout=timeout,
                            finish_func=compute_volume_finished)

        return vol

    def attach_interfaces(self, server_id, net_id, num=1):
        vm = self.client.nova.servers.get(server_id)
        for _ in range(num):
            vm.interface_attach(None, net_id, None)

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

    def delete_volume(self, volume, wait=False):
        LOG.debug('delete volume {}', volume.id)
        self.client.delete_volume(volume.id)
        if not wait:
            return
        self._wait_for_volume_deleted(volume, timeout=60)

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
            line for line in lines \
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

    def get_available_services(self, host=None, zone=None, binary=None):
        services = self.client.nova.services.list(host=host, binary=binary)
        if zone:
            services = [s for s in services if s.zone == zone]
        return [
            s for s in services if s.status == 'enabled' and s.state == 'up'
        ]

    def get_flavor_id(self, flavor):
        if not flavor:
            raise exceptions.InvalidConfig(reason='flavor is none')
        flavor_id = None

        try:
            uuid.UUID(flavor)
            return flavor
        except (TypeError, ValueError):
            if flavor not in self.flavors_cached:
                flavor_obj = self.client.nova.flavors.find(name=flavor)
                flavor_id = flavor_obj.id
                self.flavors_cached[flavor] = flavor_id

            LOG.debug('the id of flavor {} is: {}', flavor, flavor_id)
            return self.flavors_cached[flavor]

    def get_flavor(self, id_or_name):
        try:
            return self.client.nova.flavors.get(id_or_name)
        except Exception as e:
            return self.client.nova.flavors.find(name=id_or_name)

    def get_image(self, id_or_name):
        return self.client.glance.images.get(id_or_name)

    @staticmethod
    def _get_nics():
        return [
            {'net-id': net_id} for net_id in CONF.openstack.net_ids
        ] if CONF.openstack.net_ids else 'none'

    def create_server(self, name=None, timeout=1800, wait=False):
        if not name:
            name = utils.generate_name(
                CONF.openstack.boot_from_volume and 'vol-vm' or 'img-vm')

        image_id =CONF.openstack.image_id
        nics = self._get_nics()
        if not name:
            name = self.generate_name(
                CONF.openstack.boot_from_volume and 'vol-vm' or 'img-vm')
        image, block_device_mapping_v2 = None, None
        if CONF.openstack.boot_from_volume:
            block_device_mapping_v2 = [{
                'source_type': 'image', 'uuid': image_id,
                'volume_size': CONF.openstack.volume_size,
                'destination_type': 'volume', 'boot_index': 0,
                'delete_on_termination': True,
            }]
        else:
            image = image_id
        vm = self.client.nova.servers.create(
            name, image, self.get_flavor_id(CONF.openstack.flavor), nics=nics,
            block_device_mapping_v2=block_device_mapping_v2,
            availability_zone=CONF.openstack.boot_az)
        LOG.info('booting with {}',
                 'bdm' if block_device_mapping_v2 else 'image',
                 vm=vm.id)
        if wait:
            try:
                self._wait_for_vm(vm, timeout=timeout)
            except exceptions.VMIsError:
                raise exceptions.VmCreatedFailed(vm=vm.id)
            LOG.debug('created, host is {}',
                      vm.id, getattr(vm, 'OS-EXT-SRV-ATTR:host'))
        return vm

    def report_server_actions(self, vm):
        pt = prettytable.PrettyTable(['Action', 'Event', 'StartTime',
                                      'EndTime', 'Result'])
        vm_actions = self.client.get_vm_events(vm)
        vm_actions = sorted(vm_actions, key=lambda x: x[1][0]['start_time'])
        for action_name, events in vm_actions:
            for i, event in enumerate(events):
                pt.add_row([action_name if i == 0 else "",
                            event['event'],
                            event['start_time'], event['finish_time'],
                            event['result']])
        LOG.info('actions:\n{}', pt, vm=vm.id)

    def get_server_host(self, server):
        return getattr(server, 'OS-EXT-SRV-ATTR:host')

    def _wait_for_console_log(self, vm, interval=10):
        def check_vm_console_log():
            output = vm.get_console_output(length=10)
            LOG.debug('console log: {}', vm.id, output)
            for key in CONF.boot.console_log_error_keys:
                if key not in output:
                    continue
                LOG.error('found "{}" in conosole log', vm.id, key)
                raise exceptions.BootFailed(vm=vm.id)

            match_ok = sum(
                key in output for key in CONF.boot.console_log_ok_keys
            )
            if match_ok == len(CONF.boot.console_log_ok_keys):
                return True

        retry.retry_untile_true(check_vm_console_log, interval=interval,
                                timeout=600)

    def wait_for_vm_task_finished(self, vm, timeout=None, interval=5):

        def check_vm_status():
            vm.get()
            task_state = self.get_task_state(vm)
            LOG.debug('stask_state={}', vm.id, task_state)
            return not task_state

        retry.retry_untile_true(check_vm_status,
                                interval=interval, timeout=timeout)

        return vm

    def get_vm_ips(self, vm):
        ip_list = []
        for vif in self.client.list_interface(vm.id):
            ip_list.extend([ip['ip_address'] for ip in vif.fixed_ips])
        return ip_list

    def get_vm_interfaces(self, vm):
        return [
            vif.port_id for vif in self.client.list_interface(vm.id)
        ]

    def attach_volume(self, vm, volume_id, wait=False, check_with_qga=False):
        self.client.attach_volume(vm.id, volume_id)
        LOG.info('attaching volume {}', volume_id, vm=vm.id)
        if not wait:
            return

        def check_volume():
            vol = self.client.cinder.volumes.get(volume_id)
            LOG.debug('volume {} status: {}', volume_id, vol.status, vm=vm.id)
            if vol.status == 'error':
                raise exceptions.VolumeDetachFailed(volume=volume_id)
            return vol.status == 'in-use'

        retry.retry_untile_true(check_volume, interval=5, timeout=600)
        if check_with_qga:
            # qga = guest.QGAExecutor()
            # TODO: check with qga
            pass
            LOG.warning('TODO check with qga')
        LOG.info('attached volume {}', volume_id, vm=vm.id)

    def detach_volume(self, vm, volume_id, wait=False):
        self.client.detach_volume(vm.id, volume_id)
        LOG.info('detaching volume {}', volume_id, vm=vm.id)
        if not wait:
            return

        def check_volume():
            vol = self.client.cinder.volumes.get(volume_id)
            if vol.status == 'error':
                raise exceptions.VolumeDetachFailed(volume=volume_id)
            return vol.status == 'available'

        retry.retry_untile_true(check_volume, interval=5, timeout=600)
        LOG.info('detached volume {}', volume_id, vm=vm.id)
