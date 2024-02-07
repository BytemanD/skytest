from dataclasses import dataclass


@dataclass
class ECS:
    id: str
    name: str = ''
    status: str = ''
    task_state: str = ''
    host: str = ''
    progress: int = None

    def is_active(self):
        return self.status.upper() == 'ACTIVE'

    def is_stopped(self):
        return self.status.upper() == 'STOPPED'

    def is_paused(self):
        return self.status.upper() == 'PAUSED'

    def is_error(self):
        return self.status.upper() == 'ERROR'

    def is_building(self):
        return self.status.upper() == 'BUILDING'

    def is_shelved(self):
        return self.status.upper() == 'SHELVED_OFFLOADED'

    def has_task(self):
        return not not self.task_state


@dataclass
class Volume:
    id: str
    size: int
    name: str = ''
    status: str = ''

    def is_error(self):
        return self.status.upper() == 'ERROR'

    def is_inuse(self):
        return self.status.upper().replace('-', '_') == 'IN_USE'

    def is_creating(self):
        return self.status.upper() == 'CREATING'

    def is_available(self):
        return self.status.upper() == 'AVAILABLE'


@dataclass
class VolumeAttachment:
    id: str
    volumeId: str = ''
    device: str = ''
