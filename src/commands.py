#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from pathlib import Path
from typing import Optional

import os
import ast
import itertools

import paths
import shutil
import tools
import fileinput
from rc import Rc
from external import External
from git import Git
from pgsql import PgSql
from env import Environment
from templates import main_repos
from typer import Argument, Typer

from odoo import Odoo

workspace_name_help = "Name of the workspace that holds the database information, omit to use current"
db_name_help = "Name of the database"
project_name_help = "Name of the project (md5 of the path)"
modules_csv_help = "CSV list of modules"
venv_path_help = "Virtualenv path"

odev = Typer()


# FILES --------------------------------------------------

@odev.command()
def projects(edit: bool = False):
    """
        Display all the available project folders.
    """
    if edit:
        editor = Git.get_editor()
        External.edit(editor, paths.projects())
        return
    for _name, project in tools.get_projects().items():
        print(f"{project.path}  {project.name}  {paths.config() / 'workspaces' / project.name}")


@odev.command()
def project():
    """
        Display project data for the current folder.
    """
    project = tools.get_project()
    print(f"{project.name}:: {project.to_json()}")


@odev.command()
def workspaces():
    """
        Display all the available workspaces for current project.
    """
    project = tools.get_project()
    print(f"{project.name}::")
    for workspace_name in tools.get_workspaces(project):
        print(f"    {workspace_name}")


@odev.command()
def workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """
        Display currently selected workspace data.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    if not edit:
        print(f"{workspace.name}:: {workspace.to_json()}")
        return
    editor = Git.get_editor()
    workspace_file = paths.workspace_file(workspace.name)
    External.edit(editor, workspace_file)


@odev.command()
def delete_project(project_name: Optional[str] = Argument(None, help=project_name_help)):
    """
        Delete a project.
    """
    project = tools.select_project("delete", project_name)
    if not project or not tools.confirm("delete it"):
        return
    tools.delete_project(project.name)


@odev.command()
def dupe_workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help),
                   dest_workspace_name: Optional[str] = Argument(None, help="Destination name")):
    """
        Duplicate a workspace.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("copy", project)
        if not workspace_name:
            return
    if not dest_workspace_name:
        dest_workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
        if not dest_workspace_name:
            return
    sourcepath, destpath = paths.workspace(workspace_name), paths.workspace(dest_workspace_name)
    print(f'Copy {sourcepath} -> {destpath}')
    shutil.copytree(sourcepath, destpath)

    print('Changing the workspace file')
    source_json_path = sourcepath / f"{workspace_name}.json"
    dest_json_path = destpath / f"{dest_workspace_name}.json"
    shutil.move(source_json_path, dest_json_path)
    with fileinput.FileInput(dest_json_path, inplace=True, backup='.bak') as f:
        for line in f:
            print(line.replace(workspace_name, dest_workspace_name), end='')
    tools.set_last_used(project.name, workspace=dest_workspace_name)


@odev.command()
def delete_workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
        Delete a workspace.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("delete", project)
        if not workspace_name:
            return
    if not tools.confirm(f"delete {paths.workspace(workspace_name)}"):
        return
    tools.delete_workspace(workspace_name)
    if project.last_used == workspace_name:
        tools.set_last_used(project.name)


@odev.command()
def create(workspace_name: str = Argument(None, help=workspace_name_help),
           db_name: str = Argument(None, help=db_name_help),
           modules_csv: str = Argument(None, help=modules_csv_help),
           venv_path: Optional[str] = Argument(None, help=venv_path_help)):
    """
        Create a new workspace from a series of selections.
    """

    project = tools.get_project()
    if not workspace_name:
        workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
    if not workspace_name:
        return
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
    repos = checkout(workspace_name)
    if not repos:
        return
    tools.create_workspace(workspace_name, db_name, modules_csv, repos)
    tools.set_last_used(project.name, workspace_name)


# OPERATIONS ---------------------------------

@odev.command()
def start(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), fast: bool = False, demo: bool = False):
    """
        Start Odoo and reinitialize the workspace's modules.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start(project.relative('odoo'),
               rc_fullpath,
               project.relative(workspace.venv_path),
               workspace.modules if not fast else [],
               pty=True,
               demo=demo)


@odev.command()
def load(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
        Load given workspace into the session.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("load", project)
        if not workspace_name:
            return
    if not status(extended=False):
        print("Cannot load, changes present.")
        return
    checkout(workspace_name)
    tools.set_last_used(project.name, workspace_name)


@odev.command()
def shell(interface: Optional[str] = Argument("python", help="Type of shell interface (ipython|ptpython|bpython)"),
          workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
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
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Create virtualenv
    venv_path = project.relative('.venv')
    exists = venv_path.exists()
    paths.ensure(venv_path)
    env = Environment(venv_path)
    if not exists:
        env.create()

    # Clone the base repos and set the 'dev' remote
    for repo_name, repo in tools.select_repositories("setup", workspace, checked=main_repos).items():
        repo_path = project.relative(repo_name)

        print(f"cloning {repo_name}...")
        paths.ensure(repo_path)
        Git.clone(repo.origin, repo.branch, repo_path)
        Git.add_remote('dev', repo.dev, repo_path)

        # Install the requirements
        print(f"installing {repo_name}/requirements.txt...")
        with env:
            env.context.run("pip install --upgrade pip")
            reqs_file = repo_path / 'requirements.txt'
            if reqs_file.exists():
                env.context.run(f"pip install -r {reqs_file}")


# GIT ---------------------------------------------------
@odev.command()
def status(extended: bool = True):
    """
        Display status for all repos for current workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    if not workspace:
        return True
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
        Git.pull(project.relative(repo_name))


