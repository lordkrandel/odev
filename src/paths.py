# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from hashlib import md5
from pathlib import Path
from functools import lru_cache

def ensure(path):
    path = Path(path)
    if path.exists():
        if path.is_dir():
            return False
        raise ValueError("Given path exists as a file")
    parts = path.parts
    if '.' in parts or '..' in parts:
        raise ValueError("Cannot use relative paths")
    Path.mkdir(path, parents=True, exist_ok=True)

@lru_cache
def digest(path):
    hasher = md5()
    hasher.update(str(path).encode())
    return hasher.hexdigest()

def parent_digests(path):
    for subpath in (path, *path.parents):
        yield digest(subpath)
