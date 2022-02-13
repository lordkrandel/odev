#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import consts
from os import environ, mkdir, getcwd
from os.path import join, split, isdir, exists, abspath
from hashlib import sha256


class Paths():

    def __init__(self, parent):
        config_home = environ.get('APPDATA') or environ.get('XDG_CONFIG_HOME') or join(environ['HOME'], '.config')
        self._config = join(config_home, consts.APPNAME)
        self._parent = parent

    @property
    def config(self):
        return self._config

    @property
    def current(self):
        return abspath(getcwd())

    @property
    def log(self):
        return join(self.config, f"{consts.APPNAME}.log")

    @property
    def projects(self):
        return join(self.config, 'projects.json')

    @property
    def project(self):
        return self._parent.project

    @property
    def workspaces(self):
        return join(self.config, 'workspaces', self._parent.project.name)

    @property
    def workspace(self):
        return self.build_workspace_path(self._parent.workspace.name)

    @property
    def workspace_file(self):
        return self.build_workspace_file_path(self._parent.workspace.name)

    def build_workspace_path(self, name):
        return join(self.workspaces, name)

    def build_workspace_file_path(self, name=None):
        return join(self.workspaces, name, f"{name}.json")

    @property
    def rc_file(self):
        return self.relative(self._parent.workspace.rc_file)

    @property
    def venv_path(self):
        return self.relative(self._parent.workspace.venv_path)

    @property
    def db_dump_file(self):
        return join(self.workspace, self._parent.workspace.db_dump_file)

    @property
    def post_hook_script(self):
        return join(self.workspace, self._parent.workspace.post_hook_script)

    @property
    def current_digest(self):
        return self.digest(self.current)

    def relative(self, subpath):
        return join(self._parent.project.path, subpath)

    @classmethod
    def touch(cls, path):
        base, _ = split(path)
        Paths.ensure(base)
        if not exists(path):
            open(path, 'a', encoding='utf-8').close()

    @classmethod
    def digest(cls, path):
        hasher = sha256()
        hasher.update(path.encode())
        return hasher.hexdigest()

    @classmethod
    def ensure(cls, path):
        if isdir(path):
            return False

        parts = []
        while path and path != '/':
            path, end = split(path)
            if end in ('.', '..'):
                raise ValueError("Cannot use relative paths")
            parts.insert(0, end)

        path = '/'
        for folder in parts:
            path = join(path, folder)
            if exists(path):
                if not isdir(path):
                    raise ValueError("Path targets an existing file, not a folder")
            else:
                mkdir(path)

        return True
