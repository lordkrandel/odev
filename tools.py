# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import os
import logging

_logger = logging.getLogger(__name__)


def ensure_path(path):
    """ Ensure that the path exists.
        :path:  Path to be ensured. It cannot contain . or ..
    """

    if os.path.isdir(path):
        return 'exists'

    split = []
    while path and path != '/':
        path, end = os.path.split(path)
        if end in ('.', '..'):
            raise ValueError("Cannot use paths with '.' or '..' inside")
        split.insert(0, end)

    path = '/'
    for folder in split:
        path = os.path.join(path, folder)
        if os.path.exists(path):
            if not os.path.isdir(path):
                raise ValueError("Path targets an existing file, not a folder")
        else:
            _logger.info('Creating folder %s', path)
            os.mkdir(path)

    return 'created'


def init_path(path):
    return ensure_path(path) == 'created' and not any(os.scandir(path))
