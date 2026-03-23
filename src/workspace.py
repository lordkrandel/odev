# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from pathlib import Path
from repo import Repo
from json_mixin import JsonMixin
from templates import addons_path, upgrade_path


class Workspace(JsonMixin):

    def __init__(
        self,
        name,
        db_name,
        repos,
        modules,
        db_dump_file=None,
        post_hook_script=None,
        venv_path=None,
        rc_file=None,
        extra_config=None,
    ):
        self.name = name
        self.db_name = db_name
        self.repos = repos
        self.modules = modules
        self.db_dump_file = db_dump_file or f'{name}.dmp'
        self.post_hook_script = post_hook_script or 'post_hook.py'
        self.venv_path = venv_path or '.venv'
        self.rc_file = rc_file or '.odoorc'
        self.extra_config = extra_config or {}
        self.path = None

    @property
    def addons_path(self):
        return {
            Path(repo_name) / path
            for repo_name in self.repos
            for path in addons_path.get(repo_name, [])
        }

    def set_path(self, path):
        self.path = str(path)
        for repo_name in self.repos:
            self.repos[repo_name].path = str(Path(self.path) / repo_name)

    @property
    def upgrade_path(self):
        return {
            Path(repo_name) / path
            for repo_name in self.repos
            for path in upgrade_path.get(repo_name, [])
        }

    @classmethod
    def from_json(cls, data):
        repos = {}
        for repo_name, repo in data.get('repos', {}).items():
            repos[repo_name] = Repo.from_json(repo)

        return Workspace(
            data.get('name', ''),
            data.get('db_name', ''),
            repos,
            data.get('modules', ''),
            data.get('db_dump_file', ''),
            data.get('post_hook_script', ''),
            data.get('venv_path', ''),
            data.get('rc_file', ''),
            data.get('extra_config', ''),
        )

    def to_json_excluded(self):
        return ['path'] + super().to_json_excluded()

    def set_current(self, project_path):
        """ Set the workspace as current """
        fullpath = Path(project_path) / 'last_used_workspace'
        with open(fullpath, "w", encoding="utf-8") as f:
            return f.write(self.name)
