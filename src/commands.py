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
from rc import Rc
from external import External
from git import Git
from gh import Gh
from pgsql import PgSql
from env import Environment
from templates import template_repos, main_repos, post_hook_template
from typer import Argument, Typer, Context
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


# Commands ---------------------------------------

odev = Typer()


# Project ----------------------------------------

@odev.command()
def projects(edit: bool = False):
    """
        Display all the available project folders.
    """
    if edit:
        editor = Git.get_editor()
        External.edit(editor, paths.projects())
        return
    projects = tools.get_projects()
    if projects:
        for _name, project in projects.items():
            print(f"{project.path}  {project.name}  {paths.config() / 'workspaces' / project.name}")


@odev.command()
def project():
    """
        Display project data for the current folder.
    """
    project = tools.get_project()
    if project:
        print(f"{project.name}:: {project.to_json()}")


def project_delete(project_name: Optional[str] = Argument(None, help=project_name_help)):
    """
        Delete a project.
    """
    project = tools.select_project("delete", project_name)
    if not project or not tools.confirm("delete it"):
        return
    tools.delete_project(project.name)


# Workspace ------------------------------------------------


def workspaces_yield(incomplete: str = ''):
    project = tools.get_project()
    if project:
        return [(workspace_name, workspace_name) for workspace_name in tools.get_workspaces(project)
                                                 if workspace_name.startswith(incomplete)]


def WorkspaceNameArgument(*args, default=None, **kwargs):
    kwargs['help'] = workspace_name_help
    kwargs['autocompletion'] = workspaces_yield
    return Argument(default, *args, **kwargs)


@odev.command()
def workspaces():
    """
        Display all the available workspaces for current project.
    """
    project = tools.get_project()
    if project:
        print(f"{project.name}::")
    for workspace_name in dict(workspaces_yield()):
        print(f"    {workspace_name}")


@odev.command()
def workspace(workspace_name: Optional[str] = WorkspaceNameArgument(), edit: bool = False):
    """
        Display currently selected workspace data.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    if not workspace:
        print("No workspace found")
        return
    workspace_file = paths.workspace_file(workspace.name)

    print(f"{workspace.name}::")
    print(f"    {'project_folder:':18} {project.path}")
    print(f"    {'workspace_folder:':18} {paths.workspace(workspace.name)}")
    print(f"    {'workspace_file:':18} {paths.workspace_file(workspace.name)}")
    if not edit:
        print(workspace.to_json())
        return

    editor = Git.get_editor()
    External.edit(editor, workspace_file)


@odev.command()
def workspace_set(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Change the current workspace without loading it
    """
    project = tools.get_project()
    old_workspace = tools.get_workspace(project)
    if not workspace_name:
        workspace_name = tools.select_workspace("set as current", project)
        if not workspace_name:
            return
    workspace_name = tools.cleanup_workspace_name(workspace_name)

    tools.set_last_used(project.name, workspace_name=workspace_name)
    print(f"Current workspace changed: {old_workspace.name} -> {workspace_name}")


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

    projects = tools.get_projects()
    default_db_name = projects.defaults.get("db_name")
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
def workspace_dupe(workspace_name: Optional[str] = WorkspaceNameArgument(),
                   dest_workspace_name: Optional[str] = Argument(None, help="Destination name"),
                   _load: bool = False):
    """
        Duplicate a workspace.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("copy", project)
        if not workspace_name:
            return
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    if not dest_workspace_name:
        dest_workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
        if not dest_workspace_name:
            return
    dest_workspace_name = tools.cleanup_workspace_name(dest_workspace_name)
    sourcepath, destpath = paths.workspace(workspace_name), paths.workspace(dest_workspace_name)
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
    workspace(dest_workspace_name, edit=True)
    if _load:
        load(dest_workspace_name)

@odev.command()
def workspace_delete(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Delete a workspace.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("delete", project)
        if not workspace_name:
            return
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    if not tools.confirm(f"delete {paths.workspace(workspace_name)}"):
        return
    tools.delete_workspace(workspace_name)
    if project.last_used == workspace_name:
        tools.set_last_used(project.name)


@odev.command()
def workspace_create(
        ctx: Context,
        workspace_name: Optional[str] = Argument(None, help=workspace_name_help, autocompletion=workspaces_yield),
        db_name: Optional[str] = Argument(None, help=db_name_help),
        modules_csv: Optional[str] = Argument(None, help=modules_csv_help),
        venv_path: Optional[str] = Argument(None, help=venv_path_help),
        repos_csv: Optional[str] = Argument(None, help=repos_csv_help)
    ):
    """
        Create a new workspace from a series of selections.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
    if not workspace_name:
        return
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    if workspace_name in tools.get_workspaces(project) + ['last_used']:
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
            Git.checkout(project.relative(repo_name), repo.branch)
            print(f"Creating branch {repo_name} {workspace_name}...")
            Git.checkout(project.relative(repo_name), workspace_name, options = '-b')
        tools.set_last_used(project.name, workspace_name)
        workspace_file = paths.workspace_file(workspace_name)
        with fileinput.FileInput(workspace_file, inplace=True, backup='.bak') as f:
            for line in f:
                if repo.branch in line and "branch" in line:
                    print(f'{line.rstrip()} # "{workspace_name}",')
                elif 'remote' in line and not '"dev"' in line:
                    print(f'{line.rstrip()} # "dev",')
                else:
                    print(line, end="")

    return tools.get_workspace(project, workspace_name)


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
    project = tools.get_project()
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    workspace = tools.get_workspace(project, workspace_name)
    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start(project.relative('odoo'),
               rc_fullpath,
               project.relative(workspace.venv_path),
               workspace.modules if not fast else [],
               options=options,
               pty=True,
               demo=demo)


