#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from os.path import join as opjoin
from typing import Optional
from typer import Argument
import questionary

import consts
from application import odev
from external import External
from git import Git
from odoo import Odoo
from pgsql import PgSql
from templates import template_repos
from env import Environment

workspace_name_help = "Name of the workspace that holds the database information, omit to use current"
paths = odev.paths

custom_style = questionary.Style.from_dict({
    "completion-menu": "bg:#222222",
    "answer": "fg:#ffffee nobold",
})


def print_file(fullpath, encoding="UTF-8"):
    with open(fullpath, "r", encoding=encoding) as f:
        lines = f.readlines()
    for line in lines:
        print(line.rstrip())


@odev.command()
def db_erase(db_name: Optional[str] = Argument(None, help="Database name")):
    """ Drop and recreate the selected database """
    return PgSql.erase(db_name)


@odev.command()
def db_reinit(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), dump: str = None, demo: bool = False):
    """ Initialize the database with given modules and post_hook"""
    odev.select_workspace(workspace_name)

    # Erase the database
    print(f'Erasing {odev.workspace.db_name}...')
    db_erase(odev.workspace.db_name)

    # Running Odoo in the steps required to initialize the database
    print('Installing base module...')
    options = f' --stop-after-init {(demo and " --without-demo=WITHOUT_DEMO ") or ""}'
    Odoo.start(paths.relative('odoo'),
               paths.rc_file,
               paths.venv_path,
               ['base'],
               options)

    print('Installing modules %s ...', ','.join(odev.workspace.modules))
    Odoo.start(paths.relative('odoo'),
               paths.rc_file,
               paths.venv_path,
               odev.workspace.modules,
               options)

    # Dump the db before the hook if the user has specifically asked for it
    if dump == 'before_hook':
        db_dump(workspace_name)

    print('Executing post_init_hook...')
    Odoo.start(paths.relative('odoo'),
               paths.rc_file,
               paths.venv_path,
               None,
               ' < ' + paths.post_hook_script,
               'shell')

    # Dump the db after the hook if the user has specifically asked for it
    if dump == 'after_hook':
        db_dump(workspace_name)

    print('Starting Odoo...')
    Odoo.start(paths.relative('odoo'),
               paths.rc_file,
               paths.venv_path,
               None)


@odev.command()
def start(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), fast: bool = False):
    """ Start Odoo and reinitialize the workspace's modules """
    odev.select_workspace(workspace_name)
    Odoo.start(paths.relative('odoo'),
               paths.rc_file,
               paths.venv_path,
               odev.workspace.modules if not fast else [],
               ' --without-demo=WITHOUT_DEMO',
               pty=True)


@odev.command()
def start_tests(tags: Optional[str] = Argument(None, help="Corresponding to --test-tags")):
    """ Start Odoo with the tests-enable flag on """
    Odoo.start_tests(paths.relative('odoo'),
                     paths.rc_file,
                     paths.venv_path,
                     odev.workspace.modules,
                     tags)


@odev.command()
def checkout():
    """ Check out multiple repositories """

    # def validate(text):
    #     return bool(re.match(r"^[0-9a-z-_\.,]+/[0-9a-z-_\.,]+$", text, flags=re.I))

    choices = [questionary.Choice(x, checked=x in ('odoo', 'enterprise')) for x in template_repos]
    repo_names = questionary.checkbox("Which repositories do you want to checkout?", choices=choices, qmark=consts.QMARK).ask()
    if not repo_names:
        return

    for repo_name in repo_names:
        # all the available branch names
        branch_choices = Git.get_remote_branches(odev.paths.relative(repo_name))
        answer = questionary.autocomplete(
            f"[{repo_name}] What branch to checkout (<remote>/<branch>)?",
            choices=branch_choices,
            style=custom_style,
            qmark=consts.QMARK
        ).ask()
        if not answer:
            return
        remote_name, branch_name = answer.split('/')
        print(f"Fetching {repo_name} {remote_name}/{branch_name}...")
        Git.fetch(odev.project.path, repo_name, remote_name, branch_name)
        print(f"Checking out {repo_name} {remote_name}/{branch_name}...")
        Git.checkout(odev.paths.relative(repo_name), branch_name)


def _select(subject, action, choices, select_function=questionary.rawselect):
    return select_function(f"Which {subject} do you want to {action}?",
                           choices=choices,
                           style=custom_style,
                           qmark=consts.QMARK).ask() or []


def _checkbox(subject, action, choices):
    return _select(subject, action, choices, questionary.checkbox)


@odev.command()
def fetch(origin: bool = False):
    for repo_name in _checkbox("repository", "fetch", odev.workspace.repos):
        print(f"Fetching {repo_name}...")
        if origin:
            Git.fetch(odev.project.path, repo_name, "origin", "")
        else:
            repo = odev.workspace.repos[repo_name]
            Git.fetch(odev.project.path, repo_name, repo.remote, repo.branch)


@odev.command()
def push(force: bool = False):
    for repo_name in _checkbox("repository", "push", odev.workspace.repos):
        print(f"Pushing {repo_name}...")
        Git.push(odev.paths.relative(repo_name), force=force)


