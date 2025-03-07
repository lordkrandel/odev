#!/usr/bin/python3

import ast
import copy
import fileinput
import itertools
import shutil
import re
import sys
from pathlib import Path
from typing import Optional

import click

import paths
import tools
from consts import APPNAME
from env import Environment
from external import External
from git import Git
from invoke import UnexpectedExit
from odev import odev
from pgsql import PgSql
from rc import Rc
from runbot import Runbot
from templates import main_repos, post_hook_template, template_repos, have_dev_origin
from typer import Argument, Context, Option
from workspace import Workspace

from odoo import Odoo

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
def projects(edit: bool = False, simple: bool = False):
    """
        Display all the available project folders.
    """
    if edit:
        editor = Git.get_editor()
        External.edit(editor, odev.paths.projects)
        return
    if not simple:
        print(f"{odev.paths.config}/workspaces/")
    max_len = max(len(project.name) for _, project in odev.projects.items())
    for name in sorted(odev.projects, key=lambda x: odev.projects[x].path):
        project = odev.projects[name]
        if simple:
            message = project.path
        else:
            message = f"    {project.name:{max_len}} --> {project.path}"
        print(message)


@odev.command()
def project():
    """
        Display project data for the current folder.
    """
    print(f"{odev.project.name}:: {odev.project.to_json()}")


@odev.command()
def last_used():
    """
        Output the last used workspace.
    """
    if odev.project:
        print(odev.project.last_used)
        sys.exit(0)
    else:
        sys.exit(1)


@odev.command()
def project_delete(project_name: Optional[str] = Argument(None, help=project_name_help)):
    """
        Delete a project.
    """
    project = tools.select_project("delete", project_name)
    if not project or not tools.confirm("delete it"):
        return
    tools.delete_project(project.name)


@odev.command()
def project_create(project_path: Optional[str] = Argument(None, help=project_path_help),
                   db_name: Optional[str] = Argument(None, help=db_name_help)):
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


def set_target_workspace(workspace_name: str):
    subcommand = click.get_current_context().parent.invoked_subcommand
    if subcommand is None:
        # If it's autocomplete, don't ask interactively
        return
    if not odev.project and subcommand != 'setup':
        sys.exit(f"{APPNAME}: current folder holds no project.")
    if not workspace_name:
        workspace_name = tools.select_workspace("select (default=last)", odev.project)
    elif workspace_name == 'last':
        workspace_name = odev.project.last_used
    else:
        workspace_name = tools.cleanup_colon(workspace_name)
    odev.workspace = Workspace.load_json(odev.paths.workspace_file(workspace_name))
    if odev.workspace:
        for repo_key, repo in odev.workspace.repos.items():
            if str(odev.paths.starting).startswith(str(odev.paths.relative('') / repo_key)):
                odev.repo = repo
                break
    return workspace_name


def workspaces_yield(incomplete: Optional[str] = None):
    return [workspace_name for workspace_name in odev.workspaces if workspace_name.startswith(workspace_name)]


def WorkspaceNameArgument(*args, default='last', **kwargs):
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
        Display all the available workspaces for current project.
    """
    print(f"{odev.paths.config / odev.project.name}/")
    for workspace_name in workspaces_yield():
        print(f"    {workspace_name}")


@odev.command()
def workspace(workspace_name: Optional[str] = WorkspaceNameArgument(), edit: bool = False):
    """
        Display currently selected workspace data.
    """
    if not odev.workspace:
        print(f"No workspace named '{workspace_name}' found")
        return

    workspace_file = odev.paths.workspace_file(odev.workspace.name)
    if not edit:
        print(f"{odev.workspace.name}::")
        print(f"    {'project_folder:':18} {odev.project.path}")
        print(f"    {'workspace_folder:':18} {odev.paths.workspace(odev.workspace.name)}")
        print(f"    {'workspace_file:':18} {odev.paths.workspace_file(odev.workspace.name)}")
        print(odev.workspace.to_json())
    else:
        editor = Git.get_editor()
        print(f"{editor} {workspace_file}")
        External.edit(editor, workspace_file)


@odev.command()
def workspace_set(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Change the current workspace without loading it
    """
    old_workspace_name = odev.project.last_used
    odev.project.last_used = workspace_name
    odev.projects.save()
    print(f"Current workspace changed: {old_workspace_name} -> {odev.workspace.name}")


