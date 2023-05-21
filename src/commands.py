#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from pathlib import Path
from typing import Optional

import copy
import os
import sys
import json
import ast
import itertools

import paths
import shutil
import tools
import fileinput
import click
from typer import Argument, Context

from rc import Rc
from external import External
from git import Git
from gh import Gh
from pgsql import PgSql
from odev import odev
from env import Environment
from templates import template_repos, main_repos, post_hook_template
from project import Projects
from workspace import Workspace

from odoo import Odoo


# Help strings -----------------------------------

extra_help = "Additional command line parameters"
db_name_help = "Name of the database"
project_name_help = "Name of the project (md5 of the path)"
modules_csv_help = "CSV list of modules"
venv_path_help = "Virtualenv path"
repos_csv_help = "CSV list of repositories"
workspace_name_help = "Name of the workspace that holds the database information, omit to use current"


# Gh ---------------------------------------------

def ensure_gh():
    if not Gh.exists():
        print("GitHub CLI is not installed, this function is therefore disabled.")
        print("Visit https://cli.github.com/manual/installation for more information.")
        sys.exit(0)


# Project ----------------------------------------

@odev.command()
def projects(edit: bool = False):
    """
        Display all the available project folders.
    """
    if edit:
        editor = Git.get_editor()
        External.edit(editor, odev.paths.projects)
        return
    for _name, project in odev.projects.items():
        print(f"{project.path}  {project.name}  {odev.paths.workspaces / project.name}")

@odev.command()
def project():
    """
        Display project data for the current folder.
    """
    print(f"{odev.project.name}:: {odev.project.to_json()}")


def project_delete(project_name: Optional[str] = Argument(None, help=project_name_help)):
    """
        Delete a project.
    """
    project = tools.select_project("delete", project_name)
    if not project or not tools.confirm("delete it"):
        return
    tools.delete_project(project.name)


# Workspace ------------------------------------------------

def set_workspace_name(workspace_name: str):
    if odev.worktree:
        # current_path = str(paths.current())
        # project_path = str(self.project.path)
        # if str(current_path).startswith(project_path):
        #     rest = current_path[len(project_path):]
        #     if rest in sorted(paths.workspaces().iterdir()):
        #         workspace_name = rest
        pass
    # If it's autocomplete, don't ask
    if click.get_current_context().parent.invoked_subcommand is None:
        return
    if not workspace_name:
        workspace_name = tools.select_workspace("select (default=last)", odev.project)
    elif workspace_name == 'last':
        workspace_name = odev.project.last_used
    else:
        workspace_name = tools.cleanup_workspace_name(workspace_name)
    odev.workspace = Workspace.load_json(odev.paths.workspace_file(workspace_name))
    return workspace_name


def workspaces_yield(ctx: Context, incomplete: str = None):
    return [workspace_name for workspace_name in odev.workspaces if workspace_name.startswith(workspace_name)]


def WorkspaceNameArgument(*args, default='last', **kwargs):
    return Argument(*args, **{
        **kwargs,
        'help': workspace_name_help,
        'callback': set_workspace_name,
        'default': default,
        'autocompletion': workspaces_yield,
    })


@odev.command()
def workspaces():
    """
        Display all the available workspaces for current project.
    """
    print(f"{odev.project.name}::")
    for workspace_name in dict(workspaces_yield):
        print(f"    {workspace_name}")


