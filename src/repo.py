# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from json_mixin import JsonMixin


class Repo(JsonMixin):
    def __init__(self, name, dev, origin, remote, branch, addons_folders=None):
        self.name = name
        self.dev = dev
        self.origin = origin
        self.remote = remote
        self.branch = branch
        self.addons_folders = addons_folders or []