@odev.command()
def workspace_bundle(
    ctx: Context,
    bundle_name: str = Argument(None, help="Bundle name"),
    load_workspace: bool = True
):
    """
        Creates a workspace from a Bundle on Runbot.
        If `load` is specified, it also loads generated workspace.
    """

    bundle_name = tools.cleanup_colon(bundle_name)
    if not (repo_names := Runbot.get_branches(bundle_name)):
        print(f"Bundle {bundle_name} not found")
        return
    base_branch = re.match(r"((?:saas-)?\d{1,2}\.\d)", bundle_name).group(0)

    modules = set()
    repos = {}
    for repo_name in set(main_repos) | set(repo_names):
        repo = copy.copy(template_repos[repo_name])
        repo_path = odev.paths.project / repo_name
        if repo_name in repo_names:
            repo.branch = bundle_name
            repo.remote = 'dev' if repo_name in have_dev_origin else 'origin'

            Git.fetch(repo_path, repo_name, 'origin', base_branch)
            if diffiles := Git.diff_with_merge_base(repo_path, f"origin/{base_branch}"):
                for diffile in diffiles:
                    if match := re.match(r"addons/([^/]+)/", diffile):
                        modules.add(match.group(1))
        else:
            repo.branch = base_branch
            repo.remote = 'origin'
        repos[repo_name] = repo

    modules_csv = ",".join(modules) if modules else None
    workspace = tools.workspace_prepare(
        bundle_name,
        repos=repos,
        modules_csv=modules_csv,
    )
    if not workspace:
        return

    if load_workspace:
        for repo_name, repo in repos.items():
            _checkout_repo(repo, force_create=True)

    tools.workspace_install(workspace)
    print(f"Workspace {workspace.name} has been created")

    if load_workspace:
        load(workspace.name)


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
def workspace_move(workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
                   dest_workspace_name: Optional[str] = Argument(None, help="Destination name")):
    """
        Renames a workspace.
    """
    if not dest_workspace_name:
        dest_workspace_name = (tools.input_text("What destination for your workspace?") or '').strip()

    if not tools.confirm(f"Rename {workspace_name} to {dest_workspace_name}"):
        return
    tools.move_workspace(workspace_name, dest_workspace_name)


