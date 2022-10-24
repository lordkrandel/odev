# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import consts
from hashlib import md5
from pathlib import Path


def config():
    return Path.home() / '.config' / consts.APPNAME

def current():
    return Path.cwd().absolute()

def digest(path):
    hasher = md5()
    hasher.update(str(path).encode())
    return hasher.hexdigest()

def current_digest():
    return digest(current())

def projects():
    return config() / 'projects.json'

def workspaces():
    return config() / 'workspaces' / current_digest()

def workspace(name):
    return workspaces() / name

def workspace_file(name):
    return workspace(name) / f"{name}.json"

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
