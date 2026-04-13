import ast
import copy
import itertools
import re
import sys
import tempfile
import textwrap
from glob import glob
from pathlib import Path
from typing import Optional

from typer import Argument, Context, Option

# import paths
import commands.db as db
import pl
import tools
from consts import APPNAME
from commands import git
from commands.common import WorkspaceNameArgument, set_target
from commands.workspace import _switch
from git import Git
from odev import odev
from odoo import Odoo
from runbot import Runbot
from templates import addons_path, origins, main_repos, template_repos


@odev.odoo.command(name="start")
def start(workspace_name: Optional[str] = WorkspaceNameArgument(),
          fast: bool = False,
          demo: bool = False,
          options: Optional[str] = None,
          stop: bool = False):
    """
        Start Odoo and reinitialize the workspace's modules.
    """
    options = options or ''
    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        modules=odev.workspace.modules if not fast else [],
        options=options,
        pty=True,
        demo=demo,
        stop=stop,
    )


@odev.odoo.command()
def shell(
    interface: Optional[str] = Argument("ipython", help="Type of shell interface (ipython|ptpython|bpython)"),
    script: Optional[str] = Option(None, help="Startup Python script to initialize the Shell"),
    workspace_name: Optional[str] = WorkspaceNameArgument()
):
    """
        Starts Odoo as an interactive shell.
    """
    interface = f'--shell-interface={interface} ' if interface else ''
    script = f'--shell-file={script} ' if script else ''
    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        modules=[],
        options=interface + script,
        mode='shell',
        pty=True,
    )


