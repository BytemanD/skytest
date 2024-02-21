from easy2use.common import exceptions as base_exc


class ConfileNotExists(base_exc.BaseException):
    _msg = 'conf file not exists {files}'


class InvalidManager(base_exc.BaseException):
    _msg = 'Invalid manager {}'


class EcsIsError(base_exc.BaseException):
    _msg = 'vm {} status is error'


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


class VolumeIsNotAvailable(base_exc.BaseException):
    _msg = 'Volume {} is not available'


class VolumeIsError(base_exc.BaseException):
    _msg = 'Volume {} is error'


class VolumeIsNotDeleted(base_exc.BaseException):
    _msg = 'Volume {} is still not deleted'


class EcsNotMigrated(base_exc.BaseException):
    _msg = 'ecs {} is not migrated'


class VolumeNotFound(base_exc.BaseException):
    _msg = 'Volume {} not found.'


class EcsCloudAPIError(base_exc.BaseException):
    _msg = 'cloud api error: {}.'


class EcsNotMatchOKConsoleLog(base_exc.BaseException):
    _msg = '{} not matched ok console log'


class EcsMatchErrorConsoleLog(base_exc.BaseException):
    _msg = '{} matched error error console log'


class EcsGuestIsExists(base_exc.BaseException):
    _msg = 'ecs {} guest is still exists'
