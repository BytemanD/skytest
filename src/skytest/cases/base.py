import re

from concurrent import futures
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
        if self.ecs.is_error():
            raise exceptions.VMIsError(vm=self.ecs.id)
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
            raise exceptions.VMIsError(vm=self.ecs.id)
        raise exceptions.EcsIsNotDeleted(self.ecs.id)

    @retry(exceptions=exceptions.EcsHasTask,
           tries=30, delay=1, backoff=2, max_delay=10)
    def wait_for_ecs_task_finished(self, show_progress=False):
        self.ecs = self.manager.get_ecs(self.ecs)
        LOG.debug('status={}, task state={}{}', self.ecs.status,
                  self.ecs.task_state,
                  show_progress and f' progress={self.ecs.progress}' or '',
                  ecs=self.ecs.id)
        if self.ecs.has_task():
            raise exceptions.EcsHasTask(self.ecs.id)

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

    @retry(exceptions=exceptions.VolumeIsNotInuse,
           tries=60, delay=1, backoff=2, max_delay=10)
    def wait_volume_is_inuse(self, volume: model.Volume):
        vol = self.manager.get_volume(volume.id)
        LOG.info('volume {} status: {}', vol.id, vol.status, ecs=self.ecs.id)
        if not vol.is_inuse():
            raise exceptions.VolumeIsNotInuse(volume.id)
        return vol

    def get_libvirt_guest(self):
        ecs_host_ip = self.manager.get_host_ip(self.ecs.host)
        if not self._guest or self._guest.host != ecs_host_ip:
            self._guest = libvirt_guest.LibvirtGuest(self.ecs.id,
                                                     host=ecs_host_ip)
        return self._guest

    @retry(exceptions=exceptions.EcsDoseNotHaveIpAddress,
           tries=60, delay=1, backoff=2, max_delay=10)
    def _guest_must_have_all_ipaddress(self, ecs_ip_address):
        found = set(
            re.findall(r'inet ([0-9.]+)/', self.get_libvirt_guest().ip_a()))
        LOG.debug('found ip address: {}', found, ecs=self.ecs.id)
        if '127.0.0.1' in found:
            found.remove('127.0.0.1')
        if set(ecs_ip_address) != set(found):
            raise exceptions.EcsDoseNotHaveIpAddress(self.ecs.id,
                                                     ecs_ip_address - found)
        LOG.info('domain has all ip address {}', ecs_ip_address,
                 ecs=self.ecs.id)

    def guest_must_have_all_ipaddress(self):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        ecs_ip_address = set(self.manager.get_ecs_ip_address(self.ecs))
        LOG.info("ecs has ip address: {}", ecs_ip_address, ecs=self.ecs.id)
        self._guest_must_have_all_ipaddress(ecs_ip_address)

    @retry(exceptions=exceptions.EcsDoseNotHaveBlock,
           tries=60, delay=1, backoff=2, max_delay=10)
    def guest_must_have_all_block(self):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        ecs_blocks = set(self.manager.get_ecs_blocks(self.ecs))
        LOG.info("ecs has blocks: {}", ecs_blocks, ecs=self.ecs.id)
        self._guest_must_have_all_block(ecs_blocks)

    def create_volumes(self, size, name=None, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None):
        LOG.debug('try to create {} volume(s), name={}, image={}, snapshot={}',
                  num, name, image, snapshot, ecs=self.ecs.id)
        self.created_volumes = []
        if not name:
            name = utils.generate_name('vol')

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.manager.create_volume,
                                     size_gb=size, name=f'{name}-{index}',
                                     image=image, snapshot=snapshot,
                                     volume_type=volume_type)
                     for index in range(1, num + 1)]
            LOG.info('creating {} volume(s) ...', num, ecs=self.ecs.id)
            for task in futures.as_completed(tasks):
                vol = task.result()
                if not vol:
                    continue
                self.created_volumes.append(vol)

        for volume in self.created_volumes:
            self.wait_volume_created(volume)
        return self.created_volumes

    @retry(exceptions=exceptions.EcsDoseNotHaveBlock,
           tries=60, delay=1, backoff=2, max_delay=10)
    def _guest_must_have_all_block(self, ecs_blocks):
        found = set(re.findall(r'NAME="([a-zA-Z/]+)"',
                               self.get_libvirt_guest().lsblk()))
        LOG.debug('found blocks: {}', found, ecs=self.ecs.id)
        if set(ecs_blocks) != set(found):
            raise exceptions.EcsDoseNotHaveBlock(self.ecs.id,
                                                 ecs_blocks - found)
        LOG.info('domain has all blocks {}', ecs_blocks, ecs=self.ecs.id)

    def guest_find_all_blocks(self) -> list[dict]:
        found = set(re.findall(REG_LSBLK, self.get_libvirt_guest().lsblk()))
        return [{'name': v[0], 'size': v[1], 'type': v[2]} for v in found]

    @retry(exceptions=exceptions.GuestBlockSizeNotExtend,
           tries=12, delay=1, backoff=2, max_delay=5)
    def guest_block_size_must_be(self, name, size):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        blocks = [blk for blk in self.guest_find_all_blocks()
                  if blk['name'] == name]
        if not blocks:
            raise exceptions.EcsDoseNotHaveBlock(self.ecs.id, name)
        if not blocks[0].get('size') == size:
            raise exceptions.GuestBlockSizeNotExtend(name, size=blocks[0],
                                                     new_size=size)
        LOG.info('block {} size is {}', name, blocks[0].get('size'),
                 ecs=self.ecs.id)

    @retry(exceptions=exceptions.EcsNotMatchOKConsoleLog,
           tries=CONF.ecs_test.console_log_timeout,
           delay=1, backoff=2, max_delay=5)
    def ecs_must_have_ok_console_log(self):
        if not CONF.ecs_test.enable_varify_console_log:
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

    @retry(exceptions=exceptions.EcsNameNotMatch,
           tries=10, delay=1, max_delay=6)
    def ecs_must_have_name(self, name):
        if not CONF.ecs_test.enable_guest_qga_command:
            return
        guest = self.get_libvirt_guest()
        hostname = guest.hostname()
        LOG.debug('guest hostname is {}', hostname, ecs=self.ecs.id)
        if hostname != name:
            raise exceptions.EcsNameNotMatch(self.ecs.id, name)
        LOG.info('guest hostname is "{}"', hostname, ecs=self.ecs.id)
