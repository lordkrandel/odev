# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from external import External
from rc import Rc
from pathlib import Path
import os
import invoke


class Odoo(External):

    @classmethod
    def banner(cls, bin_path, rc_fullpath, venv_path, modules, options, mode, demo):
        rc = Rc(rc_fullpath)
        base_path = Path(bin_path).absolute().parent
        print(f"{80 * '-'}")
        print("Odoo starting...")
        print(f"    Database: {rc.db_name}")
        print(f"    Addons: {rc._addons(base_path)}")
        print(f"    Virtualenv: {Path(venv_path).relative_to(base_path)}")
        if modules:
            print(f"    Modules: {modules}")
        if options:
            print(f"    Options: {options}")
        if mode:
            print(f"    Mode: {mode}")
        print(f"    Demo data: {demo}")
        print(f"{80 * '-'}")

    @classmethod
    def get_demo_option(cls, demo):
        return not demo and "--without-demo=WITHOUT_DEMO" or ""

    @classmethod
    def start(cls, bin_path, rc_fullpath, venv_path, modules, options='', mode='', pty=False, demo=False, in_stream=None):
        cls.banner(bin_path, rc_fullpath, venv_path, modules, options, mode, demo)
        modules = ("-i %s" % ",".join(modules)) if modules else ''
        context = invoke.Context()
        with context.cd(bin_path):
            venv_script_path = os.path.join(venv_path, 'bin/activate')
            command = f'source {venv_script_path} && ./odoo-bin {mode} {cls.get_demo_option(demo)} -c {rc_fullpath} {modules} {options}'
            print(command)
            context.run(command, pty=pty, in_stream=in_stream)

    @classmethod
    def start_tests(cls, bin_path, rc_fullpath, venv_path, modules, tags=None):
        options = f'--test-enable --stop-after-init {f"--test-tags={tags}" if tags else ""}'
        cls.start(bin_path, rc_fullpath, venv_path, modules, options, pty=True, demo=True)