@odev.odoo.command()
def deps(module, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Find module dependancy order for a specific module.
    """
    to_be_done = [module]
    deps = []
    found = set()
    data = {}

    while to_be_done:
        current = to_be_done[0]

        manifest_names = ['__manifest__.py', '__openerp__.py']

        folders = []
        for repo_name, repo in odev.workspace.repos.items():
            if repo_addons_path := addons_path.get(repo_name, []):
                for folder in repo_addons_path:
                    folders.append(str(odev.paths.relative(repo_name) / folder))

        fullpaths = [Path(x) / current / y
                     for x, y in itertools.product(folders, manifest_names)]

        for fullpath in fullpaths:
            if Path.is_file(fullpath):
                with Path.open(fullpath, encoding="utf-8") as f:
                    data = ast.literal_eval(f.read())
                break

        if current not in found:
            found.add(current)
            if current in deps:
                deps.remove(current)
            deps.insert(0, current)

        subs = data.get('depends', [])
        for sub in subs:
            if sub not in found:
                found.add(sub)
                to_be_done.append(sub)
            else:
                deps.remove(sub)
            deps.insert(0, sub)

        to_be_done = to_be_done[1:]

    print(deps)
    return deps


@odev.odoo.command()
def get_branches(
    bundle_name: str = Argument('None', help='Bundle name'),
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Get from runbot the set of repos that have a branch with that name
    """
    bundle_name = tools.cleanup_colon(bundle_name or workspace_name)
    branches = Runbot.get_branches(bundle_name)
    print(branches)
    return branches


@odev.odoo.command()
def bundle(
    ctx: Context,
    bundle_name: str = Argument(None, help="Bundle name"),
    db_name: str = Argument('odoo', help="Database name"),
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Creates a workspace from a Bundle on Runbot.
        If `load` is specified, it also loads generated workspace.
    """
    if not odev.project:
        sys.exit(f"{APPNAME}: current folder holds no projects.")
    if not git.status(extended=False) and git.reset():
        return

    bundle_name = tools.cleanup_colon(bundle_name)
    if not (repo_names := get_branches()):
        sys.exit(f"Bundle {bundle_name} not found")

    version = tools._extract_version(bundle_name)
    venv_path = tools.get_venv_path(version)

    base_branch = version['name']
    have_dev_origin = [k for k, v in origins.items() if 'dev' in v]
    if arbitrary_repo := next(iter(have_dev_origin), None):
        base_branch = tools.find_base(arbitrary_repo, branch=bundle_name)

    repos = {}
    for repo_name in set(main_repos) | set(repo_names):
        repo = copy.copy(template_repos[repo_name])
        repo_path = odev.paths.project / repo_name

        if repo_name in repo_names:
            repo.branch = bundle_name
            repo.remote = 'dev' if repo_name in have_dev_origin else 'origin'
        else:
            if repo_name in have_dev_origin: 
                repo.branch = base_branch
            elif repo_name.lower() == 'iap-apps':
                repo.branch = template_repos['iap-apps'].branch
            else:
                repo.branch = 'master'
            repo.remote = 'origin'
        repo.path = str(odev.paths.repo(repo_name))
        repos[repo_name] = repo

    if not (workspace := tools.workspace_prepare(
        bundle_name,
        db_name=db_name,
        repos=repos,
        venv_path=venv_path,
        ask_modules=False,
    )):
        return

    # if not given, search for modules
    if (search_modules := (workspace.modules == [])):
        modules = set()
    else:
        modules = workspace.modules

    pl.run(
        "git -C {path} fetch --progress {remote} " + base_branch,
        "git -C {path} fetch --progress {remote} {branch}",
        repos=repos,
    )
    pl.run(
        "git -C {path} checkout {remote}/{branch}",
        repos=repos,
    )

    for repo_name, repo in repos.items():
        if search_modules and repo_name in repo_names:
            # Search for modules from the diff
            repo_path = odev.paths.project / repo_name
            if diffiles := Git.diff_with_merge_base(repo_path, f"origin/{base_branch}", f"{repo.remote}/{repo.branch}"):
                for diffile in diffiles:
                    if match := re.match(r"(?:addons/)?([^/]+)/.*", diffile):
                        modules.add(match.group(1))
        workspace.modules = list(modules)

    tools.workspace_install(workspace)
    set_target(workspace.name)
    _switch(workspace.name, ask_reset=False)


@odev.odoo.command()
def lint(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Start linting tests.
    """
    print("Pylint checking...")
    Odoo.start_tests(
        project=odev.project,
        workspace=odev.workspace,
        modules=['test_lint'],
        options="/test_lint",
    )


@odev.odoo.command()
def l10n_tests(
    tags: Optional[str] = "*",
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    fast: bool = False,
):
    """ Run l10n tests """

    # Eventually erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db.clear(odev.workspace.db_name)
    odev.paths.relative(odev.workspace.rc_file)

    Odoo.l10n_tests(odev.paths.relative('odoo'),
                    odev.workspace.db_name,
                    odev.paths.relative(odev.workspace.venv_path),
                    tags)


def _tests(
    tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"),
    fast: bool = False,
):
    """
        Generic test function for all commands.
    """
    # Erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db.clear(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(odev.workspace.modules))
    Odoo.start_tests(
        project=odev.project,
        workspace=odev.workspace,
        modules=odev.workspace.modules if not fast else [],
        tags=tags,
    )


@odev.odoo.command()
def test(
    tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"),
    fast: bool = False,
    workspace_name: Optional[str] = WorkspaceNameArgument()
):
    """
         Init db (if not fast) and run Odoo's post_install tests.
         This will install the demo data.
    """
    _tests(tags=tags, fast=fast)


@odev.odoo.command()
def test_commit(
    test_module: str,
    test_filename: str,
    test_class: str,
    test_name: Optional[str] = None,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Run a test class setupClass and commit, to create a test case
    """
    test_commit_template = textwrap.dedent("""\
        from odoo.addons.{test_module}.tests.{test_filename} import {test_class}

        {test_class}.setUpClass()

        test_instance = {test_class}()
        test_instance.setUp()

        {test_class}.commit_patcher.stop()
        {test_class}.savepoint.close(rollback=False)
        {test_class}.savepoint = None

        {test_name_str}

        {test_class}.cr.commit()
    """)
    _locals = locals()
    for token in ('test_module', 'test_filename', 'test_class'):
        test_commit_template = test_commit_template.replace(f'{{{token}}}', _locals[token])
    test_commit_template = test_commit_template.replace('{test_name_str}', f'test_instance.{test_name}()' if test_name else '')
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as f:
        f.write(test_commit_template)
        f.seek(0)
        shell("python", script=f.name)


def get_invalid_modules():
    all_modules = set()
    for repo_name, repo in odev.workspace.repos.items():
        repo_path = odev.paths.repo(repo_name)
        for path in addons_path.get(repo_name, []):
            all_modules |= set(Path(x).parent.name for x in glob(f"{repo_path}/{path}/*/__manifest__.py"))
    return set(odev.workspace.modules) - all_modules


@odev.odoo.command(name="init")
def init(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    options: Optional[str] = None,
    modules_csv: Optional[str] = None,
    dump_before: bool = False,
    dump_after: bool = False,
    demo: bool = False,
    debug_hook: bool = False,
    post_init_hook: bool = True
):
    """
         Initialize the database, with modules and hook.
    """
    options = options or ''

    # Erase the database
    print(f'Erasing {odev.workspace.db_name}...')
    db.clear(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')

    if invalid_modules := get_invalid_modules():
        sys.exit(f"Modules {invalid_modules} in the workspace list are not valid.")

    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        modules=['base'],
        options=options,
        demo=demo,
        stop=True,
    )

    modules = (modules_csv and modules_csv.split(',')) or odev.workspace.modules
    print('Installing modules %s ...', ','.join(modules))
    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        options=options,
        demo=demo,
        stop=True,
    )

    # Dump the db before the hook if the user has specifically asked for it
    if dump_before:
        db.dump(workspace_name)

    if post_init_hook:
        print('Executing post_init_hook...')
        hook_path = odev.paths.workspace(odev.workspace.name) / odev.workspace.post_hook_script
        if debug_hook:
            stop = False
            env_vars = f'PYTHONSTARTUP="{hook_path}"'
        else:
            stop = True
            env_vars = None
            options = f'{options} < {hook_path}'
        Odoo.start(
            project=odev.project,
            workspace=odev.workspace,
            modules=[],
            options=options,
            mode='shell',
            demo=demo,
            pty=True,
            stop=stop,
            env_vars=env_vars,
        )
        if debug_hook:
            return

    # Dump the db after the hook if the user has specifically asked for it
    if dump_after:
        db.dump(workspace_name)


@odev.odoo.command()
def setup(db_name: Optional[str] = Argument(None, help="Odoo database name")):
    """
        BROKEN -- Sets up the main folder, with repos and venv.
    """
    raise NotImplementedError()
    #     project_path = Path().absolute()
    #     if not odev.project:
    #         odev.project = project_create(project_path, db_name)
    #         odev.setup_current_project()
    #         odev.setup_variable_paths()
    #         odev.workspaces = sorted([x.name for x in odev.paths.workspaces.iterdir()])
    #     else:
    #         odev.project.db_name = db_name
    #     odev.projects[odev.project.name] = odev.project
    #     odev.projects.save()
    # 
    #     paths.ensure(odev.paths.workspaces)
    #     have_dev_origin = [k for k, v in origins.items() if 'dev' in v]
    # 
    #     # Clone the base repos and set the 'dev' remote
    #     for repo_name, repo in tools.select_repositories("setup", None, checked=main_repos).items():
    #         path = odev.paths.repo(repo_name)
    # 
    #         clone_path = path
    # 
    #         if not clone_path.exists():
    #             print(f"creating path {clone_path}...")
    #             paths.ensure(clone_path)
    # 
    #         if not list(clone_path.glob("*")):
    #             print(f"cloning {repo_name} in {clone_path}...")
    #             origin_url = f'git@github.com:odoo/{repo_name}.git'
    #             Git.clone(origin_url, template_repos[repo_name].branch, clone_path)
    #             if repo in have_dev_origin:
    #                 dev_url = f'git@github.com:odoo/{repo_name}-dev.git'
    #                 Git.add_remote('dev', dev_url, clone_path)
    # 
    #         setup_requisites(odev.paths.relative('.venv'),
    #                          added_csv='ipython,pylint',
    #                          reqs_file_csv=f"{repo_name}/requirements.txt")
    # 
    #     workspace_name = 'master'
    #     workspace_file = odev.paths.workspace_file(workspace_name)
    #     workspace_path = odev.paths.workspace(workspace_name)
    # 
    #     # Create the master workspace
    #     if not workspace_file.exists():
    #         print(f"Creating workspace {workspace_file}...")
    #         repos = {k: v for k, v in template_repos.items() if k in main_repos}
    #         new_workspace = Workspace(workspace_name, db_name, repos, ['base'])
    #         paths.ensure(workspace_path)
    #         new_workspace.save_json(workspace_file)
    #     else:
    #         print(f"{workspace_file} workspace already exists...")
    # 
    #     # Create the post_hook script
    #     post_hook_path = workspace_path / "post_hook.py"
    #     if not post_hook_path.exists():
    #         print(f"Creating {post_hook_path} post_hook script...")
    #         with Path.open(post_hook_path, "w", encoding="utf-8") as post_hook_file:
    #             post_hook_file.write(post_hook_template)
    #     else:
    #         print(f"{post_hook_path} already exists...")


@odev.odoo.command()
def setup_requisites(
    path=Argument(help='Base path for the virtual env'),
    added_csv: Optional[str] = Argument(help="CSV of the additional python modules to be installed", default=None),
    reqs_file_csv: Optional[str] = Argument(help="CSV of the requirements modules files", default=None)
):
    """
        BROKEN -- Setup a Python virtual environment for the project.
    """
    raise NotImplementedError()
    #     venv_path = Path(path)
    #     exists = venv_path.exists()
    #     paths.ensure(venv_path)
    #     added = [x for x in (added_csv or '').split(',') if x.strip()]
    #     reqs_files = (reqs_file_csv or '').split(",")
    # 
    #     env = Environment(venv_path)
    #     if not exists:
    #         env.create()
    # 
    #     with env:
    #         print("installing pip...")
    #         env.context.run("pip install --upgrade pip")
    #         for reqs_file in reqs_files:
    #             if reqs_file and Path(reqs_file).exists():
    #                 print(f"installing {reqs_file}")
    #                 env.context.run(f"pip install -r {reqs_file}")
    #         for module in added:
    #             env.context.run(f"pip install --upgrade {module}")


@odev.odoo.command()
def upgrade(old_workspace_name: str = Argument(help="Repository to be upgraded"),
            workspace_name: Optional[str] = WorkspaceNameArgument(),
            test: bool = False, test_upgrade: bool = False, hook: bool = False):
    """
        BROKEN --- Run upgrade from a old Workspace to a new Workspace
        ex. ocli upgrade 19.0 19.0-account-myfix-tag
    """
    raise NotImplementedError()
    # if not status(extended=False):
    #     print("Cannot upgrade, changes present.")
    #     return

    # assert 'upgrade' in odev.workspace.repos
    # assert 'upgrade-util' in odev.workspace.repos

    # odoo_path = odev.paths.repo('odoo')
    # upgrade_path = odev.paths.repo('upgrade') / 'migrations'
    # upgrade_util_path = odev.paths.repo('upgrade-util') / 'src'

    # print(f"Upgrading {old_workspace_name} -> {workspace_name}")
    # print(f"Loading {old_workspace_name}...")
    # load(old_workspace_name)
    # test_str = ""
    # if test or test_upgrade:
    #     test_str = "--test-enable --test-tags=upgrade.test_prepare"
    # db_init(old_workspace_name, demo=True, stop=True, post_init_hook=hook, options=test_str)

    # dump()

    # print(f"Loading {workspace_name}...")
    # load(workspace_name)
    # print("Cleaning old folders that might have old files")
    # Git.clean(odoo_path, quiet=True)

    # test_str = ""
    # if test or test_upgrade:
    #     test_str = "--test-enable --test-tags="
    #     test_tags = []
    #     if test_upgrade:
    #         test_tags.append("upgrade.test_check")
    #     if test:
    #         test_tags.append("at_install")
    #         test_tags.append("-post_install")
    #     test_str += ",".join(test_tags)
    # upgrade_options = f'--upgrade-path={upgrade_util_path},{upgrade_path} {test_str} -u all'
    # start(odoo_path, options=upgrade_options, demo=True, fast=True, stop=True)
