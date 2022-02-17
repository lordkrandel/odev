#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from pathlib import Path
from typing import Optional

import paths
import tools
from external import External
from git import Git
from pgsql import PgSql
from env import Environment
from templates import template_repos, main_repos
from typer import Argument, Typer

from odoo import Odoo

workspace_name_help = "Name of the workspace that holds the database information, omit to use current"
repo_names_csv_help = "CSV list of repositories"
project_name_help = "Name of the project (md5 of the path)"

odev = Typer()

# FILES --------------------------------------------------

@odev.command()
def projects():
    """
        Display all the available project folders.
    """
    for _name, project in tools.get_projects().items():
        print(f"{project.path}  {project.name}  {paths.config() / project.name}")

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
        Display all the available workspaces for current project
    """
    project = tools.get_project()
    print(f"{project.name}::")
    for workspace_name in tools.get_workspaces(project):
        print(f"    {workspace_name}")

@odev.command()
def workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """
        Display currently selected workspace data
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
def delete_workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
        Delete a workspace.
    """
    project = tools.get_project()
    if not workspace_name:
        workspace_name = tools.select_workspace("delete", project)
        if not workspace_name:
            return
    if not tools.confirm("delete it"):
        return
    tools.delete_workspace(workspace_name)

# OPERATIONS ---------------------------------

@odev.command()
def start(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), fast: bool = False, demo: bool = False):
    """
        Start Odoo and reinitialize the workspace's modules.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    Odoo.start(project.relative('odoo'),
               project.relative(workspace.rc_file),
               project.relative(workspace.venv_path),
               workspace.modules if not fast else [],
               pty=True,
               demo=demo)

@odev.command()
def start_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags"), demo: bool = False):
    """
        Start Odoo with the tests-enable flag on.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    Odoo.start_tests(project.relative('odoo'),
                     project.relative(workspace.rc_file),
                     project.relative(workspace.venv_path),
                     workspace.modules,
                     tags,
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
    workspace = tools.get_workspace(project, workspace_name)

    # Check the status
    if not status(extended=False):
        print("Cannot load, changes present.")
        return

    # Fetch and checkout each repo
    for _name, repo in workspace.repos.items():
        print(f"Fetching {repo.name}...")
        Git.fetch(project.path, repo.name, repo.remote, repo.branch)
        print(f"Checking out {repo.name}...")
        Git.checkout(project.relative(repo.name), repo.branch)

    # Set the current workspace
    tools.set_last_used(project.name, workspace.name)

@odev.command()
def shell(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """
        Starts Odoo as an interactive shell.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    Odoo.start(project.relative('odoo'),
               project.relative(workspace.rc_file),
               project.relative(workspace.venv_path),
               None, options='', mode='shell', pty=True)

@odev.command()
def setup(db_name):
    """
        Sets up the main folder, which will contain all repositories and the virtual environment.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    # Create virtualenv
    venv_path = project.relative('.venv')
    paths.ensure(venv_path)
    env = Environment(venv_path)
    env.create()

    # Clone the base repos and set the 'dev' remote
    for repo_name in tools.select_repository('', "setup", workspace, checked=main_repos):
        repo = template_repos[repo_name]
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
            env.context.run(f"pip install -r {reqs_file}")


# GIT ---------------------------------------------------
@odev.command()
def status(repo_names_csv: Optional[str] = Argument(None, help=repo_names_csv_help), extended: bool = True):
    """
        Display status for all repos for current workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
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
def push(repo_names_csv: Optional[str] = Argument(None, help=repo_names_csv_help), force: bool = False):
    """
        Git-pushes multiple repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in tools.select_repository(repo_names_csv, "push", workspace):
        print(f"Pushing {repo_name}...")
        Git.push(project.relative(repo_name), force=force)

@odev.command()
def fetch(repo_names_csv: Optional[str] = Argument(None, help=repo_names_csv_help), origin: bool = False):
    """
        Git-fetches multiple repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in tools.select_repository(repo_names_csv, "fetch", workspace):
        print(f"Fetching {repo_name}...")
        if origin:
            Git.fetch(project.path, repo_name, "origin", "")
        else:
            repo = workspace.repos[repo_name]
            Git.fetch(project.path, repo_name, repo.remote, repo.branch)

@odev.command()
def pull(repo_names_csv: Optional[str] = Argument(None, help=repo_names_csv_help)):
    """
        Git-pulls selected repos for current workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)
    for repo_name in tools.select_repository(repo_names_csv, "pull", workspace):
        print(f"Pulling {repo_name}...")
        Git.pull(project.relative(repo_name))

@odev.command()
def checkout(repo_names_csv: Optional[str] = Argument(None, help=repo_names_csv_help)):
    """
        Git-checkouts multiple repositories.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project)

    for repo_name in tools.select_repository(repo_names_csv, "checkout", workspace, checked=main_repos):
        # all the available branch names
        branch_choices = Git.get_remote_branches(project.relative(repo_name))
        answer = tools.select_branch(repo_name, branch_choices)
        remote_name, branch_name = answer.split('/')
        print(f"Fetching {repo_name} {remote_name}/{branch_name}...")
        Git.fetch(project.path, repo_name, remote_name, branch_name)
        print(f"Checking out {repo_name} {remote_name}/{branch_name}...")
        Git.checkout(project.relative(repo_name), branch_name)

# FILES ------------------------------------------------------------

@odev.command()
def hook(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """
        Display or edit the post_hook python file for selected workspace.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    hook_fullpath = paths.workspace(workspace.name) / workspace.post_hook_script
    if edit:
        External.edit(Git.get_editor(), hook_fullpath)
        return
    tools.cat(hook_fullpath)


@odev.command()
def rc(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """
        View or edit the .odoorc configuration with default git editor
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)
    rc_fullpath = paths.current() / workspace.rc_file
    if edit:
        return External.edit(Git.get_editor(), rc_fullpath)
    tools.cat(rc_fullpath)

# DB ------------------------------------------------------------

@odev.command()
def db_erase(db_name: Optional[str] = Argument(None, help="Database name")):
    """
         Drop and recreate the selected database.
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
def db_reinit(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), dump: str = None, demo: bool = False):
    """
         Initialize the database with given modules and post_hook.
    """
    project = tools.get_project()
    workspace = tools.get_workspace(project, workspace_name)

    # Erase the database
    print(f'Erasing {workspace.db_name}...')
    db_erase(workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    options = ' --stop-after-init'
    rc_file_path = project.relative(workspace.rc_file)
    venv_path = project.relative(workspace.venv_path)
    odoo_path = project.relative('odoo')
    Odoo.start(odoo_path, rc_file_path, venv_path, ['base'], options, demo=demo)

    print('Installing modules %s ...', ','.join(workspace.modules))
    Odoo.start(odoo_path, rc_file_path, venv_path, workspace.modules, options, demo=demo)

    # Dump the db before the hook if the user has specifically asked for it
    if dump == 'before_hook':
        db_dump(workspace_name)

    print('Executing post_init_hook...')
    hook_path = paths.workspace(workspace.name) / workspace.post_hook_script
    Odoo.start(odoo_path, rc_file_path, venv_path, None, ' < ' + str(hook_path), 'shell', demo=demo)

    # Dump the db after the hook if the user has specifically asked for it
    if dump == 'after_hook':
        db_dump(workspace_name)

    print('Starting Odoo...')
    Odoo.start(odoo_path, rc_file_path, venv_path, None)
