# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from project import Projects
from workspace import Workspace
from git import Git
from templates import template_repos, main_repos, post_hook_template
from repo import Repo
import consts
import os
import sys
import paths
import questionary
import shutil
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

def get_projects():
    return Projects.load_json(paths.projects())

def get_project():
    path_hierarchy = [paths.current(), *paths.current().parents]
    for path in path_hierarchy:
        digest = paths.digest(path)
        current_project = get_projects().get(digest)
        if current_project:
            if path != paths.current():
                print(f"Current working directory is not project root {path}")
                os.chdir(path)
            break
    else:
        message = "Project not found, do you want to create a new one?"
        if not questionary.confirm(message, qmark=consts.QMARK).ask():
            sys.exit(1)
        db_name = input_text("What db should it use?")
        if not db_name:
            sys.exit(1)
        current_project = Projects.create_project(paths.current(), paths.current_digest(), db_name)
    return current_project

def delete_project(project_name):
    Projects.delete_project(project_name)

def select_project(action, project_name=None):
    projects = get_projects()
    if not project_name:
        choices = [questionary.Choice(project.path, value=project.name) for project in projects.values()]
        project_name = select("project", action, choices, select_function=questionary.select)
        if not project_name:
            return []
    return projects.get(project_name, [])

# Workspace handling ------------------------------------------

def get_workspace(project, workspace_name=None):
    if not workspace_name or workspace_name == 'last_used':
        workspace_name = project.last_used
    return Workspace.load_json(paths.workspace_file(workspace_name))

def get_workspaces(project):
    return sorted([
        os.path.relpath(x, paths.workspaces()) for x in paths.workspaces().iterdir()
    ])

def create_workspace(workspace_name, db_name, modules_csv, repos=None):
    repos = repos or select_repositories("checkout", workspace=None, checked=main_repos)
    workspace = Workspace(
        workspace_name,
        db_name,
        repos,
        modules_csv.split(','),
        f"{workspace_name}.dmp",
        "post_hook.py",
        '.venv',
        '.odoorc')
    workspace_path = paths.workspace(workspace_name)
    paths.ensure(workspace_path)
    workspace.save_json(paths.workspace_file(workspace_name))
    with open(workspace_path / "post_hook.py", "w", encoding="utf-8") as post_hook_file:
        post_hook_file.write(post_hook_template)
    return repos

def set_last_used(project_name, workspace_name=None):
    if not workspace_name:
        workspace_name = "master"
    projects = Projects.load()
    projects[project_name].last_used = workspace_name
    projects.save()

def delete_workspace(workspace_name):
    shutil.rmtree(paths.workspace(workspace_name))

def select_workspace(action, project):
    workspaces = get_workspaces(project) + ['last_used']
    return select("workspace", action, workspaces, questionary.autocomplete)

# Repository and branches ------------------------------------

def select_repos_and_branches(project, action, workspace=None):
    repos = {}
    for repo_name, repo in select_repositories(action, workspace, checked=main_repos).items():
        repos[repo_name] = select_branch(project, repo, action)
    return repos

def select_repo_and_branch(project, action, workspace=None):
    repo = select_repository(project, action, workspace)
    if repo:
        return select_branch(project, repo, action)

# Repositories -----------------------------------------------

def select_repositories(action, workspace=None, checked=None):
    if checked:
        choices = [questionary.Choice(x, checked=(x in checked)) for x in template_repos]
        repos = template_repos
    elif workspace:
        choices = workspace.repos
        repos = workspace.repos if workspace else template_repos
    else:
        choices = template_repos.keys()
        repos = template_repos
    return {repo_name : repos[repo_name] for repo_name in checkbox("repository", action, choices)}

def select_repository(project, action, workspace=None):
    repos = workspace.repos if workspace else template_repos
    repo_name = select("repository", action, repos, select_function=questionary.select)
    if repo_name:
        repo = repos[repo_name]
        return Repo(repo.name, repo.dev, repo.origin, repo.remote, repo.branch)

# Remotes -----------------------------------------------------

def select_remote(action, remote=None, context=None):
    return remote or select("remote", action, ["origin", "dev"],
                            select_function=questionary.select,
                            context=context)

# Branches ----------------------------------------------------

def select_branch(project, repo, action, choices=None, remote=None):
    if not choices:
        remote = select_remote(action, remote, context=repo.name)
        choices = Git.get_remote_branches(project.relative(repo.name), remote)
    prefix = f"{repo.name} > " if not remote else f"{repo.name}/{remote} > "
    branch = questionary.autocomplete(
        f"{prefix}Which branch do you want to {action}?",
        choices=choices,
        style=custom_style,
        qmark=consts.QMARK
    ).ask()
    if branch:
        return Repo(repo.name, repo.dev, repo.origin, remote, branch)

# Runbot -----------------------------------------------

def open_runbot(project, workspace):
    url = f"https://runbot.odoo.com/runbot/r-d-1?search={workspace.repos['odoo'].branch}"
    webbrowser.open(url)


# Hub --------------------------------------------------

def open_hub(project, workspace):
    base_url = "https://www.github.com"
    repo = select_repo_and_branch(project, "hub", workspace=None)
    if repo:
        url_repo_part = getattr(repo, repo.remote).split(':')[1]
        url = f"{base_url}/{url_repo_part}/tree/{repo.branch}"
        webbrowser.open(url)

# Questionary helpers --------------------------------------

def input_text(text):
    return questionary.text(text, style=custom_style, qmark=consts.QMARK).ask()

def checkbox(subject, action, choices):
    return select(subject, action, choices, questionary.checkbox)

def select(subject, action, choices, select_function=questionary.rawselect, context=None):
    prefix = f"{context} > " if context else ''
    return select_function(f"{prefix}Which {subject} do you want to {action}?",
                           choices=choices,
                           style=custom_style,
                           qmark=consts.QMARK).ask() or []

def confirm(action):
    return questionary.confirm(f"Are you sure you want to {action}?",
                               style=custom_style,
                               qmark=consts.QMARK).ask()