@odev.command()
def pull():
    """ Pulls selected repos for current workspace """
    for repo_name in _checkbox("repository", "checkout", odev.workspace.repos):
        print(f"Pulling {repo_name}...")
        Git.pull(odev.paths.relative(repo_name))


@odev.command()
def projects():
    """ Display all the available project folders """
    for _name, project in odev.projects.items():
        print(project.path)


@odev.command()
def project():
    """ Display project data for the current folder """
    print(f"{odev.project.name}:: {odev.project.to_json()}")


@odev.command()
def workspaces():
    """ Display all the available workspaces for current project """
    print(f"{odev.project.name}::")
    for workspace_name in odev.workspace_names:
        print(f"    {workspace_name}")


@odev.command()
def workspace(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """ Display currently selected workspace data """
    odev.select_workspace(workspace_name)
    if not edit:
        print(f"{odev.workspace.name}:: {odev.workspace.to_json()}")
    else:
        External.edit(odev.editor, paths.workspace_file)


@odev.command()
def db_dump(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """ Dump the DB for the selected workspace """
    odev.select_workspace(workspace_name)
    print(f"Dumping {odev.workspace.db_name} -> {paths.db_dump_file}")
    PgSql.dump(odev.workspace.db_name, opjoin(paths.workspace, paths.db_dump_file))


@odev.command()
def db_restore(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """ Restore the DB for the selected workspace """
    odev.select_workspace(workspace_name)
    print("Restoring {odev.workspace.db_name} <- {paths.db_dump_file}")
    PgSql.restore(odev.workspace.db_name, opjoin(paths.workspace, paths.db_dump_file))


@odev.command()
def rc(edit: bool = False):
    """ View or edit the .odoorc configuration with default git editor """
    if edit:
        return External.edit(odev.editor, paths.rc_file)
    print_file(paths.rc_file)


@odev.command()
def hook(workspace_name: Optional[str] = Argument(None, help=workspace_name_help), edit: bool = False):
    """ Display or edit the post_hook python file for selected workspace """
    odev.select_workspace(workspace_name)
    fullpath = opjoin(paths.workspace, paths.post_hook_script)
    if edit:
        return External.edit(odev.editor, fullpath)
    print_file(fullpath)


@odev.command()
def status(extended: bool = True):
    """ Display status for all repos for current workspace """
    for name in odev.workspace.repos:
        ret = Git.status(opjoin(paths.project.path, name), extended=extended, name=name)
        if not extended and ret.stdout:
            return False
    return True


@odev.command()
def shell(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """ Start Odoo as an interactive shell """
    odev.select_workspace(workspace_name)

    Odoo.start(paths.relative('odoo'),
               paths.relative(paths.rc_file),
               paths.relative(paths.venv_path),
               None,
               options='',
               mode='shell',
               pty=True)


@odev.command()
def load(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """ Load given workspace into the session """
    # Check the status
    if not status(False):
        print("Cannot load, changes present.")
        return

    workspace_name = _select("workspace", "load", odev.workspace_names, questionary.autocomplete)
    if not workspace_name:
        return
    odev.select_workspace(workspace_name)

    # Fetch and checkout each repo
    for _name, repo in odev.workspace.repos.items():
        print(f"Fetching {repo.name}...")
        Git.fetch(odev.project.path, repo.name, repo.remote, repo.branch)
        print(f"Checking out {repo.name}...")
        Git.checkout(paths.relative(repo.name), repo.branch)

    # Set the current workspace
    odev.last_used = workspace_name


@odev.command()
def setup(db_name):
    """
        Sets up the main folder, which will contain all repositories and the virtual environment.
    """

    choices = [questionary.Choice(x, checked=x in ('odoo', 'enterprise')) for x in template_repos]
    repo_names = questionary.checkbox("Which repositories do you want to clone?", choices=choices, qmark=consts.QMARK).ask()
    if not repo_names:
        return

    # Create virtualenv
    venv_path = paths.relative('.venv')
    paths.ensure(venv_path)
    env = Environment(venv_path)
    env.create()

    # Clone the base repos and set the 'dev' remote
    for repo_name in repo_names:
        repo = template_repos[repo_name]
        repo_path = paths.relative(repo_name)

        print(f"cloning {repo_name}...")
        paths.ensure(repo_path)
        Git.clone(repo.origin, repo.branch, repo_path)
        Git.add_remote('dev', repo.dev, repo_path)

        # Install the requirements
        print(f"installing {repo_name}/requirements.txt...")
        with env:
            env.context.run(f"pip install --upgrade pip")
            reqs_file = opjoin(repo_path, 'requirements.txt')
            env.context.run(f"pip install -r {reqs_file}")


# FUNCTIONAL ----------------------------------------------------------------

from workspace import Workspace


@odev.command()
def fshell(workspace_name: Optional[str] = Argument(None, help=workspace_name_help)):
    """ Start Odoo as an interactive shell """
    project_base = paths.project()
    workspace = Workspace.load_json(paths.workspace(workspace_name))
    Odoo.start(project_base / 'odoo',
               project_base / workspace.rc_file,
               project_base / workspace.venv_path,
               None,
               options='',
               mode='shell',
               pty=True)