@odev.command()
def load(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Load given workspace into the session.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("load", project)
        if not workspace_name:
            return
    workspace_name = tools.cleanup_workspace_name(workspace_name)
    if not status(extended=False):
        print("Cannot load, changes present.")
        return
    checkout(workspace_name)
    tools.set_last_used(project.name, workspace_name)


@odev.command()
def shell(interface: Optional[str] = Argument("python", help="Type of shell interface (ipython|ptpython|bpython)"),
          workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Starts Odoo as an interactive shell.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    interface = f'--shell-interface={interface}' if interface else ''
    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start(project.relative('odoo'),
               rc_fullpath,
               project.relative(workspace.venv_path),
               None, options=interface, mode='shell', pty=True)


@odev.command()
def setup(db_name):
    """
        Sets up the main folder, with repos and venv.
    """
    paths.ensure(paths.config())
    projects_path = Path(paths.projects())
    if not projects_path.exists():
        with open(projects_path, "w", encoding="UTF-8") as projects_file:
            projects_file.write("{\n}")
    paths.ensure(paths.workspaces())

    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Clone the base repos and set the 'dev' remote
    for repo_name, repo in tools.select_repositories("setup", workspace, checked=main_repos).items():
        repo_path = project.relative(repo_name)

        if repo_path.exists():
            print(f"{repo_name} already exists...")
        else:
            print(f"cloning {repo_name}...")
            paths.ensure(repo_path)
            Git.clone(repo.origin, repo.branch, repo_path)
            Git.add_remote('dev', repo.dev, repo_path)
            _setup_requisites(project.relative('.venv'),
                              added=['ipython', 'pylint'],
                              reqs_file=f"{repo_name}/requirements.txt")

        workspace_name = 'master'
        workspace_file = paths.workspace_file(workspace_name)
        workspace_path = paths.workspace(workspace_name)
        if workspace_file.exists():
            print(f"{workspace_file} workspace already exists...")
        else:
            new_workspace = Workspace(
                workspace_name,
                db_name,
                {k: v for k, v in template_repos.items() if k in main_repos},
                ['base'],
                'master.dmp',
                'post_hook.py',
                '.venv',
                '.odoorc')
            paths.ensure(workspace_path)
            new_workspace.save_json(workspace_file)

        post_hook_path = workspace_path / "post_hook.py"
        if not post_hook_path.exists():
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
def status(extended: bool = True):
    """
        Display status for all repos for current workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    if not workspace:
        return True
    print(f"{project.path} - {workspace.name}")
    for name in workspace.repos:
        repo_path = Path(project.path) / name
        if not repo_path.is_dir():
            print(f"Repository {name} hasn't been cloned yet.")
            continue
        ret = Git.status(repo_path, extended=extended, name=name)
        if not extended and ret.stdout:
            return False
    return True


@odev.command()
def push(force: bool = False):
    """
        Git-pushes multiple repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in tools.select_repositories("push", workspace):
        print(f"Pushing {repo_name}...")
        Git.push(project.relative(repo_name), force=force)


@odev.command()
def diff(origin: bool = False):
    """
        Git-diffs all repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in workspace.repos:
        Git.diff(project.path, repo_name)


@odev.command()
def fetch(origin: bool = False):
    """
        Git-fetches multiple repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name, repo in tools.select_repositories("fetch", workspace, checked=main_repos).items():
        print(f"Fetching {repo_name}...")
        if origin:
            Git.fetch(project.path, repo_name, "origin", "")
        else:
            Git.fetch(project.path, repo_name, repo.remote, repo.branch)


@odev.command()
def pull():
    """
        Git-pulls selected repos for current workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in tools.select_repositories("pull", workspace, checked=main_repos):
        print(f"Pulling {repo_name}...")
        repo = workspace.repos[repo_name]
        Git.pull(project.relative(repo_name), repo.remote, repo.branch)

@odev.command()
def checkout(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-checkouts multiple repositories.
    """
    project = tools.get_project()
    repos = None
    workspace = None
    if workspace_name:
        workspace = tools.get_workspace(project, workspace_name)
        if workspace:
            repos = workspace.repos

    repos = repos or tools.select_repos_and_branches(project, "checkout", workspace)

    for repo_name, repo in repos.items():
        print(f"Fetching {repo_name} {repo.remote}/{repo.branch}...")
        Git.fetch(project.path, repo_name, repo.remote, repo.branch)
        print(f"Checking out {repo_name} {repo.remote}/{repo.branch}...")
        Git.checkout(project.relative(repo_name), repo.branch)

    return repos

@odev.command()
def update(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Updates given workspace and reloads the current one.
    """
    project = tools.get_project()
    last_used = project.last_used

    repos = checkout(workspace_name)
    for _repo_name, repo in repos.items():
        Git.pull(project.relative(repo.name), repo.remote, repo.branch)
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
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    hook_fullpath = paths.workspace(workspace.name) / workspace.post_hook_script
    if name:
        print(hook_fullpath)
        return
    if edit:
        External.edit(Git.get_editor(), hook_fullpath)
        return
    if run:
        rc_fullpath = project.relative(workspace.rc_file)
        Rc(rc_fullpath).check_db_name(workspace.db_name)
        Odoo.start(project.relative('odoo'),
                   rc_fullpath,
                   project.relative(workspace.venv_path),
                   None, ' < ' + str(hook_fullpath),
                   'shell')
        return
    tools.cat(hook_fullpath)


@odev.command()
def rc(workspace_name: Optional[str] = WorkspaceNameArgument(), edit: bool = False):
    """
        View or edit the .odoorc config with default editor.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    rc_fullpath = paths.current() / workspace.rc_file
    if edit:
        External.edit(Git.get_editor(), rc_fullpath)
    else:
        tools.cat(rc_fullpath)


# DB ------------------------------------------------------------

@odev.command()
def db_clear(db_name: Optional[str] = Argument(None, help="Database name")):
    """
         Clear database by dropping and recreating it.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    return PgSql.erase(db_name or workspace.db_name)


@odev.command()
def db_dump(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Dump the DB for the selected workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    dump_fullpath = paths.workspace(workspace.name) / workspace.db_dump_file
    print(f"Dumping {workspace.db_name} -> {dump_fullpath}")
    PgSql.dump(workspace.db_name, dump_fullpath)


@odev.command()
def db_restore(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Restore the DB for the selected workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    dump_fullpath = paths.workspace(workspace.name) / workspace.db_dump_file
    print(f"Restoring {workspace.db_name} <- {dump_fullpath}")
    PgSql.restore(workspace.db_name, dump_fullpath)

@odev.command()
def l10n_tests(fast: bool = False):
    """
        Run l10n tests
    """

    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Eventually erase the database
    if not fast:
        print(f'Erasing {workspace.db_name}...')
        db_clear(workspace.db_name)

    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)

    Odoo.l10n_tests(project.relative('odoo'),
                    workspace.db_name,
                    project.relative(workspace.venv_path))
    # /data/build/odoo/odoo/tests/test_module_operations.py -d 17105465-15-0-l10n_account --data-dir /data/build/datadir --addons-path odoo/addons,odoo/odoo/addons,enterprise --standalone all_l10n


def _tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False):
    """
        Generic test function for all commands.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Erase the database
    if not fast:
        print(f'Erasing {workspace.db_name}...')
        db_clear(workspace.db_name)

    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(workspace.modules))
    Odoo.start_tests(project.relative('odoo'),
                     rc_fullpath,
                     project.relative(workspace.venv_path),
                     workspace.modules if not fast else [],
                     tags)


@odev.command()
def post_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False):
    """
         Init db (if not fast) and run Odoo's post_install tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}-at_install", fast=fast)


@odev.command()
def init_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags")):
    """
         Init db and run Odoo's at_install tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}-post_install", fast=False)


@odev.command()
def external_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags")):
    """
         Init db and run Odoo's external tests.
         This will install the demo data.
    """
    _tests(tags=f"{(tags + ',') if tags else ''}external", fast=True)


@odev.command()
def test(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags")):
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
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)

    # Erase the database
    print(f'Erasing {workspace.db_name}...')
    db_clear(workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    rc_fullpath = project.relative(workspace.rc_file)
    venv_path = project.relative(workspace.venv_path)
    odoo_path = project.relative('odoo')
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=['base'],
               options=f'{options} --stop-after-init',
               demo=demo)

    print('Installing modules %s ...', ','.join(workspace.modules))
    Odoo.start(odoo_path,
               rc_fullpath,
               venv_path,
               modules=workspace.modules,
               options=f'{options} --stop-after-init',
               demo=demo)

    # Dump the db before the hook if the user has specifically asked for it
    if dump_before:
        db_dump(workspace_name)

    print('Executing post_init_hook...')
    hook_path = paths.workspace(workspace.name) / workspace.post_hook_script
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
def activate():
    """
        Path to the activate script for the current virtual environment.
    """
    out, sys.stdout = sys.stdout, None
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    sys.stdout = out
    activate_path = os.path.join(project.path, workspace.venv_path, "bin", "activate")
    print(activate_path)


# Hub ------------------------------------------------------------

@odev.command()
def hub():
    """
        Open Github in a browser on a branch of a given repo.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    tools.open_hub(project, workspace)


# Lint -----------------------------------------------------------

@odev.command()
def lint():
    """
        Open Github in a browser on a branch of a given repo.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Running Odoo in the steps required to initialize the database
    print("Pylint checking...")
    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start_tests(project.relative('odoo'),
                     rc_fullpath,
                     project.relative(workspace.venv_path),
                     ['test_lint'],
                     "/test_lint")


# Runbot ---------------------------------------------------------

@odev.command()
def runbot():
    """
        Open runbot in a browser for current bundle.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    tools.open_runbot(project, workspace)


# Deps -----------------------------------------------------------
@odev.command()
def deps(module):
    """
        Find module dependancy order for a specific module.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    to_be_done = [module]
    deps = []
    found = set()
    data = {}

    while to_be_done:
        current = to_be_done[0]

        manifest_names = ['__manifest__.py', '__openerp__.py']

        folders = []
        for repo_name, repo in workspace.repos.items():
            if repo.addons_folders:
                for folder in repo.addons_folders:
                    folders.append(str(project.relative(repo_name) / Path(folder)))

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
