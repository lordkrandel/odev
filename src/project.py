# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import os
from json_mixin import JsonMixin
from paths import Paths


TEMPLATE = """{
    "name": "master",
    "db_name": "odoodb",
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
            "branch": "master"
        },
        "enterprise": {
            "name": "enterprise",
            "dev": "git@github.com:odoo-dev/enterprise",
            "origin": "git@github.com:odoo/enterprise",
            "remote": "origin",
            "branch": "master"
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
                       data.get('path'),
                       data.get('last_used'))

    def to_json(self):
        data = {'name': self.name,
                'path': self.path,
                'last_used': self.last_used}
        return json.dumps(data, indent=4)


class Projects(JsonMixin, dict):

    def __init__(self, projects):
        super().__init__()
        self.update(projects)
        self._selected = {}

    @classmethod
    def from_json(cls, data):
        return Projects({k: Project.from_json(v) for k, v in data.items()})

    def to_json(self):
        data = {k: v.__dict__ for k, v in self.items()}
        return json.dumps(data, indent=4)

    @property
    def selected(self):
        return self.get(self._selected, {})

    def select(self, project_name):
        if project_name not in self:
            raise ValueError("Current folder does not belong to a project.")
        self._selected = project_name


def create_project(digest):
    paths = Paths(None)
    projects = Projects.load_json(paths.projects)
    projects[digest] = Project(digest, paths.current, "master")
    projects.save_json(paths.projects)
    project_dir = os.path.join(paths.config, "workspaces", digest)
    if not os.path.isdir(project_dir):
        os.mkdir(project_dir)
    master_dir = os.path.join(project_dir, "master")
    if not os.path.isdir(master_dir):
        os.mkdir(master_dir)
    master_file = os.path.join(master_dir, "master.json")
    if not os.path.exists(master_file):
        with open(master_file, "w", encoding="utf-8") as f:
            f.write(TEMPLATE)
