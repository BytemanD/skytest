import json
import time
import base64
import time
import contextlib
import pathlib

import libvirt
import libvirt_qemu

from skytest.common import log
from skytest.common import utils
from skytest.common import exceptions

LOG = log.getLogger()

VIR_DOMAIN_NOSTATE = 0
VIR_DOMAIN_RUNNING = 1
VIR_DOMAIN_BLOCKED = 2
VIR_DOMAIN_PAUSED = 3
VIR_DOMAIN_SHUTDOWN = 4
VIR_DOMAIN_SHUTOFF = 5
VIR_DOMAIN_CRASHED = 6
VIR_DOMAIN_PMSUSPENDED = 7

LIBVIRT_POWER_STATE = {
    VIR_DOMAIN_NOSTATE: 'NOSTATE',
    VIR_DOMAIN_RUNNING: 'RUNNING',
    VIR_DOMAIN_BLOCKED: 'RUNNING',
    VIR_DOMAIN_PAUSED: 'PAUSED',
    VIR_DOMAIN_SHUTDOWN: 'SHUTDOWN',
    VIR_DOMAIN_SHUTOFF: 'SHUTDOWN',
    VIR_DOMAIN_CRASHED: 'CRASHED',
    VIR_DOMAIN_PMSUSPENDED: 'SUSPENDED',
}

class DomainNotFound(Exception):
    def __init__(self, name):
        super().__init__(f'Domain {name} not found.')


class LibvirtGuest(object):

    def __init__(self, domain, host=None):
        self.host = host or 'localhost'
        self.name_or_id = domain
        self._domain = None
        self._connect = None

    @property
    def connect(self):
        if not self._connect:
            self._connect = libvirt.open(f'qemu+tcp://{self.host}/system')
        return self._connect

    def _lookup_domain(self):
        if self._domain:
            return
        LOG.debug('look up domain {}', self.name_or_id)
        lookup_funcs = [self.connect.lookupByName]
        if utils.is_uuid(self.name_or_id):
            lookup_funcs.insert(0, self.connect.lookupByUUIDString)

        for func in [self.connect.lookupByName,
                     self.connect.lookupByUUIDString]:
            try:
                self._domain = func(self.name_or_id)
                break
            except libvirt.libvirtError as e:
                if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
                    raise

    @property
    def domain(self):
        self._lookup_domain()
        if not self._domain:
            raise DomainNotFound(self.name_or_id)
        return self._domain

    @property
    def uuid(self):
        return self.domain.UUIDString()

    def _get_agent_exec_cmd(self, cmd):
        """
        param: cmd   list or str
        """
        cmd_list = isinstance(cmd, str) and cmd.split() or cmd
        if not cmd_list:
            raise ValueError('Cmd is empty')
        cmd_obj = {'execute': 'guest-exec',
                   'arguments': {'capture-output': True,
                                 'path': cmd_list[0], 'arg': cmd_list[1:]}}
        return json.dumps(cmd_obj)

    def _get_agent_exec_status_cmd(self, pid):
        return json.dumps(
            {'execute': 'guest-exec-status', 'arguments': {'pid': pid}})

    def guest_exec(self, cmd, wait_exists=True, timeout=60):
        exec_cmd = self._get_agent_exec_cmd(cmd)
        result = libvirt_qemu.qemuAgentCommand(self.domain, exec_cmd,
                                               timeout, 0)
        result_obj = json.loads(result)
        cmd_pid = result_obj.get('return', {}).get('pid')
        LOG.debug('RUN: {} => PID: {}', cmd, cmd_pid,
                  vm=self.domain.UUIDString())

        if not cmd_pid:
            raise RuntimeError('guest-exec pid is none')
        return (
            self.guest_exec_status(cmd_pid, wait_exists=wait_exists,
                                   timeout=timeout)
            if wait_exists else cmd_pid
        )

    def guest_exec_status(self, pid, wait_exists=False, timeout=None):
        cmd_obj = self._get_agent_exec_status_cmd(pid)
        result_obj = {}
        start_timeout = time.time()
        while True:
            LOG.debug('waiting for {}', pid)
            result = libvirt_qemu.qemuAgentCommand(self.domain, cmd_obj,
                                                   timeout, 0)
            result_obj = json.loads(result)
            if not wait_exists or result_obj.get('return', {}).get('exited'):
                break
            if timeout and (time.time() - start_timeout) >= timeout:
                raise RuntimeError(f'Waiting for {pid} timeout')
            time.sleep(1)
        out_data = result_obj.get('return', {}).get('out-data')
        err_data = result_obj.get('return', {}).get('err-data')
        out_decode = out_data and base64.b64decode(out_data)
        err_decode = err_data and base64.b64decode(err_data)

        if isinstance(out_decode, bytes):
            out_decode = out_decode.decode()
        if isinstance(err_decode, bytes):
            err_decode = err_decode.decode()
        LOG.debug('PID: {} => OUTPUT: {}', pid, out_decode,
                  vm=self.domain.UUIDString())
        return out_decode or err_decode

    def rpm_i(self, rpm_file):
        if rpm_file:
            self.guest_exec(['/usr/bin/rpm','-ivh', rpm_file])

    def is_ip_exists(self, ipaddress):
        result = self.ip_a()
        return f'inet {ipaddress}/' in result

    def hostname(self):
        return self.guest_exec(['/usr/bin/hostname'])

    def whereis_cmd(self, cmd):
        result = self.guest_exec(['/usr/bin/whereis', cmd])
        return result and result.split()[1] or None

    def kill(self, pid, signal=9):
        self.guest_exec(['/usr/bin/kill', str(signal), str(pid)])

    def start_iperf_server(self, iperf_cmd, logfile):
        return self.guest_exec(
            [iperf_cmd, '--format', 'K', '-s', '--logfile', logfile],
            wait_exists=False)

    def start_iperf_client(self, iperf_cmd, target, timeout=60 * 5):
        return self.guest_exec(
            [iperf_cmd, '--format', 'k', '-c', target],
            wait_exists=True, timeout=timeout)

    @contextlib.contextmanager
    def open_iperf3_server(self, iperf_cmd, logfile):
        server_pid = self.guest_exec(
            [iperf_cmd, '--format', 'k', '-s', '--logfile', logfile],
            wait_exists=False)

        yield server_pid

        self.kill(server_pid)

    def update_device(self, xml, persistent=False, live=False):
        """Update guest device

        Args:
            xml (Path or str): device xml
            persistent (bool, optional): persistent. Defaults to False.
            live (bool, optional): live. Defaults to False.
        """
        flags = persistent and libvirt.VIR_DOMAIN_AFFECT_CONFIG or 0
        flags |= live and libvirt.VIR_DOMAIN_AFFECT_LIVE or 0

        if isinstance(xml, pathlib.Path):
            with xml.open() as f:
                device_xml = ''.join(f.readlines())
        else:
            device_xml = xml
        self.domain.updateDeviceFlags(device_xml, flags=flags)

    def is_exists(self):
        try:
            self.uuid
        except DomainNotFound:
            return False
        return True

    def info(self):
        dom_info = self.domain.info()
        return {'state': LIBVIRT_POWER_STATE.get(dom_info[0]),
                'max_mem_kb': dom_info[1],
                'mem_kb': dom_info[2], 'num_cpu': dom_info[3],
                'cpu_time_ns': dom_info[4]}

    def ip_a(self):
        return self.guest_exec(['/sbin/ip', 'a'])