@odev.command()
def workspace(workspace_name: Optional[str] = WorkspaceNameArgument(), edit: bool = False):
    """
        Display currently selected workspace data.
    """
    workspace_file = odev.paths.workspace_file(odev.workspace.name)

    print(f"{odev.workspace.name}::")
    print(f"    {'project_folder:':18} {odev.project.path}")
    print(f"    {'workspace_folder:':18} {odev.paths.workspace(odev.workspace.name)}")
    print(f"    {'workspace_file:':18} {odev.paths.workspace_file(odev.workspace.name)}")
    if not edit:
        print(odev.workspace.to_json())
        return

    editor = Git.get_editor()
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
def workspace_from_pr(ctx: Context, pr_number: int = Argument(None, help="PR number"), load_workspace: bool = False):
    """
        Requires `gh` to be installed (Github CLI)
        Creates a workspace from a PR number on odoo/odoo or odoo/enterprise.
        If `load` is specified, it also loads generated workspace.
    """
    ensure_gh()

    main_owner, dev_owner = 'odoo', 'odoo-dev'
    coros_dict = {name: Gh.get_pr_info(main_owner, name, pr_number) for name in template_repos}
    result = tools.await_first_result(coros_dict)
    if not result:
        print(f"PR {pr_number} not found")
        return

    repo_name, info = result[0], json.loads(result[1])
    branch = info['head']['ref']
    title = info['title']
    base_ref = info['base']['ref']

    print(f"{repo_name}#{pr_number}   {title} ({branch})")

    repos_to_search = [x for x in template_repos if x != repo_name]
    coros_dict = {name: Gh.get_branch_info(dev_owner, name, branch) for name in repos_to_search}
    result = tools.await_all_results(coros_dict)
    repo_names = [repo_name] + [other_repo_name for other_repo_name in result]
    print(f"Branch '{branch}' has been found in {repo_names}")

    default_db_name = odev.projects.defaults.get("db_name")
    print(f"Default db name: '{default_db_name}'")

    workspace = workspace_create(
         ctx,
         workspace_name=branch,
         db_name=default_db_name,
         venv_path=None,
         modules_csv=None,
         repos_csv=",".join(repo_names))
    if not workspace:
        return

    missing_repos = {missing_repo for missing_repo in main_repos if missing_repo not in repo_names}
    for repo_name, repo in workspace.repos.items():
        repo.remote = 'dev'
        repo.branch = branch
    for missing_repo in missing_repos:
        new_repo = copy.copy(template_repos[missing_repo])
        new_repo.remote = 'origin'
        new_repo.branch = base_ref
        workspace.repos[missing_repo] = new_repo
    workspace.save_json(paths.workspace_file(workspace.name))
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
    dest_workspace_name = tools.cleanup_workspace_name(dest_workspace_name)
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

    set_workspace_name(dest_workspace_name)
    workspace(dest_workspace_name, edit=True)
    if _load:
        load(dest_workspace_name)

