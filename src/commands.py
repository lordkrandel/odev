#!/usr/bin/python3

import ast
import copy
import fileinput
import itertools
import shutil
import re
import sys
from glob import glob
from pathlib import Path
from typing import Optional

import click
from invoke import UnexpectedExit
from typer import Argument, Context, Option

import paths
import pl
import tools
from consts import APPNAME, IAP_BASE
from env import Environment
from git import Git
from odev import odev
from odoo import Odoo
from pgsql import PgSql
from runbot import Runbot
from templates import main_repos, post_hook_template, template_repos, addons_path, origins
from workspace import Workspace


# Help strings -----------------------------------

extra_help = "Additional command line parameters"
db_name_help = "Name of the database"
project_path_help = "Path where to create the project, default is current"
project_name_help = "Name of the project (md5 of the path)"
modules_csv_help = "CSV list of modules"
venv_path_help = "Virtualenv path"
repos_csv_help = "CSV list of repositories"
workspace_name_help = "Name of the workspace that holds the database information, omit to use current"


# Project ----------------------------------------

@odev.command()
def projects():
    """
        Print the projects folder
    """
    print(odev.paths.projects)


@odev.command()
def last_used():
    """
        Print the last_used workspace
    """
    if not odev.project:
        sys.exit(1)
    print(odev.project.last_used)


@odev.command()
def project_create(
    project_path: Optional[str] = Argument(None, help=project_path_help),
    db_name: Optional[str] = Argument(None, help=db_name_help)
):
    """
        Create a project for the current directory
    """
    if project_path:
        project_path = Path(project_path).absolute()
    else:
        project_path = Path().absolute()

    if odev.projects:
        db_name = db_name or odev.projects.defaults['db_name']

    print(f"Creating project in folder {project_path}")
    return tools.create_project(project_path, db_name)


# Workspace ------------------------------------------------


def set_target_workspace(workspace_name: str = None):
    subcommand = click.get_current_context().parent.invoked_subcommand
    if subcommand is None:
        # If it's autocomplete, don't ask interactively
        return
    if not workspace_name:
        workspace_name = tools.select_workspace("select (default=last)", odev.project)
    elif workspace_name == 'last':
        workspace_name = odev.project.last_used
    else:
        workspace_name = tools.cleanup_colon(workspace_name)
    odev.workspace = Workspace.load_json(odev.paths.workspace_file(workspace_name))
    if odev.workspace:
        odev.workspace.set_path(odev.paths.project)
        for repo_name, repo in odev.workspace.repos.items():
            if str(odev.paths.starting).startswith(str(odev.paths.relative('') / repo_name)):
                odev.repo = repo
                break
    if workspace_name not in odev.workspaces:
        print(f"Workspace {workspace_name} not found.")
        sys.exit(0)

    return workspace_name


def WorkspaceNameArgument(*args, default='last', **kwargs):

    def workspaces_yield(incomplete: Optional[str] = None):
        return [workspace_name for workspace_name in odev.workspaces if workspace_name.startswith(workspace_name)]

    return Argument(*args, **{
        **kwargs,
        'help': workspace_name_help,
        'callback': set_target_workspace,
        'default': default,
        'autocompletion': workspaces_yield,
    })


@odev.command()
def workspaces():
    """
        Output the path of the workspaces folder
    """
    print(f"{odev.paths.config / 'workspaces' / odev.project.name}")


@odev.command()
def workspace(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    edit: bool = False,
    name: bool = False,
    file: bool = False
):
    """
        Display currently selected workspace data.
    """
    if not odev.workspace:
        print(f"No workspace named '{workspace_name}' found")
        return
    print(odev.paths.workspace_file(odev.workspace.name))


@odev.command()
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
    if not status(extended=False) and reset():
        return

    bundle_name = tools.cleanup_colon(bundle_name)
    if not (repo_names := Runbot.get_branches(bundle_name)):
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
                repo.branch = IAP_BASE
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
    set_target_workspace(workspace.name)
    _switch(workspace.name, ask_reset=False)