@odev.command()
def checkout(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
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


# FILES ------------------------------------------------------------

@odev.command()
def hook(workspace_name: Optional[str] = Argument(None, help=workspace_name_help),
         edit: bool = False,
         run: bool = False):
    """
        Display or edit the post_hook python file.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    hook_fullpath = paths.workspace(workspace.name) / workspace.post_hook_script
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
def rc(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
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
    return PgSql.erase(db_name)


@odev.command()
def db_dump(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
         Dump the DB for the selected workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    dump_fullpath = paths.workspace(workspace.name) / workspace.db_dump_file
    print(f"Dumping {workspace.db_name} -> {dump_fullpath}")
    PgSql.dump(workspace.db_name, dump_fullpath)


@odev.command()
def db_restore(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
         Restore the DB for the selected workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    dump_fullpath = paths.workspace(workspace.name) / workspace.db_dump_file
    print("Restoring {workspace.db_name} <- {dump_fullpath}")
    PgSql.restore(workspace.db_name, dump_fullpath)


@odev.command()
def post_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), fast: bool = False):
    """
        Start Odoo for post_install tests.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start_tests(project.relative('odoo'),
                     rc_fullpath,
                     project.relative(workspace.venv_path),
                     workspace.modules if not fast else [],
                     f"{(tags + ',') if tags else ''}-at_install")


@odev.command()
def init_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags")):
    """
         Initialize the database, then start Odoo for at_install tests.
         This will install the demo data.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Erase the database
    print(f'Erasing {workspace.db_name}...')
    db_clear(workspace.db_name)

    rc_fullpath = project.relative(workspace.rc_file)
    Rc(rc_fullpath).check_db_name(workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Starting tests with modules %s ...', ','.join(workspace.modules))
    Odoo.start_tests(project.relative('odoo'),
                     rc_fullpath,
                     project.relative(workspace.venv_path),
                     workspace.modules,
                     f"{(tags + ',') if tags else ''}-post_install")


@odev.command()
def db_init(workspace_name: Optional[str] = Argument(None, help=workspace_name_help),
            dump_before: bool = False,
            dump_after: bool = False,
            demo: bool = False,
            stop: bool = False):
    """
         Initialize the database, with modules and hook.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)

    # Erase the database
    print(f'Erasing {workspace.db_name}...')
    db_clear(workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    options = ' --stop-after-init'
    rc_fullpath = project.relative(workspace.rc_file)
    venv_path = project.relative(workspace.venv_path)
    odoo_path = project.relative('odoo')
    Rc(rc_fullpath).check_db_name(workspace.db_name)
    Odoo.start(odoo_path, rc_fullpath, venv_path, ['base'], options, demo=demo)

    print('Installing modules %s ...', ','.join(workspace.modules))
    Odoo.start(odoo_path, rc_fullpath, venv_path, workspace.modules, options, demo=demo)

    # Dump the db before the hook if the user has specifically asked for it
    if dump_before:
        db_dump(workspace_name)

    print('Executing post_init_hook...')
    hook_path = paths.workspace(workspace.name) / workspace.post_hook_script
    Odoo.start(odoo_path, rc_fullpath, venv_path, None, ' < ' + str(hook_path), 'shell', demo=demo)

    # Dump the db after the hook if the user has specifically asked for it
    if dump_after:
        db_dump(workspace_name)

    if not stop:
        print('Starting Odoo...')
        Odoo.start(odoo_path, rc_fullpath, venv_path, None)


# HUB ------------------------------------------------------------

@odev.command()
def hub():
    """
        Open Github in a browser on a branch of a given repo.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    tools.open_hub(project, workspace)


# RUNBOT ---------------------------------------------------------

@odev.command()
def runbot():
    """
        Open runbot in a browser for current bundle.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    tools.open_runbot(project, workspace)


# DEPS -----------------------------------------------------------

@odev.command()
def deps(module):
    """
        Find module dependancy order.
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
