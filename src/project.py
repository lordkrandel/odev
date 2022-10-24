# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from json_mixin import JsonMixin
import paths
from pathlib import Path


TEMPLATE = """{
    "name": "master",
    "db_name": "{{db_name}}",
    "db_dump_file": "master.dmp",
    "modules": [
        "base"
    ],
    "post_hook_script": "post_hook.py",
    "venv_path": ".venv",
    "rc_file": ".odoorc",
    "repos": {
        "odoo": {
            "name": "odoo",
            "dev": "git@github.com:odoo-dev/odoo",
            "origin": "git@github.com:odoo/odoo",
            "remote": "origin",
            "branch": "master",
            "addons_folders": ["./addons"]
        },
        "enterprise": {
            "name": "enterprise",
            "dev": "git@github.com:odoo-dev/enterprise",
            "origin": "git@github.com:odoo/enterprise",
            "remote": "origin",
            "branch": "master",
            "addons_folders": ["."]
        }
    }
}"""


class Project(JsonMixin):

    def __init__(self, name, path, last_used):
        self.name = name
        self.path = path
        self.last_used = last_used

    @classmethod
    def from_json(cls, data):
        return Project(data.get('name'),
                       str(data.get('path')),
                       data.get('last_used'))

    def to_json(self):
        data = {'name': self.name,
                'path': str(self.path),
                'last_used': self.last_used}
        return json.dumps(data, indent=4)

    def relative(self, path):
        return Path(self.path) / path


class Projects(JsonMixin, dict):

    def __init__(self, projects=None):
        super().__init__()
        self.update(projects or {})

    @classmethod
    def from_json(cls, data):
        return Projects({k: Project.from_json(v) for k, v in data.items()})

    def to_json(self):
        data = {k: v.__dict__ for k, v in self.items()}
        return json.dumps(data, indent=4)

    @classmethod
    def load(cls):
        return Projects.load_json(paths.projects())

    def save(self):
        return self.save_json(paths.projects())

    @classmethod
    def delete_project(cls, project_name):
        projects = Projects.load()
        if project_name not in projects:
            raise ValueError(f"{project_name} is not a valid project")
        projects.pop(project_name)
        projects.save_json(paths.projects())

    @classmethod
    def create_project(cls, path, digest, db_name="odoodb"):
        """
            Create a new project, path, and its 'master' workspace.
        """
        projects = Projects.load()
        project = Project(digest, str(path), "master")
        projects[digest] = project
        projects.save_json(paths.projects())

        project_path = paths.config() / "workspaces" / digest
        if not project_path.is_dir():
            paths.ensure(project_path)
        master_path = project_path / "master"

        if not master_path.is_dir():
            paths.ensure(master_path)

        master_fullpath = master_path / "master.json"
        if not master_fullpath.exists():
            with open(master_fullpath, "w", encoding="utf-8") as f:
                f.write(TEMPLATE.replace("{{db_name}}", db_name))

        return project
