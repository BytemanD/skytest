from concurrent import futures
import functools
import json
import os
import time
import pathlib
import re

from easy2use import date
from skytest.common import exceptions
from skytest.common import log

LOG = log.getLogger()


def wait_user_input(prompt, valid_values, invalid_help):
    user_input = input(prompt)
    while user_input not in valid_values:
        user_input = input(invalid_help)

    return user_input


def load_env(env_file):
    if not env_file or not pathlib.Path(env_file).is_file():
        raise exceptions.InvalidConfig(
            reason='env file is not set or not exists')

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.strip().startswith('#'):
                continue
            env = line.split()[-1]
            if not env:
                continue
            k, v = env.split('=')
            os.environ[k] = v


# TODO: move this to easy2use
def echo(message=None, list_join: str = None):
    if isinstance(message, bytes):
        print(message.decode())
        return
    if isinstance(message, list) and list_join:
        print(list_join.join(message))
        return
    if isinstance(message, dict):
        print(json.dumps(message, indent=True))

    print(message or '')


def do_times(options=None):
    def wrapper(func):
        @functools.wraps(func)
        def wrapper_func(*args, **kwargs):
            run_times, run_interval = (options.times, options.interval) \
                if options else (1, 1)
            LOG.info('do %s %s time(s)', func.__name__, run_times)
            for i in range(run_times):
                LOG.debug('do %s %s', func.__name__, i + 1)
                result = func(*args, **kwargs)
                time.sleep(run_interval)
            return result

        return wrapper_func

    return wrapper


# TODO: move this to easy2use
def run_processes(func, maps=None, max_workers=1, nums=None):
    with futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        if maps:
            tasks = executor.map(func, maps)
        elif nums:
            tasks = [executor.submit(func) for _ in range(nums)]
        for future in futures.as_completed(tasks):
            yield future.result()


def generate_name(resource):
    return 'skytest-{}-{}'.format(resource,
                                  date.now_str(date_fmt='%m%d-%H:%M:%S'))


def is_uuid(text):
    import uuid
    try:
        uuid.UUID(text)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def report_results(total, ng):
    if ng > 0:
        log_func = LOG.error
    else:
        log_func = LOG.success

    log_func('Total: {}, OK: {}, NG: {}', total, total - ng, ng)


def count_repeat_words(words: list) -> list:
    repeat_list = []
    for word in words:
        if repeat_list and word == repeat_list[-1]['word']:
            repeat_list[-1]['count'] += 1
        else:
            repeat_list.append({'word': word, 'count': 1})
    return repeat_list


def is_uint(value: str):
    return re.match(r'[0-9]+', value) is not None


class CircularQueue(object):

    def __init__(self, items: list, current=None) -> None:
        self.items = items or []
        self.index = self.items.index(current) if current else 0

    def length(self):
        return len(self.items)

    def __next__(self, ):
        if not self.items:
            return None
        if self.index >= len(self.items) - 1:
            self.index = 0
        else:
            self.index += 1
        return self.current()

    def current(self):
        return self.items[self.index]

    def __len__(self):
        return len(self.items)

    def is_empty(self):
        return self.length() <= 0