@odev.command()
def workspace_delete(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Delete a workspace.
    """
    if not tools.confirm(f"delete {odev.paths.workspace(workspace_name)}"):
        return
    tools.delete_workspace(workspace_name)
    if odev.project.last_used == workspace_name:
        tools.set_last_used("master")


@odev.command()
def workspace_create(
    ctx: Context,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    db_name: Optional[str] = Argument(None, help=db_name_help),
    modules_csv: Optional[str] = Argument(None, help=modules_csv_help),
    venv_path: Optional[str] = Argument(None, help=venv_path_help),
    repos_csv: Optional[str] = Argument(None, help=repos_csv_help),
    load_workspace: bool = True
):
    """
        Create a new workspace from a series of selections.
    """

    if load_workspace and not status(extended=False):
        print("Cannot load, changes present.")
        return

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

    if load_workspace:
        load(workspace.name)

    return odev.workspace


# OPERATIONS ---------------------------------

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
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start(odev.paths.repo(odoo_repo),
               rc_fullpath,
               odev.paths.relative(odev.workspace.venv_path),
               odev.workspace.modules if not fast else [],
               options=options,
               pty=True,
               demo=demo,
               stop=stop)


@odev.command()
def load(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Load given workspace into the session.
    """
    if not status(extended=False, workspace_name=workspace_name):
        print("Cannot load, changes present.")
        return

    set_target_workspace(workspace_name)
    checkout(workspace_name)
    clean(workspace_name, quiet=True)

    tools.set_last_used(workspace_name)


@odev.command()
def clean(workspace_name: Optional[str] = WorkspaceNameArgument(), quiet: bool = False):
    """
        Git clean all repos
    """
    for _repo_name, repo in odev.workspace and odev.workspace.repos.items():
        Git.clean(odev.paths.repo(repo), quiet=quiet)


@odev.command()
def shell(interface: Optional[str] = Argument("ipython", help="Type of shell interface (ipython|ptpython|bpython)"),
          startup_script: Optional[str] = Option(None, help="Startup Python script to initialize the Shell"),
          workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Starts Odoo as an interactive shell.
    """
    interface = f'--shell-interface={interface}' if interface else ''
    startup_vars = f'PYTHONSTARTUP={startup_script}' if startup_script else ''
    rc_fullpath = odev.paths.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start(odev.paths.repo(odoo_repo),
               rc_fullpath,
               odev.paths.relative(odev.workspace.venv_path),
               None, options=interface, mode='shell', pty=True,
               env_vars=startup_vars)


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

    # Clone the base repos and set the 'dev' remote
    for repo_name, repo in tools.select_repositories("setup", None, checked=main_repos).items():
        path = odev.paths.repo(repo)

        clone_path = path

        if not clone_path.exists():
            print(f"creating path {clone_path}...")
            paths.ensure(clone_path)

        if not list(clone_path.glob("*")):
            print(f"cloning {repo_name} in {clone_path}...")
            Git.clone(repo.origin, repo.branch, clone_path)
            Git.add_remote('dev', repo.dev, clone_path)

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
        path = odev.paths.repo(repo)
        if not path.is_dir():
            print(f"Repository {repo_name} hasn't been cloned yet.")
            continue
        ret = Git.status(path, extended=extended, name=repo_name)
        if not extended and ret.stdout:
            return False
    return True


@odev.command()
def push(force: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-pushes multiple repositories.
    """
    for repo_name in tools.select_repositories("push", odev.workspace):
        print(f"Pushing {repo_name}...")
        repo = odev.workspace.repos[repo_name]
        Git.push(odev.paths.repo(repo), force=force)


@odev.command()
def diff(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-diffs all repositories.
    """
    for repo_name in odev.workspace.repos:
        repo = odev.workspace.repos[repo_name]
        Git.diff(odev.paths.repo(repo), repo_name)


@odev.command()
def fetch(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-fetches multiple repositories.
    """
    workspace = odev.workspace if not origin else None
    for repo_name, repo in tools.select_repositories("fetch", workspace, checked=main_repos).items():
        print(f"Fetching {repo_name}...")
        path = odev.paths.repo(repo)
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
        Git.pull(odev.paths.repo(repo), repo.remote, repo.branch)


def _checkout_repo(repo, force_create=False):
    path = odev.paths.repo(repo)
    target = f"{repo.name} {repo.remote}/{repo.branch}"
    try:
        print(f"Fetching {target}...")
        Git.fetch(path, repo.name, repo.remote, repo.branch)
    except UnexpectedExit:
        if not force_create:
            raise
        print(f"Creating {target}...")
        Git.checkout(path, repo.branch, options="-B")
    print(f"Checking out {target}...")
    Git.checkout(path, repo.branch)


@odev.command()
def checkout(workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
             force_create: bool = False):
    """
        Git-checkouts multiple repositories.
    """
    repos = (odev.workspace and odev.workspace.repos)
    for repo_name, repo in repos.items():
        print(f"Checkout repo {repo_name} branch {repo.branch}...")
        _checkout_repo(repo, force_create=force_create)
    return repos


@odev.command()
def update(ctx: Context, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Updates given workspace and reloads the current one.
    """
    last_used = odev.project.last_used
    repos = checkout(workspace_name)
    for repo_name, repo in repos.items():
        print(f"Updating repo {repo_name}...")
        Git.pull(odev.paths.repo(repo), repo.remote, repo.branch)

    set_target_workspace(last_used)
    load(last_used)


# Files  ------------------------------------------------------------

@odev.command()
def hook(subcommand: Optional[str] = Argument(help="Action to be taken (show, name, edit, run, copy)", default="show"),
         workspace_name: Optional[str] = WorkspaceNameArgument(),
         copy_dest: Optional[str] = Argument(help="Copy's workspace destination", default=None)):
    """
        Display or edit the post_hook python file.
    """
    def hook_fullpath(workspace=None):
        workspace = workspace or odev.workspace
        return odev.paths.workspace(workspace.name) / Path(workspace.post_hook_script)
    subcommand = subcommand.lower()
    if subcommand == 'name':
        print(hook_fullpath())
    elif subcommand == 'edit':
        External.edit(Git.get_editor(), hook_fullpath())
    elif subcommand == 'run':
        rc_fullpath = odev.paths.relative(odev.workspace.rc_file)
        Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
        odoo_repo = odev.workspace.repos['odoo']
        Odoo.start(odev.paths.repo(odoo_repo),
                   rc_fullpath,
                   odev.paths.relative(odev.workspace.venv_path),
                   None, ' < ' + str(hook_fullpath()),
                   'shell')
    elif subcommand == 'copy':
        src_fullpath = hook_fullpath(odev.workspace)
        if (dest_workspace_path := Path(odev.paths.workspace_file(copy_dest))) and dest_workspace_path.exists():
            dest_fullpath = hook_fullpath(Workspace.load_json(dest_workspace_path))
        else:
            dest_fullpath = odev.paths.hook_file(copy_dest)
            paths.ensure(dest_fullpath.parent)
        print(f"cp {src_fullpath} {dest_fullpath}")
        shutil.copyfile(src_fullpath, dest_fullpath)
    else:
        tools.cat(hook_fullpath())


@odev.command()
def rc(workspace_name: Optional[str] = WorkspaceNameArgument(), edit: bool = False):
    """
        View or edit the .odoorc config with default editor.
    """
    rc_fullpath = odev.paths.project / Path(odev.workspace.rc_file)
    if edit:
        External.edit(Git.get_editor(), rc_fullpath)
    else:
        tools.cat(rc_fullpath)


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
            workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Run upgrade from a old Workspace to a new Workspace
        ex. ocli upgrade 15.0 15.0-account-myfix
    """

    if not status(extended=False):
        print("Cannot upgrade, changes present.")
        return

    odoo_path = odev.paths.repo(odev.workspace.repos['odoo'])
    upgrade_path = odev.paths.repo(odev.workspace.repos['upgrade']) / 'migrations'
    upgrade_util_path = odev.paths.repo(odev.workspace.repos['upgrade-util']) / 'src'
    upgrade_options = f'--upgrade-path={upgrade_util_path},{upgrade_path} -u all --test-enable --test-tags=at_install,-post_install'

    print(f"Upgrading {old_workspace_name} -> {workspace_name}")
    print(f"Loading {old_workspace_name}...")
    load(old_workspace_name)
    db_init(old_workspace_name, demo=True, stop=True, post_init_hook=False)

    print(f"Loading {workspace_name}...")
    load(workspace_name)
    print("Cleaning old folders that might have old files")
    Git.clean(odoo_path, quiet=True)

    start(odoo_path, options=upgrade_options, demo=True)


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
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

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
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(odev.workspace.modules))
    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start_tests(odev.paths.repo(odoo_repo),
                     rc_fullpath,
                     odev.paths.relative(odev.workspace.venv_path),
                     odev.workspace.modules if not fast else [],
                     tags)


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
    odoo_repo = odev.workspace.repos['odoo']
    odoo_path = odev.paths.repo(odoo_repo)

    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=['base'],
               options=options,
               demo=demo,
               stop=True)

    modules = (modules_csv and modules_csv.split(',')) or odev.workspace.modules
    print('Installing modules %s ...', ','.join(modules))
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=modules,
               options=options,
               demo=demo,
               stop=True)

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
            odoo_path,
            rc_fullpath,
            venv_path,
            modules=None,
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
        Odoo.start(odoo_path, rc_fullpath, venv_path, modules=None, options=options, stop=stop)


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
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    odoo_repo = odev.workspace.repos['odoo']
    Odoo.start_tests(odev.paths.repo(odoo_repo),
                     rc_fullpath,
                     odev.paths.relative(odev.workspace.venv_path),
                     ['test_lint'],
                     "/test_lint")


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
            if repo.addons_folders:
                for folder in repo.addons_folders:
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
