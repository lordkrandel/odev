# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from external import External
import os
import invoke


class Odoo(External):

    @classmethod
    def get_demo_option(cls, demo):
        return not demo and "--without-demo=WITHOUT_DEMO" or ""

    @classmethod
    def start(cls, odoo_bin_path, odoo_rc_fullpath, venv_path, modules, options='', mode='', pty=False, demo=False, in_stream=None):
        modules = ("-i %s" % ",".join(modules)) if modules else ''
        context = invoke.Context()
        with context.cd(odoo_bin_path):
            venv_script_path = os.path.join(venv_path, 'bin/activate')
            command = f'source {venv_script_path} && ./odoo-bin {mode} {cls.get_demo_option(demo)} -c {odoo_rc_fullpath} {modules} {options}'
            print(command)
            context.run(command, pty=pty, in_stream=in_stream)

    @classmethod
    def start_tests(cls, odoo_bin_path, odoo_rc_fullpath, venv_path, modules, tags=None):
        tags = f"--test-tags={tags}" if tags else ""
        cls.start(odoo_bin_path,
                  odoo_rc_fullpath,
                  venv_path,
                  modules,
                  f'--test-enable --stop-after-init {tags}',
                  pty=True,
                  demo=True)