@odev.command()
def workspace_dupe(workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
                   dest_workspace_name: Optional[str] = Argument(None, help="Destination name"),
                   _load: bool = False):
    """
        Duplicate a workspace.
    """
    if not dest_workspace_name:
        dest_workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
        if not dest_workspace_name:
            return
    dest_workspace_name = tools.cleanup_colon(dest_workspace_name)
    sourcepath, destpath = odev.paths.workspace(workspace_name), odev.paths.workspace(dest_workspace_name)
    print(f'Copy {sourcepath} -> {destpath}')
    shutil.copytree(sourcepath, destpath)

    print('Changing the workspace file')
    source_json_path = destpath / f"{workspace_name}.json"
    dest_json_path = destpath / f"{dest_workspace_name}.json"
    shutil.move(source_json_path, dest_json_path)

    with fileinput.FileInput(dest_json_path, inplace=True, backup='.bak') as f:
        for line in f:
            if workspace_name in line and "branch" in line:
                print(f'{line.rstrip()} #" {dest_workspace_name}",')
            elif workspace_name in line and ("name" in line or "dump" in line):
                print(line.replace(workspace_name, dest_workspace_name), end="")
            else:
                print(line, end="")

    set_target_workspace(dest_workspace_name)
    workspace(dest_workspace_name, edit=True)
    if _load:
        load(dest_workspace_name)


