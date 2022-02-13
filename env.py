# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import venv
import invoke
import os.path

class Environment():

    def __init__(self, path):
        self.path = path

    def create(self):
        venv.create(self.path, clear=False, with_pip=True)

    def __enter__(self):
        self.context = invoke.Context()
        activate_path = os.path.join(self.path, "bin", "activate")
        self.prefix = self.context.prefix(f'source {activate_path}')
        return self.prefix.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        prefix = self.prefix
        result = prefix.__exit__(exc_type, exc_val, exc_tb)
        self.prefix = None
        self.context = None
        return result
