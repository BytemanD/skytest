import abc

from easy2use.globals import cfg

from skytest.common import exceptions
from skytest.common import libvirt_guest
from skytest.common import log
from skytest.common import model

from .openstack.manager import OpenstackManager

CONF = cfg.CONF
LOG = log.getLogger()


class BaseManager(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def create_ecs(self, name=None, timeout=1800, wait=False) -> model.ECS:
        pass

    @abc.abstractmethod
    def delete_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def get_ecs(self, id) -> model.ECS:
        pass

    @abc.abstractmethod
    def stop_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def start_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def reboot_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def hard_reboot_ecs(self, ecs):
        pass

    @abc.abstractmethod
    def get_ecs_console_log(self, ecs: model.ECS) -> str:
        pass

    @abc.abstractmethod
    def attach_interface(self, ecs: model.ECS, port_ids):
        pass

    @abc.abstractmethod
    def attach_net(self, ecs: model.ECS, net_id):
        pass

    @abc.abstractmethod
    def detach_interface(self, ecs: model.ECS, vif: str):
        pass

    @abc.abstractmethod
    def attach_interfaces(self, ecs: model.ECS, net_id, num=1):
        pass

    @abc.abstractmethod
    def report_ecs_actions(self, ecs: model.ECS):
        pass

    # @abc.abstractmethod
    # def rebuild_ecs(self, ecs):
    #     pass

    def refresh_ecs(self, ecs: model.ECS):
        pass

    def get_ecs_interfaces(self, ecs: model.ECS) -> list:
        pass

    def get_ecs_ip_address(self, ecs: model.ECS) -> list:
        pass

    @abc.abstractmethod
    def get_host_ip(self, hostname) -> str:
        pass

    @abc.abstractmethod
    def get_libvirt_guest(self, ecs: model.ECS) -> libvirt_guest.LibvirtGuest:
        host_ip = self.get_host_ip(self.server.host)
        return libvirt_guest.LibvirtGuest(ecs.id, host=host_ip)


def get_manager():
    if CONF.manager == 'openstack':
        return OpenstackManager()
    raise exceptions.InvalidManager(CONF.manager)