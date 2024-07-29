# Part of Odoo. See LICENSE file for full copyright and licensing details.

import consts
from pathlib import Path
from paths import digest, parent_digests
from project import Projects
from typer import Typer


class Odev(Typer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = None
        self.repo = None

        self.setup_fixed_paths()
        self.projects = Projects.load(self.paths.projects)
        self.projects.save()
        if self.setup_current_project():
            self.setup_variable_paths()
            self.workspaces = sorted([x.name for x in self.paths.workspaces.iterdir()])

    def setup_fixed_paths(self):
        class Paths:
            pass
        self.paths = Paths()
        self.paths.config = Path.home() / '.config' / consts.APPNAME
        self.paths.starting = Path.cwd().absolute()
        self.paths.projects = self.paths.config / 'projects.json'
        return self.paths

    def setup_current_project(self):
        self.project = None
        for parent_digest in parent_digests(self.paths.starting):
            if parent_digest in self.projects:
                self.project = self.projects.get(parent_digest)
                break
        return self.project

    def setup_variable_paths(self):
        self.paths.project = Path(self.project.path)
        self.paths.relative = lambda x: self.paths.project / x
        self.paths.repo = lambda repo: self.paths.relative(repo.name)
        self.paths.workspaces = self.paths.config / 'workspaces' / digest(self.paths.project)
        self.paths.workspace = lambda name: self.paths.workspaces / name
        self.paths.workspace_file = lambda name: self.paths.workspace(name) / Path(f"{name}.json")
        self.paths.hook_file = lambda name: self.paths.workspace(name) / Path("post_hook.py")

odev = Odev()
