# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from json_mixin import JsonMixin
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
    "repos": {:
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

    def __init__(self, projects=None, defaults=None, path=None):
        super().__init__()
        if path:
            self.path = path
        self.defaults = defaults or {
            "db_name": "odoodb",
            "worktree": False
        }
        self.update(projects or {})

    @classmethod
    def from_json(cls, data):
        projects = {k: Project.from_json(v) for k, v in data.items() if k not in ('path', "defaults")}
        defaults = data.get("defaults")
        path = data.get("path")
        return Projects(projects, defaults, path)

    def to_json(self):
        data = {k: v.__dict__ for k, v in self.items()}
        data['path'] = str(self.path)
        data['defaults'] = self.defaults
        return json.dumps(data, indent=4)

    @classmethod
    def load(cls, path):
        return Projects.load_json(path)

    def save(self):
        return self.save_json(self.path)
