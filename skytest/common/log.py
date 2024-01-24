import logging
import os
import sys

from loguru import logger
from easy2use.globals import log as root_loger


TIME_FORMAT_DEFAULT = 'YYYY-MM-DD HH:mm:ss'

LOG_FOAMAT_DEFAULT = f'{{time:{TIME_FORMAT_DEFAULT}}} ' \
                     '{process} <level>{level:7}</level> ' \
                     '<level>[vm: {extra[vm]}] {message}</level>'
LOG_FORMAT_FILE = f'{{time:{TIME_FORMAT_DEFAULT}}} ' \
                  '{process} {level:7} [vm: {extra[vm]}] {message}'

LOG = logger.bind(vm='-')


def basic_config(verbose_count=0, log_file=None):
    global LOG

    logger.configure(handlers=[{
        "sink": log_file or sys.stdout,
        'format': log_file and LOG_FORMAT_FILE or LOG_FOAMAT_DEFAULT,
        "colorize": True,
        "level": "DEBUG" if verbose_count >= 1 else "INFO",
    }])
    if verbose_count >= 2:
        root_loger.basic_config(
            level=logging.DEBUG,
            filename=log_file and os.path.abspath(log_file))


def getLogger():
    return LOG
