# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from project import Projects
from workspace import Workspace
import consts
import os
import sys
import paths
import questionary
from templates import template_repos

custom_style = questionary.Style.from_dict({
    "completion-menu": "bg:#222222",
    "answer": "fg:#ffffee nobold",
})

def cat(fullpath, encoding="UTF-8"):
    with open(fullpath, "r", encoding=encoding) as f:
        lines = f.readlines()
    for line in lines:
        print(line.rstrip())

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
        current_project = Projects.create_project(paths.current(), paths.current_digest())
    return current_project

def get_workspace(project, workspace_name=None):
    if not workspace_name or workspace_name == 'last_used':
        workspace_name = project.last_used
    return Workspace.load_json(paths.workspace_file(workspace_name))

def get_workspaces(project):
    return sorted([
        os.path.relpath(x, paths.workspaces()) for x in paths.workspaces().iterdir()
    ])

def select_workspace(action, project):
    workspaces = get_workspaces(project) + ['last_used']
    return select("workspace", action, workspaces, questionary.autocomplete)

def select_repository(repo_names_csv, action, workspace, checked=None):
    if repo_names_csv:
        return repo_names_csv.split(',')
    if checked:
        choices = [questionary.Choice(x, checked=(x in checked)) for x in template_repos]
    else:
        choices = workspace.repos
    return checkbox("repository", action, choices)

def select_branch(repo_name, choices):
    return questionary.autocomplete(
        f"[{repo_name}] Which branch do you want to checkout (<remote>/<branch>)?",
        choices=choices,
        style=custom_style,
        qmark=consts.QMARK
    ).ask() or []

def set_last_used(project_name, workspace_name):
    projects = Projects.load()
    projects[project_name].last_used = workspace_name
    projects.save()

def checkbox(subject, action, choices):
    return select(subject, action, choices, questionary.checkbox)

def select(subject, action, choices, select_function=questionary.rawselect):
    return select_function(f"Which {subject} do you want to {action}?",
                           choices=choices,
                           style=custom_style,
                           qmark=consts.QMARK).ask() or []
