from easy2use.common import exceptions as base_exc


class ConfileNotExists(base_exc.BaseException):
    _msg = 'conf file not exists'

class InvalidManager(base_exc.BaseException):
    _msg = 'Invalid manager {}'


class InterfaceDetachTimeout(base_exc.BaseException):
    _msg = 'vm {vm} interface detach timeout({timeout}s)'


class VolumeAttachTimeout(base_exc.BaseException):
    _msg = 'volume {volume} attach timeout({timeout}s'


class VolumeAttachtFailed(base_exc.BaseException):
    _msg = 'volume {volume} attach  failed'


class VolumeDetachTimeout(base_exc.BaseException):
    _msg = 'volume {volume} detach failed'


class VolumeCreateTimeout(base_exc.BaseException):
    _msg = 'volume {volume} create timeout({timeout}s)'


class VolumeCreateFailed(base_exc.BaseException):
    _msg = 'volume {volume} create failed'


class VmCreatedFailed(base_exc.BaseException):
    _msg = 'vm {vm} create failed'


class StopFailed(base_exc.BaseException):
    _msg = 'Stop {vm} failed, reason: {reason}'


class StartFailed(base_exc.BaseException):
    _msg = 'Start {vm} failed, reason: {reason}'


class SuspendFailed(base_exc.BaseException):
    _msg = 'suspend {vm} failed, reason: {reason}'


class ResumeFailed(base_exc.BaseException):
    _msg = 'resume {vm} failed, reason: {reason}'


class RebootFailed(base_exc.BaseException):
    _msg = 'Reboot {vm} failed, reason: {reason}'


class BootFailed(base_exc.BaseException):
    _msg = 'Boot {vm} failed, reason: {reason}'


class WaitVMStatusTimeout(base_exc.BaseException):
    _msg = 'wait {vm} status timeout, expect: {expect}, actual: {actual}'


class VMIsError(base_exc.BaseException):
    _msg = 'vm {vm} status is error'


class LoopTimeout(base_exc.BaseException):
    _msg = 'loop timeout({timeout}s)'


class VolumeDetachFailed(base_exc.BaseException):
    _msg = 'volume {volume} detach failed'


class ResizeFailed(base_exc.BaseException):
    _msg = 'resize {vm} failed, reason: {reason}'


class MigrateFailed(base_exc.BaseException):
    _msg = 'migrate {vm} failed, reason: {reason}'


class LiveMigrateFailed(base_exc.BaseException):
    _msg = 'live migrate {vm} failed, reason: {reason}'


class VMBackupFailed(base_exc.BaseException):
    _msg = 'backup {vm} failed, reason: {reason}'


class InvalidArgs(base_exc.BaseException):
    _msg = 'Invalid args, {reason}'


class VmTestActionNotFound(base_exc.BaseException):
    _msg = 'Vm test action not found: {action}'


class NotAvailableServices(base_exc.BaseException):
    _msg = 'Not available services, reason: {reason}'


class InvalidScenario(base_exc.BaseException):
    _msg = 'Invalid scenario "{}"'


class InvalidConfig(base_exc.BaseException):
    _msg = 'Invalid config, {reason}.'


class InvalidFlavor(base_exc.BaseException):
    _msg = 'Invalid flavor, {reason}.'


class InvalidImage(base_exc.BaseException):
    _msg = 'Invalid image, reason: {reason}.'


class VMTestFailed(base_exc.BaseException):
    _msg = 'vm {vm} {action} falied, {reason}.'
