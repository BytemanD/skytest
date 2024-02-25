import abc

from skytest.common import exceptions
from skytest.common import conf
from skytest.common import libvirt_guest
from skytest.common import log
from skytest.common import model

from .openstack.manager import OpenstackManager

CONF = conf.CONF
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
    def get_ecs_console_log(self, ecs: model.ECS, length=None) -> str:
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
    def attach_volume(self, ecs: model.ECS, volume_id: str):
        pass

    @abc.abstractmethod
    def detach_volume(self, ecs: model.ECS, volume_id: str):
        pass

    @abc.abstractmethod
    def report_ecs_actions(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def rebuild_ecs(self, ecs):
        pass

    @abc.abstractmethod
    def resize_ecs(self, ecs: model.ECS, flavor):
        pass

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
        pass

    @abc.abstractmethod
    def create_volume(self, size_gb=None, name=None, image=None,
                      snapshot=None, volume_type=None) -> model.Volume:
        pass

    @abc.abstractmethod
    def get_volume(self, volume_id) -> model.Volume:
        pass

    @abc.abstractmethod
    def delete_volume(self, volume: model.Volume):
        pass

    @abc.abstractmethod
    def get_ecs_volumes(self, ecs: model.ECS) -> list[model.VolumeAttachment]:
        pass

    @abc.abstractmethod
    def get_ecs_blocks(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def live_migrate_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def migrate_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def rename_ecs(self, ecs: model.ECS, name):
        pass

    @abc.abstractmethod
    def shelve_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def unshelve_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def pause_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def unpause_ecs(self, ecs: model.ECS):
        pass

    @abc.abstractmethod
    def extend_volume(self, volume: model.Volume, new_size):
        pass

    @abc.abstractmethod
    def get_flavor(self, id_or_name):
        pass

    @abc.abstractmethod
    def get_flavor_id(self, flavor):
        pass

    @abc.abstractmethod
    def get_image(self, id_or_name):
        pass

    @abc.abstractmethod
    def get_available_services(host=None, zone=None, binary=None):
        pass

    def must_support_action(self, ecs: model.ECS, action):
        pass

    @abc.abstractmethod
    def get_ecs_flavor_id(self, ecs: model.ECS):
        pass


def get_manager():
    if CONF.manager == 'openstack':
        return OpenstackManager()
    raise exceptions.InvalidManager(CONF.manager)