@odev.command()
def delete(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Delete a workspace.
    """
    if not tools.confirm(f"delete {odev.paths.workspace(workspace_name)}"):
        return
    tools.delete_workspace(workspace_name)
    if odev.project.last_used == workspace_name:
        tools.set_last_used("master")


@odev.command()
def create(
    ctx: Context,
    db_name: Optional[str] = Argument(None, help=db_name_help),
    modules_csv: Optional[str] = Argument(None, help=modules_csv_help),
    venv_path: Optional[str] = Argument(None, help=venv_path_help),
    repos_csv: Optional[str] = Argument(None, help=repos_csv_help),
):
    """
        Create a new workspace from a series of selections.
    """

    new_workspace_name = None
    if not (workspace := tools.workspace_prepare(
        new_workspace_name,
        db_name,
        venv_path,
        repos=[template_repos[name] for name in (repos_csv or '').split(',') if name.strip()],
        modules_csv=modules_csv,
    )):
        return

    tools.workspace_install(workspace)

    workspace_file = odev.paths.workspace_file(workspace.name)
    with fileinput.FileInput(workspace_file, inplace=True, backup='.bak') as f:
        for line in f:
            if workspace.name in line and "branch" in line:
                print(f'{line.rstrip()} # "{workspace.name}",')
            elif 'remote' in line and '"dev"' not in line:
                print(f'{line.rstrip()} # "dev",')
            else:
                print(line, end="")

    return odev.workspace


# OPERATIONS ---------------------------------

def sname(name="QuickSave"):
    from datetime import datetime
    return f"{name}_{datetime.now().strftime('%a%d%b%Y_%H%M%S')}"

@odev.command()
def ssave(
    ctx: Context,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    name: Optional[str] = Argument(default="QuickSave"),
):
    pl.run(
        f"git -C {{path}} stash push -u -m '{sname(name)}'",
        repos=odev.workspace.repos,
    )

@odev.command()
def sload(
    ctx: Context,
    name: Optional[str] = Argument(default='QuickSave'),
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    output = pl.run(
        f"git -C {{path}} stash list --grep='{name}'",
        repos=odev.workspace.repos,
        header=False,
        output=False,
    )
    result = [
        {
            k: int(v) if v.isdigit() else v
            for k, v in groups.items()
        }
        for line in output.splitlines()
        if (name in line)
        and (match := re.match(r'stash@{(?P<stash_no>\d+)}: On (?P<branch>.*): (?P<title>.*)$', line))
        and (groups := match.groupdict())
    ]
    for line in result:
        if name == 'QuickSave':
            line['title'] = re.sub(r'_?QuickSave_?', '', line['title'])
        print(f"#{line['stash_no']}: {line['title']} ({line['branch']})")

@odev.command()
def start(workspace_name: Optional[str] = WorkspaceNameArgument(),
          fast: bool = False,
          demo: bool = False,
          options: Optional[str] = None,
          stop: bool = False):
    """
        Start Odoo and reinitialize the workspace's modules.
    """
    options = options or ''
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)

    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        modules=odev.workspace.modules if not fast else [],
        options=options,
        pty=True,
        demo=demo,
        stop=stop,
    )


@odev.command()
def load(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Load given workspace into the session.
    """
    _switch(workspace_name)


@odev.command()
def clean():
    """
        Git clean all repos
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    pl.run(
        "git -C {path} clean -xdf",
        repos=odev.workspace.repos,
    )

@odev.command()
def reset(
    ask: bool = True,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Git reset on all workspaces, hard by default
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    if not ask or tools.strtobool(tools.input_text("Do you wanna reset all changes? (Y/n)")) in (True, 'default'):
        pl.run(
            "git -C {path} reset --hard",
            repos=odev.workspace.repos,
        )
        return False
    return True

def _switch(workspace_name, ask_reset=True):
    workspace_file = odev.paths.workspace_file(workspace_name)
    workspace = Workspace.load_json(workspace_file)
    repos = workspace.repos
    if not status(extended=False) and ask_reset and reset():
        return

    last_used = odev.project.last_used
    print(f"{last_used} -> {workspace_name} (updated)...")

    pl.run(
        "git -C {path} rebase --abort",
        "git -C {path} fetch --progress --verbose  {remote} {branch}",
        repos=odev.workspace.repos,
    )
    reset(ask=False)
    clean()
    pl.run(
        "git -C {path} switch -C {branch} --track {remote}/{branch}",
        repos=odev.workspace.repos
    )
    pl.run(
        "git -C {path} pull {remote} {branch}",
        repos=odev.workspace.repos
    )
    clean()
    tools.set_last_used(workspace_name)
    odev.workspace = workspace


@odev.command()
def shell(
    interface: Optional[str] = Argument("ipython", help="Type of shell interface (ipython|ptpython|bpython)"),
    script: Optional[str] = Option(None, help="Startup Python script to initialize the Shell"),
    workspace_name: Optional[str] = WorkspaceNameArgument()
):
    """
        Starts Odoo as an interactive shell.
    """
    interface = f'--shell-interface={interface}' if interface else ''
    env_vars = f'PYTHONSTARTUP={script}' if script else ''
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)
    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start(
        project=odev.project,
        workspace=odev.workspace,
        modules=[],
        options=interface,
        mode='shell',
        pty=True,
        env_vars=env_vars,
    )


@odev.command()
def setup(db_name: Optional[str] = Argument(None, help="Odoo database name")):
    """
        Sets up the main folder, with repos and venv.
    """

    project_path = Path().absolute()
    if not odev.project:
        odev.project = project_create(project_path, db_name)
        odev.setup_current_project()
        odev.setup_variable_paths()
        odev.workspaces = sorted([x.name for x in odev.paths.workspaces.iterdir()])
    else:
        odev.project.db_name = db_name
    odev.projects[odev.project.name] = odev.project
    odev.projects.save()

    paths.ensure(odev.paths.workspaces)
    have_dev_origin = [k for k, v in origins.items() if 'dev' in v]

    # Clone the base repos and set the 'dev' remote
    for repo_name, repo in tools.select_repositories("setup", None, checked=main_repos).items():
        path = odev.paths.repo(repo_name)

        clone_path = path

        if not clone_path.exists():
            print(f"creating path {clone_path}...")
            paths.ensure(clone_path)

        if not list(clone_path.glob("*")):
            print(f"cloning {repo_name} in {clone_path}...")
            origin_url = 'git@github.com:odoo/{repo.name}.git'
            Git.clone(origin_url, repo.branch, clone_path)
            if repo in have_dev_origin:
                dev_url = 'git@github.com:odoo/{repo.name}-dev.git'
                Git.add_remote('dev', dev_url, clone_path)

        setup_requisites(odev.paths.relative('.venv'),
                         added_csv='ipython,pylint',
                         reqs_file_csv=f"{repo_name}/requirements.txt")

    workspace_name = 'master'
    workspace_file = odev.paths.workspace_file(workspace_name)
    workspace_path = odev.paths.workspace(workspace_name)

    # Create the master workspace
    if not workspace_file.exists():
        print(f"Creating workspace {workspace_file}...")
        repos = {k: v for k, v in template_repos.items() if k in main_repos}
        new_workspace = Workspace(workspace_name, db_name, repos, ['base'])
        paths.ensure(workspace_path)
        new_workspace.save_json(workspace_file)
    else:
        print(f"{workspace_file} workspace already exists...")

    # Create the post_hook script
    post_hook_path = workspace_path / "post_hook.py"
    if not post_hook_path.exists():
        print(f"Creating {post_hook_path} post_hook script...")
        with Path.open(post_hook_path, "w", encoding="utf-8") as post_hook_file:
            post_hook_file.write(post_hook_template)
    else:
        print(f"{post_hook_path} already exists...")


@odev.command()
def setup_requisites(
        path=Argument(help='Base path for the virtual env'),
        added_csv: Optional[str] = Argument(help="CSV of the additional python modules to be installed", default=None),
        reqs_file_csv: Optional[str] = Argument(help="CSV of the requirements modules files", default=None)
    ):
    """
        Setup a Python virtual environment for the project.
    """
    venv_path = Path(path)
    exists = venv_path.exists()
    paths.ensure(venv_path)
    added = [x for x in (added_csv or '').split(',') if x.strip()]
    reqs_files = (reqs_file_csv or '').split(",")

    env = Environment(venv_path)
    if not exists:
        env.create()

    with env:
        print("installing pip...")
        env.context.run("pip install --upgrade pip")
        for reqs_file in reqs_files:
            if reqs_file and Path(reqs_file).exists():
                print(f"installing {reqs_file}")
                env.context.run(f"pip install -r {reqs_file}")
        for module in added:
            env.context.run(f"pip install --upgrade {module}")


# Cache -------------------------------------------------

@odev.command()
def update_merge_base_cache(
    workspace_name: Optional[str] = WorkspaceNameArgument()
):
    """
        Update the merge base cache
    """
    versions = odev.merge_cache.versions
    have_dev_origin = [k for k, v in origins.items() if 'dev' in v]
    repos = {
        repo_name: repo
        for repo_name, repo in odev.workspace.repos.items()
        if repo_name in have_dev_origin
    }
    pl.run(
        "git -C {path} fetch {remote} {branch}",
        repos=repos,
    )
    results = tools.await_all_results({
        f'{repo_name}/{version}': Git.merge_base_async(repo_path, 'origin/master', f'origin/{version}')
        for repo_name, repo in repos.items()
        for version in versions
        if (repo_path := odev.paths.repo(repo_name))
    })
    for key, merge_base in results.items():
        repo, version = key.split('/')
        merge_base = merge_base.decode().rstrip()
        getattr(odev.merge_cache, repo)[merge_base] = version
    odev.merge_cache.save_json(odev.paths.cache)


# Git ---------------------------------------------------


@odev.command()
def status(
    extended: bool = True,
    workspace_name: Optional[str] = WorkspaceNameArgument(default='last')
):
    """
        Display status for all repos for current workspace.
    """
    if extended:
        print(f"{odev.project.path} - {odev.workspace.name}")
    for repo_name, repo in odev.workspace.repos.items():
        path = odev.paths.repo(repo_name)
        if not path.is_dir():
            print(f"Repository {repo_name} hasn't been cloned yet.")
            continue
        ret = Git.status(path, extended=extended, name=repo_name)
        if not extended and ret.stdout:
            return False
    return True


@odev.command()
def diff(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-diffs all repositories.
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    pl.run(
        "git -C {path} status --untracked-files --short",
        "git -C {path} diff",
        "git -C {path} diff --cached",
        repos=odev.workspace.repos,
    )


@odev.command()
def fetch(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-fetches multiple repositories.
    """
    workspace = odev.workspace if not origin else None
    for repo_name, repo in tools.select_repositories("fetch", workspace, checked=main_repos).items():
        print(f"Fetching {repo_name}...")
        path = odev.paths.repo(repo_name)
        if origin:
            Git.fetch(path, repo_name, "origin", "")
    else:
            Git.fetch(path, repo_name, repo.remote, repo.branch)


@odev.command()
def pull(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-pulls selected repos for current workspace.
    """
    for repo_name in tools.select_repositories("pull", odev.workspace, checked=main_repos):
        print(f"Pulling {repo_name}...")
        repo = odev.workspace.repos[repo_name]
        Git.pull(odev.paths.repo(repo_name), repo.remote, repo.branch)


def _checkout_repo(repo_name, repo, force_create=False):
    path = odev.paths.repo(repo_name)
    target = f"{repo_name} {repo.remote}/{repo.branch}"
    try:
        print(f"Fetching {target}...")
        Git.fetch(path, repo_name, repo.remote, repo.branch)
    except UnexpectedExit:
        if not force_create:
            raise
        print(f"Creating {target}...")
        Git.checkout(path, repo.branch, options="-B")
    print(f"Checking out {target}...")
    Git.checkout(path, repo.branch)
    print(f"Cleaning {path}...")
    Git.clean(path, quiet=True)



@odev.command()
def update(ctx: Context, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Updates given workspace and reloads the current one.
        With asynchronous methods.
    """
    last_used = odev.project.last_used
    _switch(workspace_name)
    if last_used:
        last_workspace_file = odev.paths.workspace_file(last_used)
        last_repos = Workspace.load_json(last_workspace_file).repos
        tools.async_sequence(last_repos, promises=[Git.checkout_async])
        tools.set_last_used(workspace_name)


@odev.command()
def checkout(
    workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
    force_create: bool = False
):
    """
        Git-checkouts multiple repositories.
    """
    repos = (odev.workspace and odev.workspace.repos)
    for repo_name, repo in repos.items():
        print(f"Checkout repo {repo_name} branch {repo.branch}...")
        _checkout_repo(repo_name, repo, force_create=force_create)
    return repos


# Files  ------------------------------------------------------------

@odev.command()
def hook(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Print the post_hook python full path
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    print(odev.paths.workspace(odev.workspace.name) / Path(odev.workspace.post_hook_script))


@odev.command()
def rc(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Print the .odoorc config with default editor.
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    print(odev.paths.project / Path(odev.workspace.rc_file))


# Db ------------------------------------------------------------

@odev.command()
def db_clear(db_name: Optional[str] = Argument(None, help="Database name"),
             workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Clear database by dropping and recreating it.
    """
    return PgSql.erase(db_name or odev.workspace.db_name)


@odev.command()
def db_dump(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Dump the DB for the selected workspace.
    """
    dump_fullpath = odev.paths.workspace(odev.workspace.name) / odev.workspace.db_dump_file
    print(f"Dumping {odev.workspace.db_name} -> {dump_fullpath}")
    PgSql.dump(odev.workspace.db_name, dump_fullpath)


@odev.command()
def db_restore(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Restore the DB for the selected workspace.
    """
    dump_fullpath = odev.paths.workspace(workspace_name) / odev.workspace.db_dump_file
    print(f"Restoring {odev.workspace.db_name} <- {dump_fullpath}")
    PgSql.restore(odev.workspace.db_name, dump_fullpath)


@odev.command()
def upgrade(old_workspace_name: str = Argument(help="Repository to be upgraded"),
            workspace_name: Optional[str] = WorkspaceNameArgument(),
            test: bool = False, test_upgrade: bool = False, hook: bool = False):
    """
        Run upgrade from a old Workspace to a new Workspace
        ex. ocli upgrade 19.0 19.0-account-myfix-tag
    """

    if not status(extended=False):
        print("Cannot upgrade, changes present.")
        return

    assert 'upgrade' in odev.workspace.repos
    assert 'upgrade-util' in odev.workspace.repos

    odoo_path = odev.paths.repo('odoo')
    upgrade_path = odev.paths.repo('upgrade') / 'migrations'
    upgrade_util_path = odev.paths.repo('upgrade-util') / 'src'

    print(f"Upgrading {old_workspace_name} -> {workspace_name}")
    print(f"Loading {old_workspace_name}...")
    load(old_workspace_name)
    test_str = ""
    if test or test_upgrade:
        test_str = "--test-enable --test-tags=upgrade.test_prepare"
    db_init(old_workspace_name, demo=True, stop=True, post_init_hook=hook, options=test_str)

    db_dump()

    print(f"Loading {workspace_name}...")
    load(workspace_name)
    print("Cleaning old folders that might have old files")
    Git.clean(odoo_path, quiet=True)

    test_str = ""
    if test or test_upgrade:
        test_str = "--test-enable --test-tags="
        test_tags = []
        if test_upgrade:
            test_tags.append("upgrade.test_check")
        if test:
            test_tags.append("at_install")
            test_tags.append("-post_install")
        test_str += ",".join(test_tags)
    upgrade_options = f'--upgrade-path={upgrade_util_path},{upgrade_path} {test_str} -u all'
    start(odoo_path, options=upgrade_options, demo=True, fast=True, stop=True)


@odev.command()
def l10n_tests(tags: Optional[str] = "*",
               workspace_name: Optional[str] = WorkspaceNameArgument(),
               fast: bool = False):
    """ Run l10n tests """

    # Eventually erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db_clear(odev.workspace.db_name)
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)

    Odoo.l10n_tests(odev.paths.relative('odoo'),
                    odev.workspace.db_name,
                    odev.paths.relative(odev.workspace.venv_path),
                    tags)


def _tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False):
    """
        Generic test function for all commands.
    """
    # Erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db_clear(odev.workspace.db_name)

    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(odev.workspace.modules))
    Odoo.start_tests(
        project=odev.project,
        workspace=odev.workspace,
        modules=odev.workspace.modules if not fast else [],
        tags=tags,
    )


@odev.command()
def post_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Init db (if not fast) and run Odoo's post_install tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}-at_install", fast=fast)


@odev.command()
def init_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Init db and run Odoo's at_install tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}-post_install", fast=False)


@odev.command()
def external_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Init db and run Odoo's external tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}external", fast=True)


@odev.command()
def test(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Initialize db and run all tests, but the external ones.
    """
    post_tests(tags)
    init_tests(tags)

def get_invalid_modules():
    all_modules = set()
    for repo_name, repo in odev.workspace.repos.items():
        repo_path = odev.paths.repo(repo_name)
        for path in addons_path.get(repo_name, []):
            all_modules |= set(Path(x).parent.name for x in glob(f"{repo_path}/{path}/*/__manifest__.py"))
    return set(odev.workspace.modules) - all_modules

@odev.command()
def db_init(
        workspace_name: Optional[str] = WorkspaceNameArgument(),
        options: Optional[str] = None,
        modules_csv: Optional[str] = None,
        dump_before: bool = False,
        dump_after: bool = False,
        demo: bool = False,
        stop: bool = False,
        debug_hook: bool = False,
        post_init_hook: bool = True
    ):
    """
         Initialize the database, with modules and hook.
    """
    options = options or ''

    # Erase the database
    print(f'Erasing {odev.workspace.db_name}...')
    db_clear(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)
    venv_path = odev.paths.relative(odev.workspace.venv_path)
    odoo_path = odev.paths.repo('odoo')

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
        db_dump(workspace_name)

    if post_init_hook:
        print('Executing post_init_hook...')
        hook_path = odev.paths.workspace(odev.workspace.name) / odev.workspace.post_hook_script
        if debug_hook:
            stop = False
            env_vars = f'PYTHONSTARTUP="{hook_path}"'
        else:
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
        db_dump(workspace_name)

    if not stop:
        print('Starting Odoo...')
        Odoo.start(
            project=odev.project,
            workspace=odev.workspace,
            modules=[],
            options="",
            pty=True,
        )


# Venv -----------------------------------------------------------

@odev.command()
def activate_path(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Path to the activate script for the current virtual environment.
    """
    print(Path(odev.project.path) / odev.workspace.venv_path / "bin" / "activate")


# Lint -----------------------------------------------------------

@odev.command()
def lint(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Start linting tests.
    """
    print("Pylint checking...")
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)
    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start_tests(
        project=odev.project,
        workspace=odev.workspace,
        modules=['test_lint'],
        options="/test_lint",
    )


# Deps -----------------------------------------------------------

@odev.command()
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
