# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from pathlib import Path
from repo import Repo
from json_mixin import JsonMixin


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
    ):
        self.name = name
        self.db_name = db_name
        self.repos = repos
        self.modules = modules
        self.db_dump_file = db_dump_file or f'{name}.dmp'
        self.post_hook_script = post_hook_script or 'post_hook.py'
        self.venv_path = venv_path or '.venv'
        self.rc_file = rc_file or '.odoorc'

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
            data.get('rc_file', ''))

    def to_json(self):
        data = self.__dict__.copy()
        for k, v in data.items():
            if k == 'repos':
                data[k] = {k2: v2.__dict__ for k2, v2 in v.items()}
            else:
                data[k] = v
        return json.dumps(data, indent=4)

    def set_current(self, project_path):
        """ Set the workspace as current """
        fullpath = Path(project_path) / 'last_used_workspace'
        with open(fullpath, "w", encoding="utf-8") as f:
            return f.write(self.name)
