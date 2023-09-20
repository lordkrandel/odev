# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from project import Projects, Project, TEMPLATE
from workspace import Workspace
from git import Git
from odev import odev
from templates import template_repos, main_repos, post_hook_template
from repo import Repo

import paths
import asyncio
import consts
import questionary
import shutil
import sys
import webbrowser

custom_style = questionary.Style.from_dict({
    "completion-menu": "bg:#222222",
    "answer": "fg:#ffffee nobold",
})


# Files handling -------------------------------------------

def cat(fullpath, encoding="UTF-8"):
    with open(fullpath, "r", encoding=encoding) as f:
        lines = f.readlines()
    for line in lines:
        print(line.rstrip())


# Project handling ---------------------------------------------

def select_project(action, project_name=None):
    if not project_name:
        choices = [questionary.Choice(project.path, value=project.name) for project in odev.projects.values()]
        project_name = select("project", action, choices, select_function=questionary.select)
        if not project_name:
            return []
    return odev.projects.get(project_name, [])

def delete_project(project_name):
    projects = Projects.load(odev.paths.projects)
    if project_name not in projects:
        raise ValueError(f"{project_name} is not a valid project")
    projects.pop(project_name)
    projects.save_json(odev.paths.projects)

def create_project(path, db_name=None, worktree=False):
    """
        Create a new project, path, and its 'master' workspace.
    """
    digest_current = paths.digest(path)
    project = Project(digest_current, str(path), "master", worktree)
    odev.projects[digest_current] = project
    odev.projects.save_json(odev.paths.projects)

    project_path = odev.paths.config / "workspaces" / digest_current
    if not project_path.is_dir():
        paths.ensure(project_path)
    master_path = project_path / "master"

    if not master_path.is_dir():
        paths.ensure(master_path)

    db_name = db_name or odev.projects.defaults["db_name"]
    master_fullpath = master_path / "master.json"
    if not master_fullpath.exists():
        with open(master_fullpath, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.replace("{{db_name}}", db_name))

    return project

def set_last_used(last_used, project=odev.project):
    odev.projects[odev.project.name].last_used = last_used
    odev.projects.save_json(odev.paths.projects)

# Workspace handling ------------------------------------------

def cleanup_workspace_name(workspace_name):
    if workspace_name and ":" in workspace_name:
        return workspace_name.split(":")[1]
    return workspace_name

def create_workspace(workspace_name, db_name, modules_csv, repos=None, worktree=False):
    repos = repos or select_repositories("checkout", workspace=None, checked=main_repos, worktree=worktree)
    workspace = Workspace(
        workspace_name,
        db_name,
        repos,
        modules_csv.split(','),
        f"{workspace_name}.dmp",
        "post_hook.py",
        '.venv',
        '.odoorc')
    workspace_path = odev.paths.workspace(workspace_name)
    paths.ensure(workspace_path)
    workspace.save_json(odev.paths.workspace_file(workspace_name))
    with open(workspace_path / "post_hook.py", "w", encoding="utf-8") as post_hook_file:
        post_hook_file.write(post_hook_template)
    return repos


def delete_workspace(workspace_name):
    shutil.rmtree(odev.paths.workspace(workspace_name))


def select_workspace(action, project):
    workspaces = odev.workspaces + ['last']
    result = select("workspace", action, workspaces, questionary.autocomplete)
    if result is None:
        sys.exit(1)
    if not result or result == 'last':
        result = project.last_used
    return result


# Repository and branches ------------------------------------

def select_repos_and_branches(project, action, workspace=None, worktree=False):
    repos = {}
    for repo_name, repo in select_repositories(action, workspace, checked=main_repos).items():
        repos[repo_name] = select_branch(project, repo, action, worktree=worktree)
    return repos


def select_repo_and_branch(project, action, workspace=None, worktree=False):
    repo = select_repository(project, action, workspace)
    if repo and not workspace:
        return select_branch(project, repo, action, worktree)
    else:
        return repo


