from skytest.common import log

LOG = log.getLogger()


class TearDownMethod:
    def __init__(self, func, *args, **kwargs) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        LOG.debug('run {} with args: {}, kwargs: {}',
                  self.func, self.args, self.kwargs)
        self.func(*self.args, **self.kwargs)

    def __str__(self):
        return f'{self.func}'


class TeaDownCollector(object):

    def __init__(self) -> None:
        self.tasks: list[TearDownMethod] = []

    def append(self, func, *args, **kwargs):
        self.tasks.append(TearDownMethod(func, *args, **kwargs))

    def run(self):
        LOG.info('==== Run Tear Down ====')
        for task in reversed(self.tasks):
            try:
                task.run()
            except Exception as e:
                LOG.warning('run {} failed: {}', task, e)
