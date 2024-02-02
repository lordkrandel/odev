# Part of Odoo. See LICENSE file for full copyright and licensing details.

from json_mixin import JsonMixin


class Repo(JsonMixin):
    def __init__(self, name, dev, origin, remote, branch, addons_folders):
        self.name = name
        self.dev = dev
        self.origin = origin
        self.remote = remote
        self.branch = branch
        self.addons_folders = addons_folders

    def __copy__(self):
        return Repo(self.name, self.dev, self.origin, self.remote, self.branch, self.addons_folders)