# Repositories -----------------------------------------------

def select_repositories(action, workspace=None, checked=None):
    repos = workspace.repos if workspace else template_repos
    if checked:
        choices = [questionary.Choice(x, checked=(x in checked)) for x in repos]
    else:
        choices = repos
    return {repo_name: repos[repo_name] for repo_name in checkbox("repository", action, choices)}


def select_repository(project, action, workspace=None):
    repos = workspace.repos if workspace else template_repos
    repo_name = select("repository", action, repos, select_function=questionary.select)
    if repo_name:
        repo = repos[repo_name]
        return Repo(repo.name, repo.dev, repo.origin, repo.remote, repo.branch, repo.addons_folders)


# Remotes -----------------------------------------------------

def select_remote(action, remote=None, context=None):
    return remote or select("remote", action, ["origin", "dev"],
                            select_function=questionary.select,
                            context=context)


# Branches ----------------------------------------------------

def select_branch(project, repo, action, choices=None, remote=None, worktree=False):
    if not choices:
        remote = select_remote(action, remote, context=repo.name)
        path = odev.paths.relative(repo.name) if not worktree else odev.paths.bare(repo)
        choices = Git.get_remote_branches(path, remote, worktree)
    prefix = f"{repo.name} > " if not remote else f"{repo.name}/{remote} > "
    branch = questionary.autocomplete(
        f"{prefix}Which branch do you want to {action}?",
        choices=choices,
        style=custom_style,
        qmark=consts.QMARK
    ).ask()
    if branch:
        return Repo(repo.name, repo.dev, repo.origin, remote, branch, repo.addons_folders)


# Runbot -----------------------------------------------

def open_runbot(project, workspace):
    url = f"https://runbot.odoo.com/runbot/r-d-1?search={workspace.repos['odoo'].branch}"
    webbrowser.open(url)


# Github----------------------------------------------------

def open_hub(project, workspace):
    base_url = "https://www.github.com"
    repo = select_repo_and_branch(project, "hub", workspace=odev.workspace)
    if repo:
        url_repo_part = getattr(repo, repo.remote).split(':')[1]
        url = f"{base_url}/{url_repo_part}/tree/{repo.branch}"
        webbrowser.open(url)

# Async ------------------------------------------------------

def await_first_result(coros_dict):
    async def await_first_result_async(coros_dict):
        tasks = [asyncio.create_task(coro, name=name) for name, coro in coros_dict.items()]
        while tasks:
            done, unfinished = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                ret = task.result().join()
                if ret.ok:
                    for unfinished_task in unfinished:
                        unfinished_task.cancel()
                    await asyncio.wait(tasks)
                    return task.get_name(), ret.stdout
            tasks = unfinished
    return asyncio.run(await_first_result_async(coros_dict))

def await_all_results(coros_dict):
    async def await_all_result_async(coros_dict):
        results = {}
        tasks = [asyncio.create_task(coro, name=name) for name, coro in coros_dict.items()]
        done, dummy = await asyncio.wait(tasks)
        for task in done:
            ret = task.result().join()
            if ret.ok:
                results[task.get_name()] = ret.stdout
        return results
    return asyncio.run(await_all_result_async(coros_dict))


# Questionary helpers --------------------------------------

def input_text(text):
    return questionary.text(text, style=custom_style, qmark=consts.QMARK).ask()


def checkbox(subject, action, choices):
    return select(subject, action, choices, questionary.checkbox)


def select(subject, action, choices, select_function=questionary.rawselect, context=None):
    prefix = f"{context} > " if context else ''
    result = select_function(f"{prefix}Which {subject} do you want to {action}?",
                           choices=choices,
                           style=custom_style,
                           qmark=consts.QMARK).ask()
    if result is None:
        sys.exit(1)
    return result or []


def confirm(action):
    return questionary.confirm(f"Are you sure you want to {action}?",
                               style=custom_style,
                               qmark=consts.QMARK).ask()