@odev.command()
def workspace_delete(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Delete a workspace.
    """
    if not tools.confirm(f"delete {odev.paths.workspace(workspace_name)}"):
        return
    tools.delete_workspace(workspace_name)
    if odev.project.last_used == workspace_name:
        tools.set_last_used(odev.project.name)


@odev.command()
def workspace_create(
        ctx: Context,
        workspace_name: Optional[str] = WorkspaceNameArgument(),
        db_name: Optional[str] = Argument(None, help=db_name_help),
        modules_csv: Optional[str] = Argument(None, help=modules_csv_help),
        venv_path: Optional[str] = Argument(None, help=venv_path_help),
        repos_csv: Optional[str] = Argument(None, help=repos_csv_help)
    ):
    """
        Create a new workspace from a series of selections.
    """
    if not workspace_name:
        workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
    if not workspace_name:
        return
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    if workspace_name in odev.workspaces + ['last_used']:
        print(f"Workspace {workspace_name} is empty or already exists")
        return
    if not db_name:
        db_name = (tools.input_text("What database name to use?") or '').strip()
    if not db_name:
        return
    if not modules_csv:
        modules_csv = tools.input_text("What modules to use? (CSV)").strip()
    if not modules_csv:
        return
    if not repos_csv:
        set_workspace_name(workspace_name)
        repos = checkout(workspace_name)
        if not repos:
            return
    else:
        repos = {repo_name: template_repos[repo_name] for repo_name in repos_csv.split(',')}

    tools.create_workspace(workspace_name, db_name, modules_csv, repos)

    # If this function was used as a command, also checkout the branches
    if ctx.command.name == 'workspace-create':
        for repo_name, repo in repos.items():
            print(f"Checking out {repo_name} {repo.remote}/{repo.branch}...")
            Git.checkout(odev.project.relative(repo_name), repo.branch)
            print(f"Creating branch {repo_name} {workspace_name}...")
            Git.checkout(odev.project.relative(repo_name), workspace_name, options = '-b')
        tools.set_last_used(odev.project.name, workspace_name)
        workspace_file = paths.workspace_file(workspace_name)
        with fileinput.FileInput(workspace_file, inplace=True, backup='.bak') as f:
            for line in f:
                if repo.branch in line and "branch" in line:
                    print(f'{line.rstrip()} # "{workspace_name}",')
                elif 'remote' in line and not '"dev"' in line:
                    print(f'{line.rstrip()} # "dev",')
                else:
                    print(line, end="")

    return odev.workspace


# OPERATIONS ---------------------------------

@odev.command()
def start(workspace_name: Optional[str] = WorkspaceNameArgument(),
          fast: bool = False,
          demo: bool = False,
          options: str = None):
    """
        Start Odoo and reinitialize the workspace's modules.
    """
    options = options or ''
    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

    Odoo.start(odev.project.relative('odoo'),
               rc_fullpath,
               odev.project.relative(odev.workspace.venv_path),
               odev.workspace.modules if not fast else [],
               options=options,
               pty=True,
               demo=demo)


@odev.command()
def load(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Load given workspace into the session.
    """
    if not status(extended=False):
        print("Cannot load, changes present.")
        return

    set_workspace_name(workspace_name)
    checkout(workspace_name)

    odev.project.last_used = workspace_name
    odev.projects.save()


@odev.command()
def shell(interface: Optional[str] = Argument("python", help="Type of shell interface (ipython|ptpython|bpython)"),
          workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Starts Odoo as an interactive shell.
    """
    interface = f'--shell-interface={interface}' if interface else ''
    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    Odoo.start(odev.project.relative('odoo'),
               rc_fullpath,
               odev.project.relative(odev.workspace.venv_path),
               None, options=interface, mode='shell', pty=True)


@odev.command()
def setup(db_name, worktree: bool = False):
    """
        Sets up the main folder, with repos and venv.
    """
    # Prepare the Projects file
    paths.ensure(paths.config())
    if not odev.projects:
        paths.ensure(odev.paths.projects)
        defaults = dict(db_name=db_name, worktree=worktree)
        projects = Projects(defaults=defaults)
        projects.save()

    paths.ensure(paths.workspaces())

    # Clone the base repos and set the 'dev' remote
    for repo_name, repo in tools.select_repositories("setup", None, checked=main_repos).items():
        repo_path = odev.project.relative(repo_name)

        # Clone the repo
        if repo_path.exists():
            print(f"{repo_name} already exists...")
        else:
            print(f"cloning {repo_name}...")
            paths.ensure(repo_path)
            Git.clone(repo.origin, repo.branch, repo_path)
            Git.add_remote('dev', repo.dev, repo_path)
            _setup_requisites(odev.project.relative('.venv'),
                              added=['ipython', 'pylint'],
                              reqs_file=f"{repo_name}/requirements.txt")

        workspace_name = 'master'
        workspace_file = paths.workspace_file(workspace_name)
        workspace_path = paths.workspace(workspace_name)

        # Create the master workspace
        if not workspace_file.exists():
            print(f"Creating workspace {workspace_file}...")
            repos = {k: v for k, v in template_repos.items() if k in main_repos}
            new_workspace = Workspace( workspace_name, db_name, repos, ['base'], 'master.dmp', 'post_hook.py', '.venv', '.odoorc')
            paths.ensure(workspace_path)
            new_workspace.save_json(workspace_file)
        else:
            print(f"{workspace_file} workspace already exists...")

        # Create the post_hook script
        post_hook_path = workspace_path / "post_hook.py"
        if not post_hook_path.exists():
            print(f"Creating {post_hook_path} post_hook script...")
            with open(post_hook_path, "w", encoding="utf-8") as post_hook_file:
                post_hook_file.write(post_hook_template)
        else:
            print(f"{post_hook_path} already exists...")


def _setup_requisites(venv_path, added=None, reqs_file=None):
    venv_path = Path(venv_path)
    exists = venv_path.exists()
    paths.ensure(venv_path)
    env = Environment(venv_path)
    if not exists:
        env.create()
    added = added or []
    with env:
        print("installing pip...")
        env.context.run("pip install --upgrade pip")
        if reqs_file and Path(reqs_file).exists():
            print(f"installing {reqs_file}")
            env.context.run(f"pip install -r {reqs_file}")
        for module in added:
            env.context.run(f"pip install --upgrade {module}")


# Git ---------------------------------------------------
@odev.command()
def status(extended: bool = True, workspace_name: Optional[str] = WorkspaceNameArgument(default='last')):
    """
        Display status for all repos for current workspace.
    """
    print(f"{odev.project.path} - {odev.workspace.name}")
    for name in odev.workspace.repos:
        repo_path = Path(odev.project.path) / name
        if not repo_path.is_dir():
            print(f"Repository {name} hasn't been cloned yet.")
            continue
        ret = Git.status(repo_path, extended=extended, name=name)
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
        Git.push(odev.project.relative(repo_name), force=force)


@odev.command()
def diff(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-diffs all repositories.
    """
    for repo_name in odev.workspace.repos:
        Git.diff(odev.project.path, repo_name)


@odev.command()
def fetch(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-fetches multiple repositories.
    """
    workspace = odev.workspace if not origin else None
    for repo_name, repo in tools.select_repositories("fetch", workspace, checked=main_repos).items():
        print(f"Fetching {repo_name}...")
        if origin:
            Git.fetch(odev.project.path, repo_name, "origin", "")
        else:
            Git.fetch(odev.project.path, repo_name, repo.remote, repo.branch)


@odev.command()
def pull(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-pulls selected repos for current workspace.
    """
    for repo_name in tools.select_repositories("pull", odev.workspace, checked=main_repos):
        print(f"Pulling {repo_name}...")
        repo = odev.workspace.repos[repo_name]
        Git.pull(odev.project.relative(repo_name), repo.remote, repo.branch)

@odev.command()
def checkout(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Git-checkouts multiple repositories.
    """
    repos = odev.workspace.repos or tools.select_repos_and_branches(odev.project, "checkout", odev.workspace)
    for repo_name, repo in repos.items():
        print(f"Fetching {repo_name} {repo.remote}/{repo.branch}...")
        Git.fetch(odev.project.path, repo_name, repo.remote, repo.branch)
        print(f"Checking out {repo_name} {repo.remote}/{repo.branch}...")
        Git.checkout(odev.project.relative(repo_name), repo.branch)

    return repos

@odev.command()
def update(ctx: Context, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Updates given workspace and reloads the current one.
    """
    last_used = odev.project.last_used
    repos = checkout(workspace_name)
    for _repo_name, repo in repos.items():
        Git.pull(odev.project.relative(repo.name), repo.remote, repo.branch)

    set_workspace_name(last_used)
    load(last_used)

# FILES ------------------------------------------------------------

@odev.command()
def hook(workspace_name: Optional[str] = WorkspaceNameArgument(),
         name: bool = False,
         edit: bool = False,
         run: bool = False):
    """
        Display or edit the post_hook python file.
    """
    hook_fullpath = odev.paths.workspace(workspace_name) / Path(odev.workspace.post_hook_script)
    if name:
        print(hook_fullpath)
        return
    if edit:
        External.edit(Git.get_editor(), hook_fullpath)
        return
    if run:
        rc_fullpath = odev.project.relative(odev.workspace.rc_file)
        Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
        Odoo.start(odev.project.relative('odoo'),
                   rc_fullpath,
                   odev.project.relative(odev.workspace.venv_path),
                   None, ' < ' + str(hook_fullpath),
                   'shell')
        return
    tools.cat(hook_fullpath)


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


# DB ------------------------------------------------------------

@odev.command()
def db_clear(db_name: Optional[str] = Argument(None, help="Database name"), workspace_name: Optional[str] = WorkspaceNameArgument()):
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
def l10n_tests(fast: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Run l10n tests
    """

    # Eventually erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db_clear(odev.workspace.db_name)

    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

    Odoo.l10n_tests(odev.project.relative('odoo'),
                    odev.workspace.db_name,
                    odev.project.relative(odev.workspace.venv_path))
    # /data/build/odoo/odoo/tests/test_module_operations.py -d 17105465-15-0-l10n_account --data-dir /data/build/datadir --addons-path odoo/addons,odoo/odoo/addons,enterprise --standalone all_l10n


def _tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False):
    """
        Generic test function for all commands.
    """
    # Erase the database
    if not fast:
        print(f'Erasing {odev.workspace.db_name}...')
        db_clear(odev.workspace.db_name)

    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(odev.workspace.modules))
    Odoo.start_tests(odev.project.relative('odoo'),
                     rc_fullpath,
                     odev.project.relative(odev.workspace.venv_path),
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
def db_init(workspace_name: Optional[str] = WorkspaceNameArgument(),
            options: str = None,
            dump_before: bool = False,
            dump_after: bool = False,
            demo: bool = False,
            stop: bool = False):
    """
         Initialize the database, with modules and hook.
    """
    options = options or ''

    # Erase the database
    print(f'Erasing {odev.workspace.db_name}...')
    db_clear(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    venv_path = odev.project.relative(odev.workspace.venv_path)
    odoo_path = odev.project.relative('odoo')
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=['base'],
               options=f'{options} --stop-after-init',
               demo=demo)

    print('Installing modules %s ...', ','.join(odev.workspace.modules))
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=odev.workspace.modules,
               options=f'{options} --stop-after-init',
               demo=demo)

    # Dump the db before the hook if the user has specifically asked for it
    if dump_before:
        db_dump(workspace_name)

    print('Executing post_init_hook...')
    hook_path = odev.paths.workspace(odev.workspace.name) / odev.workspace.post_hook_script
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=None,
               options=f'{options} --stop-after-init < {hook_path}',
               mode='shell',
               demo=demo)

    # Dump the db after the hook if the user has specifically asked for it
    if dump_after:
        db_dump(workspace_name)

    if not stop:
        print('Starting Odoo...')
        Odoo.start(odoo_path, rc_fullpath, venv_path, modules=None, options=options)


# Venv -----------------------------------------------------------

@odev.command()
def activate_path(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Path to the activate script for the current virtual environment.
    """
    activate_path = Path(odev.project.path).joinpath(odev.workspace.venv_path, "bin", "activate")
    print(activate_path)


# Hub ------------------------------------------------------------

@odev.command()
def hub(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Open Github in a browser on a branch of a given repo.
    """
    tools.open_hub(odev.project, odev.workspace)


# Lint -----------------------------------------------------------

@odev.command()
def lint(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Open Github in a browser on a branch of a given repo.
    """
    print("Pylint checking...")
    rc_fullpath = odev.project.relative(odev.workspace.rc_file)
    Rc(rc_fullpath).check_db_name(odev.workspace.db_name)
    Odoo.start_tests(odev.project.relative('odoo'),
                     rc_fullpath,
                     odev.project.relative(odev.workspace.venv_path),
                     ['test_lint'],
                     "/test_lint")


# Runbot ---------------------------------------------------------

@odev.command()
def runbot(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Open runbot in a browser for current bundle.
    """
    tools.open_runbot(odev.project, odev.workspace)


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
                    folders.append(str(odev.project.relative(repo_name) / Path(folder)))

        fullpaths = [os.path.join(x, current, y)
                     for x, y in itertools.product(folders, manifest_names)]

        for fullpath in fullpaths:
            if os.path.isfile(fullpath):
                with open(fullpath, encoding="utf-8") as f:
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
