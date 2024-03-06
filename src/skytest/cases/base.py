import re

from concurrent import futures
import libvirt
from retry import retry

from skytest.common import conf
from skytest.common import exceptions
from skytest.common import log
from skytest.common import model
from skytest.common import libvirt_guest
from skytest.common import utils
from skytest.managers import base as base_manager

CONF = conf.CONF
LOG = log.getLogger()


REG_LSBLK = r'NAME="([\w/]+)" SIZE="([\w.]+)" +TYPE="([\w]+)"'


class EcsActionTestBase(object):

    def __init__(self, ecs: model.ECS,
                 manager: base_manager.BaseManager) -> None:
        self.ecs = ecs
        self.manager = manager
        self._guest: libvirt_guest.LibvirtGuest = None
        self.created_volumes: list[model.Volume] = []

    def tear_up(self): pass
    def tear_down(self): pass
    def start(self): pass

    def run(self):
        self.tear_up()
        try:
            self.start()
        except exceptions.ActionNotSuppport as e:
            raise exceptions.SkipActionException(e)

    @retry(exceptions=exceptions.EcsIsNotCreated,
           tries=CONF.ecs_test.boot_timeout/5, delay=5)
    def wait_for_ecs_created(self):
        if not self.ecs:
            raise Exception(f'{self.__class__}.ecs is None')

        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status: {:10}, task state: {:10}, host: {}',
                  self.ecs.status, self.ecs.task_state, self.ecs.host,
                  ecs=self.ecs.id)

        self.assert_ecs_is_not_error()
        if self.ecs.is_building() or self.ecs.has_task():
            raise exceptions.EcsIsNotCreated(self.ecs.id)

    @retry(exceptions=exceptions.EcsIsNotDeleted,
           tries=30, delay=1, backoff=2, max_delay=10)
    def wait_for_ecs_deleted(self):
        if not self.ecs:
            raise Exception(f'{self.__class__}.ecs is None')
        try:
            self.ecs = self.manager.get_ecs(self.ecs.id)
            LOG.debug('status: {:10}, stask_state: {:10}',
                      self.ecs.status, self.ecs.task_state, ecs=self.ecs.id)
        except exceptions.ECSNotFound:
            return
        if self.ecs.is_error():
            raise exceptions.EcsIsError(self.ecs.id)
        raise exceptions.EcsIsNotDeleted(self.ecs.id)

    @retry(exceptions=AssertionError,
           tries=60, delay=1, backoff=2, max_delay=5)
    def wait_for_ecs_task_finished(self, show_progress=False):
        self.refresh_ecs()
        LOG.debug('status={}, task state={}{}', self.ecs.status,
                  self.ecs.task_state,
                  show_progress and f' progress={self.ecs.progress}' or '',
                  ecs=self.ecs.id)
        assert not self.ecs.has_task(), f'ecs {self.ecs.id} still has task'
        assert not self.ecs.is_building(), f'ecs {self.ecs.id} is building'

    @retry(exceptions=exceptions.VolumeIsNotAvailable,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_created(self, volume: model.Volume):
        LOG.info('waiting volume {} created', volume.id, ecs=self.ecs.id)
        volume = self.manager.get_volume(volume.id)
        LOG.debug('volume {} status: {}', volume.id, volume.status,
                  ecs=self.ecs.id)
        if volume.is_error():
            raise exceptions.VolumeIsError(volume.id)
        if volume.is_creating():
            raise exceptions.VolumeIsNotAvailable(volume.id)
        LOG.debug('volume {} created', volume.id, ecs=self.ecs.id)
        return volume

    @retry(exceptions=exceptions.VolumeIsNotDeleted,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_deleted(self, volume: model.Volume):
        try:
            self.manager.get_volume(volume)
            LOG.info('volume {} status: {}', volume.id, volume.status,
                     ecs=self.ecs.id)
        except exceptions.VolumeNotFound:
            LOG.info("deleted volume {} ", volume.id, ecs=self.ecs.id)
            return
        else:
            if volume.is_error():
                raise exceptions.VolumeIsError(volume.id)
            raise exceptions.VolumeIsNotDeleted(volume.id)

    @retry(exceptions=exceptions.VolumeIsNotAvailable,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_is_available(self, volume: model.Volume):
        vol = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', vol.id, vol.status,
                 ecs=self.ecs.id)
        if not vol.is_available():
            raise exceptions.VolumeIsNotAvailable(volume.id)
        return vol

    @retry(exceptions=AssertionError,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_is_inuse(self, volume: model.Volume):
        vol = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', vol.id, vol.status, ecs=self.ecs.id)
        self.assert_volume_is_inuse(vol)
        return vol

    def get_libvirt_guest(self, host=None) -> libvirt_guest.LibvirtGuest:
        ecs_host_ip = host or self.manager.get_host_ip(self.ecs.host)
        if not self._guest or self._guest.host != ecs_host_ip:
            self._guest = libvirt_guest.LibvirtGuest(self.ecs.id,
                                                     host=ecs_host_ip)
        return self._guest

    @retry(exceptions=AssertionError,
           tries=6, delay=1, backoff=2, max_delay=10)
    def _guest_must_have_all_ipaddress(self, ecs_ip_address):
        found = set(
            re.findall(r'inet ([0-9.]+)/', self.get_libvirt_guest().ip_a()))
        LOG.debug('found ip address: {}', found, ecs=self.ecs.id)
        if '127.0.0.1' in found:
            found.remove('127.0.0.1')
        assert set(ecs_ip_address) == set(found), \
            f'ecs {self.ecs.id} does not ip address {ecs_ip_address - found}.'
        LOG.info('domain has all ip address {}', ecs_ip_address,
                 ecs=self.ecs.id)

    def guest_must_have_all_ipaddress(self):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        ecs_ip_address = set(self.manager.get_ecs_ip_address(self.ecs))
        LOG.info("ecs has ip address: {}", ecs_ip_address, ecs=self.ecs.id)
        self._guest_must_have_all_ipaddress(ecs_ip_address)

    def guest_must_have_all_block(self):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        ecs_blocks = set(self.manager.get_ecs_blocks(self.ecs))
        LOG.info("ecs has blocks: {}", ecs_blocks, ecs=self.ecs.id)
        self._guest_must_have_all_block(ecs_blocks)

    def create_volumes(self, size, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None):
        created_volumes = []
        LOG.debug('try to create {} volume(s), image={}, snapshot={}',
                  num, image, snapshot, ecs=self.ecs.id)

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.manager.create_volume,
                                     size_gb=size, image=image,
                                     snapshot=snapshot,
                                     volume_type=volume_type)
                     for _ in range(1, num + 1)]
            LOG.info('creating {} volume(s) ...', num, ecs=self.ecs.id)
            for task in futures.as_completed(tasks):
                vol = task.result()
                if not vol:
                    continue
                created_volumes.append(vol)

        for volume in created_volumes:
            self.wait_volume_created(volume)
        return created_volumes

    def create_ports(self, networks, workers=None) -> list[str]:
        created_ports = []
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(self.manager.create_port, networks)
            for result in results:
                created_ports.append(result)
        return created_ports

    @retry(exceptions=AssertionError,
           tries=60, delay=1, backoff=2, max_delay=10)
    def _guest_must_have_all_block(self, ecs_blocks):
        found = set(re.findall(r'NAME="([a-zA-Z/]+)"',
                               self.get_libvirt_guest().lsblk()))
        LOG.debug('found blocks: {}', found, ecs=self.ecs.id)
        assert set(ecs_blocks) == set(found), \
            f'ecs {self.ecs.id} does not block {ecs_blocks - found}.'
        LOG.info('domain has all blocks {}', ecs_blocks, ecs=self.ecs.id)

    def guest_find_all_blocks(self) -> list[dict]:
        found = set(re.findall(REG_LSBLK, self.get_libvirt_guest().lsblk()))
        return [{'name': v[0], 'size': v[1], 'type': v[2]} for v in found]

    @retry(exceptions=AssertionError,
           tries=12, delay=1, backoff=2, max_delay=5)
    def guest_block_size_must_be(self, name, size):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        blocks = [blk for blk in self.guest_find_all_blocks()
                  if blk['name'] == name]
        LOG.info('block {} size is {}', name, blocks[0].get('size'),
                 ecs=self.ecs.id)
        assert blocks[0].get('size') == size, \
            f'block {name} size is {blocks[0]} , not {size}'

    @retry(exceptions=exceptions.EcsNotMatchOKConsoleLog,
           tries=CONF.ecs_test.console_log_timeout,
           delay=1, backoff=2, max_delay=5)
    def ecs_must_have_ok_console_log(self):
        if not CONF.ecs_test.enable_verify_console_log:
            return
        output = self.manager.get_ecs_console_log(self.ecs, length=10)
        LOG.debug('console log:\n{}', output, ecs=self.ecs.id)
        for key in CONF.ecs_test.console_log_ok_keys:
            if key in output:
                LOG.info('found "{}" in console.log', key, ecs=self.ecs.id)
                return
        for key in CONF.ecs_test.console_log_error_keys:
            if key in output:
                LOG.error('found "{}" in console.log', key, ecs=self.ecs.id)
                raise exceptions.EcsMatchErrorConsoleLog(self.ecs.id)
        raise exceptions.EcsNotMatchOKConsoleLog(self.ecs.id)

    @retry(exceptions=AssertionError, tries=10, delay=1, max_delay=6)
    def ecs_guest_must_have_hostname(self, name):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        guest = self.get_libvirt_guest()
        hostname = guest.hostname()
        LOG.info('guest hostname is "{}"', hostname, ecs=self.ecs.id)
        assert hostname == name, f'ecs {self.ecs.id} name is not "{name}"'

    def get_ecs_flavor_id(self) -> str:
        return self.manager.get_ecs_flavor_id(self.ecs)

    def refresh_ecs(self):
        self.ecs = self.manager.get_ecs(self.ecs.id)

    @retry(exceptions=libvirt.libvirtError, tries=60*6, delay=5)
    def wait_ecs_qga_connected(self):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        LOG.debug('waiting QGA is connected', ecs=self.ecs.id)
        guest = self.get_libvirt_guest()
        guest.guest_exec('hostname')

    @retry(exceptions=AssertionError, tries=12, delay=5)
    def wait_ecs_guest_active(self, host=None):
        if not CONF.ecs_test.enable_guest_connection:
            return
        LOG.debug('waiting guest to be active', ecs=self.ecs.id)
        guest = self.get_libvirt_guest(host=host)
        assert guest.is_active, f'ecs {self.ecs.id} guest is not active'

    @retry(exceptions=AssertionError, tries=60, delay=5)
    def wait_ecs_guest_not_exists(self, host=None):
        if not CONF.ecs_test.enable_guest_connection:
            return
        LOG.debug('waiting guest to be deleted', ecs=self.ecs.id)
        guest = self.get_libvirt_guest(host=host)
        assert guest.is_exists(), f'ecs {self.ecs.id} guest is still exists'
        LOG.info('guest is not exists', ecs=self.ecs.id)

    def assert_ecs_has_interfaces(self, interfaces: list[str]):
        vifs = self.manager.get_ecs_interfaces(self.ecs)
        for vif_id in interfaces:
            assert vif_id in vifs, \
                f'ecs {self.ecs.id} does not have interface {vif_id}'

    @retry(exceptions=AssertionError, tries=30, delay=2)
    def assert_ecs_has_no_interfaces(self, interfaces: list[str]):
        vifs = self.manager.get_ecs_interfaces(self.ecs)
        for vif_id in interfaces:
            assert vif_id not in vifs, \
                f'ecs {self.ecs.id} has interface {vif_id}'

    def assert_ecs_is_active(self):
        LOG.info('ecs status is {}', self.ecs.status, ecs=self.ecs.id)
        assert self.ecs.is_active(), f'ecs {self.ecs.id} is not ACTIVE'

    def assert_ecs_is_not_error(self):
        LOG.info('ecs status is {}', self.ecs.status, ecs=self.ecs.id)
        assert not self.ecs.is_error(), f'ecs {self.ecs.id} is not ERROR'

    def assert_ecs_is_shelved(self):
        LOG.info('ecs status is {}', self.ecs.status, ecs=self.ecs.id)
        assert self.ecs.is_shelved(), f'ecs {self.ecs.id} is not SHELVED'

    def assert_ecs_is_stopped(self):
        assert self.ecs.is_stopped(), f'ecs {self.ecs.id} is not STOPPED'
        LOG.info('ecs is stopped', ecs=self.ecs.id)

    def assert_volume_is_inuse(self, volume: model.Volume):
        assert volume.is_inuse(), f'volume {volume.id} not in use'

    def assert_ecs_host_is_not(self, host: str):
        assert self.ecs.host != host, f'ecs {self.ecs.id} host is {host}'
        LOG.info('host is {}', self.ecs.host, ecs=self.ecs.id)

    def assert_ecs_name_is(self, name: str):
        assert self.ecs.name == name, f'ecs {self.ecs.id} name is not {name}'

    def assert_ecs_flavor_is(self, flavor_id: str):
        ecs_flavor_id = self.get_ecs_flavor_id()
        LOG.info('ecs flavor id is {}', ecs_flavor_id, ecs=self.ecs.id)
        assert ecs_flavor_id == flavor_id, \
            f'ecs {self.ecs.id} flavor is not {flavor_id}'
