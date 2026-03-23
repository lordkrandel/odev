# Part of Odoo. See LICENSE file for full copyright and licensing details.

import invoke
from tempfile import NamedTemporaryFile

from external import External
from pathlib import Path


class Odoo(External):

    @classmethod
    def banner(cls, bin_path, venv_path, modules, options, mode, demo, stop, workspace):
        addons_path = ",".join(str(x) for x in (workspace.addons_path or []))
        upgrade_path = ",".join(str(x) for x in (workspace.upgrade_path or []))
        base_path = Path(bin_path).absolute().parent
        print(f"{80 * '-'}")
        print("Odoo starting...")
        print(f"    Odoo: {bin_path}/odoo-bin")
        if workspace:
            print(f"    addons_path:  {addons_path}")
            print(f"    upgrade_path: {upgrade_path}")
            print(f"    extra_config: {workspace.extra_config}")
            print(f"    database: {workspace.db_name}")
        print(f"    Virtualenv: {Path(venv_path).relative_to(base_path)}")
        if modules:
            print(f"    Modules: {modules}")
        if options:
            print(f"    Options: {options}")
        if mode:
            print(f"    Mode: {mode}")
        if stop:
            print(f"    Stop: {stop}")
        print(f"    Demo data: {demo}")
        print(f"{80 * '-'}")

    @classmethod
    def get_demo_option(cls, demo):
        return not demo and "--without-demo=1" or "--without-demo=0"

    @classmethod
    def start(cls, project, workspace, modules=None, options=None, mode=None, pty=False, demo=False, stop=False, in_stream=None, env_vars=None):
        project_path = Path(project.path)
        bin_path = project_path / 'odoo'
        venv_path = project_path / workspace.venv_path

        options = options or ''
        mode = mode or ''
        env_vars = env_vars or ''
        stop = "--stop-after-init" if stop else ''

        if modules:
            modules = f"-i {','.join(modules)}"
        elif modules is None:
            modules = f"-i {','.join(workspace.modules)}"
        else:
            modules = ""

        cls.banner(bin_path, venv_path, modules, options, mode, demo, stop, workspace)

        extra_config = {
            "addons_path": ",".join(str(project_path / x) for x in (workspace.addons_path or [])),
            "upgrade_path": ",".join(str(project_path / x) for x in (workspace.upgrade_path or [])),
            "db_name": workspace.db_name or 'odoo',
            **workspace.extra_config,
        }

        with NamedTemporaryFile(mode='w+', delete=False, delete_on_close=False) as tfile:
            tfile.write("[options]\n")
            for k, v in (extra_config or {}).items():
                tfile.write(f"{k}={v}\n")
            tfile.close()
            context = invoke.Context()
            with context.cd(bin_path):
                venv_script_path = project_path / Path(workspace.venv_path) / 'bin' / 'activate'
                command = f'source {venv_script_path} && {env_vars} {bin_path}/odoo-bin {mode} {cls.get_demo_option(demo)} -c {tfile.name} {modules} {stop} {options}'
                print(command)
                context.run(command, pty=pty, in_stream=in_stream)

    @classmethod
    def start_tests(cls, project, workspace, modules=None, tags=None):
        options = f'--test-enable --stop-after-init {f"--test-tags={tags}" if tags else ""}'
        cls.start(
            project=project,
            workspace=workspace,
            modules=modules,
            options=options,
            pty=True,
            demo=True,
        )

    @classmethod
    def l10n_tests(cls, bin_path, db_name, venv_path):
        context = invoke.Context()
        with context.cd(bin_path):
            venv_script_path = Path(venv_path) / 'bin' / 'activate'
            command = f'source {venv_script_path} && {bin_path}/odoo/tests/test_module_operations.py -d {db_name} --standalone all_l10n'
            print(command)
            context.run(command, pty=True)
