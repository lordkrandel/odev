#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import consts
from pathlib import Path
from paths import digest, parent_digests
from project import Projects
from typer import Typer

class Odev(Typer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup_fixed_paths()
        self.projects = Projects.load_json(self.paths.projects)
        self.projects.path = self.paths.projects
        self.projects.save()
        if not self.setup_current_project():
            raise RuntimeError("Current path is not in a project. Please create one.")
        self.worktree = self.projects.defaults['worktree']
        self.setup_variable_paths()
        self.workspaces = sorted([x.name for x in self.paths.workspaces.iterdir()])

    def setup_fixed_paths(self):
        class Paths():
            pass
        self.paths = Paths()
        self.paths.config = Path.home() / '.config' / consts.APPNAME
        self.paths.starting = Path.cwd().absolute()
        self.paths.projects = self.paths.config / 'projects.json'
        return self.paths

    def setup_current_project(self):
        self.project = None
        for digest in parent_digests(self.paths.starting):
            if digest in self.projects:
                self.project = self.projects.get(digest)
                break
        return self.project

    def setup_variable_paths(self):
        self.paths.project = Path(self.project.path)
        self.paths.workspaces = self.paths.config / 'workspaces' / digest(self.paths.project)
        self.paths.workspace = lambda name: self.paths.workspaces / name
        self.paths.workspace_file = lambda name: self.paths.workspace(name) / Path(f"{name}.json")


odev = Odev()
