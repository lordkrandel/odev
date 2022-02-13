# -*- coding: utf-8 -*-

import logging
from git import Git
from os import listdir
from sys import stdout
from workspace import Workspace
from project import Projects

from consts import APPNAME
from paths import Paths
from typer import Typer


class Odev(Typer):

    def __init__(self):
        super().__init__()
        self.paths = Paths(self)
        self.paths.ensure(self.paths.config)
        self.logger = self._setup_logger()
        self.projects = Projects.load_json(self.paths.projects)

        try:
            self.projects.select(self.paths.current_digest)
        except ValueError as e:
            e.message = self.paths.current_digest
            raise e

        self.select_workspace(self.last_used)
        self.editor = Git.get_editor()

    def _setup_logger(self):
        self.paths.touch(self.paths.log)
        logging.basicConfig(
            filename=self.paths.log,
            level=logging.INFO,
            format='[%(asctime)s] %(name)-20s %(levelname)-7s %(message)s')
        logger = logging.getLogger(APPNAME)
        stream_handler = logging.StreamHandler(stdout)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(filename)s.%(funcName)s:%(lineno)d] %(message)s',
            datefmt='%d/%m/%Y %H:%M:%S')
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        return logger

    def select_workspace(self, workspace_name):
        workspace_name = workspace_name or self.last_used
        workspace_file_path = self.paths.build_workspace_file_path(workspace_name)
        self._workspace = Workspace.load_json(workspace_file_path)

    @property
    def project(self):
        return self.projects.selected

    @property
    def workspace(self):
        return self._workspace

    @property
    def last_used(self):
        return self.project.last_used

    @last_used.setter
    def last_used(self, new_last_used):
        self.project.last_used = new_last_used
        self.projects.save_json(self.paths.projects)

    @property
    def workspace_names(self):
        return self.project and sorted(listdir(self.paths.workspaces)) or []


odev = Odev()
