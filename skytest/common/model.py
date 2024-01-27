from dataclasses import dataclass


@dataclass
class ECS:

    id: str
    name: str = ''
    status: str = ''
    task_state: str = ''
    host: str = ''

    def is_active(self):
        return self.status.upper() == 'ACTIVE'

    def is_stopped(self):
        return self.status.upper() == 'STOPPED'

    def is_paused(self):
        return self.status.upper() == 'PAUSED'

    def is_error(self):
        return self.status.upper() == 'ERROR'

    def has_task(self):
        return not not self.task_state
