import json
from paths import ensure
from pathlib import Path
from workspace import Workspace
from templates import main_repos, template_repos
from json_mixin import JsonMixin


def create_template(name, db_name):
    return Workspace(
        name=name,
        db_name=db_name,
        repos={
            repo_name: template_repos[repo_name]
            for repo_name in main_repos
        },
        modules=['base'],
        db_dump_file=f'{name}.dmp',
        post_hook_script='post_hook.py',
        venv_path='.venv',
        rc_file='.odoorc',
        extra_config=None,
    ).to_json()


class Project(JsonMixin):

    def __init__(self, name, path, last_used):
        self.name = name
        self.path = path
        self.last_used = last_used or 'master'

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


class Projects(JsonMixin, dict):

    def __init__(self, projects=None, defaults=None, path=None):
        self.path = Path(path)
        self.defaults = defaults or {
            "db_name": "odoo",
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
        return Projects.load_json(path) or Projects(path=path)

    def save(self):
        ensure(self.path.parent)
        return self.save_json(self.path)
