import typer

import consts
from merge_cache import MergeCache
from pathlib import Path
from paths import digest, parent_digests
from project import Projects



class Odev(typer.Typer):

    def __init__(self, *args, **kwargs):
        super(Odev, self).__init__(*args, **kwargs)
        self.workspace = None
        self.repo = None

        self.setup_fixed_paths()
        self.projects = Projects.load(self.paths.projects)
        self.projects.save()
        if self.setup_current_project():
            self.setup_variable_paths()
            self.merge_cache = MergeCache.load_json(self.paths.cache)
            self.reload_workspaces()

        self.db = self._subcommand("db", help="Manage Odoo database")
        self.path = self._subcommand("path", help="Get paths info")
        self.git = self._subcommand("git", help="Git operations on all repos")
        self.workspace = self._subcommand("workspace", help="Workspace operations")
        self.slot = self._subcommand("slot", help="Manage save slots")
        self.odoo = self._subcommand("odoo", help="Odoo operations")

    def _subcommand(self, name, **kwargs):
        subcommand = typer.Typer(no_args_is_help=True)
        self.add_typer(subcommand, name=name, **kwargs)
        return subcommand

    def reload_workspaces(self):
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
        self.paths.repo = lambda repo_name: self.paths.relative(repo_name)
        self.paths.workspaces = self.paths.config / 'workspaces' / digest(self.paths.project)
        self.paths.cache = self.paths.workspaces / "cache.json"
        self.paths.workspace = lambda name: self.paths.workspaces / name
        self.paths.workspace_file = lambda name: self.paths.workspace(name) / f"{name}.json"
        self.paths.hook_file = lambda name: self.paths.workspace(name) / "post_hook.py"


odev = Odev(rich_markup_mode=False)
