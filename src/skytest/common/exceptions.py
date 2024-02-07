from easy2use.common import exceptions as base_exc


class ConfileNotExists(base_exc.BaseException):
    _msg = 'conf file not exists {files}'


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
    _msg = 'Config is invalid because {reason}.'


class InvalidFlavor(base_exc.BaseException):
    _msg = 'Invalid flavor, {reason}.'


class InvalidImage(base_exc.BaseException):
    _msg = 'Invalid image, reason: {reason}.'


class EcsTestFailed(base_exc.BaseException):
    _msg = 'ecs {ecs} {action} falied, {reason}.'


class GuestDomainIpaddressNotExists(base_exc.BaseException):
    _msg = 'ipaddress {} not exsits on guest domain.'


class GuestnIpaddressNotExists(base_exc.BaseException):
    _msg = 'ipaddress {} not exsits on guest domain.'


class HypervisorNotFound(base_exc.BaseException):
    _msg = 'hypervisor {} not found.'


class ECSNotFound(base_exc.BaseException):
    _msg = 'ECS {} not found.'


class NotFound(base_exc.BaseException):
    _msg = 'not found error: {}'


class TestFailed(base_exc.BaseException):
    _msg = 'test failed'


class SkipActionException(base_exc.BaseException):
    _msg = 'skip this action because {}'


class ActionNotSuppport(base_exc.BaseException):
    _msg = 'action {} not supported({reason})'


class EcsIsNotCreated(base_exc.BaseException):
    _msg = 'ECS {} still not created'


class EcsIsNotDeleted(base_exc.BaseException):
    _msg = 'ECS {} still not deleted'


class EcsHasTask(base_exc.BaseException):
    _msg = 'ECS {} still has task'


class VolumeIsNotAvailable(base_exc.BaseException):
    _msg = 'Volume {} is not available'


class VolumeIsNotInuse(base_exc.BaseException):
    _msg = 'Volume {} is not inuse'


class VolumeIsError(base_exc.BaseException):
    _msg = 'Volume {} is error'


class VolumeIsNotDeleted(base_exc.BaseException):
    _msg = 'Volume {} is still not deleted'


class VolumeIsNotAvailable(base_exc.BaseException):
    _msg = 'Volume {} is still not available'


class VolumeNotFound(base_exc.BaseException):
    _msg = 'Volume {} not found.'


class EcsDoseNotHaveIpAddress(base_exc.BaseException):
    _msg = 'ecs {} does not ip address {}.'


class EcsDoseNotHaveBlock(base_exc.BaseException):
    _msg = 'ecs {} does not block {}.'


class GuestBlockSizeNotExtend(base_exc.BaseException):
    _msg = 'Block {} is {size} not {new_size}'


class EcsCloudAPIError(base_exc.BaseException):
    _msg = 'cloud api error: {}.'


class EcsNotMatchOKConsoleLog(base_exc.BaseException):
    _msg = '{} not matched ok console log'


class EcsMatchErrorConsoleLog(base_exc.BaseException):
    _msg = '{} matched error error console log'


class EcsNameNotMatch(base_exc.BaseException):
    _msg = 'ecs {} is not "{}"'
