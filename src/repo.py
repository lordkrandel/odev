# Part of Odoo. See LICENSE file for full copyright and licensing details.

from json_mixin import JsonMixin


class Repo(JsonMixin):
    def __init__(self, name, remote, branch, addons_folders, **kwargs):
        self.name = name
        self.remote = remote
        self.branch = branch
        self.addons_folders = addons_folders
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __copy__(self):
        return Repo(self.name, self.remote, self.branch, self.addons_folders)
