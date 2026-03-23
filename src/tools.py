# Part of Odoo. See LICENSE file for full copyright and licensing details.

from pathlib import Path

import paths
from git import Git
import pl
from odev import odev
from pgsql import PgSql
from project import Projects, Project, TEMPLATE
from repo import Repo
from templates import template_repos, main_repos, origins, post_hook_template
from workspace import Workspace

import asyncio
import consts
from datetime import datetime
import questionary
import shutil
import re
import sys


yeslike = [1, "s", "y", "si", "yes", "true"]
nolike = [0, "n", "no", "false"]

def strtobool(value):
    lowered = (value or '').lower()
    if lowered == '':
        return 'default'
    if lowered in yeslike:
        return True
    if lowered in nolike:
        return False
    return None

custom_style = questionary.Style.from_dict({
    "completion-menu": "bg:#222222",
    "answer": "fg:#ffffee nobold",
})


# Pure tools ---------------------------------------------------

def date_to_string(d):
    return datetime.strftime(d, "%H:%M:%S %d/%m/%Y")


# Files handling -----------------------------------------------

def cat(fullpath, encoding="UTF-8"):
    with open(fullpath, encoding=encoding) as f:
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

def create_project(path, db_name=None):
    """
        Create a new project, path, and its 'master' workspace.
    """
    digest_current = paths.digest(path)
    project = Project(digest_current, str(path), "master")
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

def cleanup_colon(name):
    if name and ":" in name:
        return name.split(":")[1]
    return name


def _extract_version(branch_name):
    base = (
        re.match(r"(?P<name>(?P<major>\d{1,2}).(?P<minor>\d))", branch_name)
        or re.match(r"(?P<name>saas-(?P<major>\d{1,2}).(?P<minor>\d))", branch_name)
        or re.match(r"(?P<name>master)", branch_name)
    )
    return base.groupdict() if base else None

def get_venv_path(version):
    match int(version.get('major', 999)):
        case x if x >= 19:
            return ".venv313"
        case x if x in range(16, 19):
            return ".venv311"
        case _:
            return ".venv310"

def find_base(repo_name, branch):
    fallback = _extract_version(branch)['name']
    arbitrary_path = odev.paths.project / repo_name
    have_dev_origin = [k for k, v in origins.items() if 'dev' in v]
    remote = 'dev' if repo_name in have_dev_origin else 'origin'
    Git.fetch(arbitrary_path, repo_name, remote, branch)
    bundle_merge_base = Git.merge_base(arbitrary_path, 'master', f'{remote}/{branch}')
    return getattr(odev.merge_cache, repo_name, {}).get(bundle_merge_base, fallback)

def workspace_prepare(
    workspace_name=None,
    db_name=None,
    venv_path=None,
    repos=None,
    modules_csv=None,
    ask_modules=True,
):
    if not (workspace_name := (workspace_name or select_new_workspace())):
        return

    workspace_name = cleanup_colon(workspace_name)
    if workspace_name in odev.workspaces + ['last_used']:
        print(f"Workspace {workspace_name} is empty or already exists")
        return

    db_name = db_name or select_db_name()
    venv_path = venv_path or select_venv(odev.workspace)

    if not (repos := repos or select_repos_and_branches(odev.project, "checkout")):
        return

    if modules_csv or ask_modules and (modules_csv := select_modules()):
        modules = modules_csv.split(',')
    else:
        modules = []

    return Workspace(workspace_name, db_name, repos, modules, venv_path=venv_path)


def workspace_install(workspace):
    workspace_path = odev.paths.workspace(workspace.name)
    paths.ensure(workspace_path)
    with (workspace_path / workspace.post_hook_script).open("w", encoding="utf-8") as f:
        f.write(post_hook_template)
    workspace.save_json(odev.paths.workspace_file(workspace.name))
    odev.reload_workspaces()


def move_workspace(workspace_name, dest_workspace_name):
    path = odev.paths.workspace_file(workspace_name)
    dest_path = odev.paths.workspace(workspace_name) / Path(f"{dest_workspace_name}.json")
    workspace = Workspace.load_json(path)
    shutil.move(path, dest_path)

    workspace.db_dump_file.replace(workspace_name, dest_workspace_name)
    workspace.name = dest_workspace_name
    workspace.save_json(dest_path)

    path = odev.paths.workspace(workspace_name)
    dest_path = odev.paths.workspace(dest_workspace_name)
    shutil.move(path, dest_path)


def delete_workspace(workspace_name):
    shutil.rmtree(odev.paths.workspace(workspace_name))


def select_new_workspace():
    return (input_text("What name for your workspace?") or '').strip()


def select_workspace(action, project):
    workspaces = odev.workspaces + ['last']
    result = select("workspace", action, workspaces, questionary.autocomplete)
    if result is None:
        sys.exit(1)
    if not result or result == 'last':
        result = project.last_used
    return result


# Repository and branches ------------------------------------

def select_repos_and_branches(project, action, workspace=None):
    repos = {}
    for repo_name, repo in select_repositories(action, workspace, checked=main_repos).items():
        repos[repo_name] = select_branch(project, repo_name, action)
    return repos


# Repositories -----------------------------------------------

def select_repositories(action, workspace=None, checked=None):
    repos = workspace.repos if workspace else template_repos
    if checked:
        choices = [questionary.Choice(x, checked=(x in checked)) for x in repos]
    else:
        choices = repos
    return {repo_name: repos[repo_name] for repo_name in checkbox("repository", action, choices)}


def select_repository(action, workspace=None, repo_names=None):
    all_repos = workspace.repos if workspace else template_repos
    if not repo_names:
        repo_choices = all_repos
    else:
        repo_choices = {repo_name: repo for repo_name, repo in all_repos.items() if repo_name in repo_names}

    repo_name = select("repository", action, repo_choices, select_function=questionary.select)
    if repo_name:
        repo = repo_choices[repo_name]
        return repo_name, Repo(repo.remote, repo.branch)


# Remotes -----------------------------------------------------

def select_remote(action, remote=None, context=None):
    return remote or select("remote", action, ["origin", "dev"],
                            select_function=questionary.select,
                            context=context)


# Modules -----------------------------------------------------
def select_modules():
    return (input_text("What modules to use? (CSV)") or '').strip()

# Branches ----------------------------------------------------

def select_branch(project, repo_name, action, choices=None, remote=None):
    if not choices:
        remote = select_remote(action, remote, context=repo_name)
        path = odev.paths.repo(repo_name)
        choices = Git.get_remote_branches(path, remote)
    prefix = f"{repo_name} > " if not remote else f"{repo_name}/{remote} > "
    branch = questionary.autocomplete(
        f"{prefix}Which branch do you want to {action}?",
        choices=choices,
        style=custom_style,
        qmark=consts.QMARK
    ).ask()
    if branch:
        return Repo(remote, branch)


# Async ------------------------------------------------------

def await_all_results(coros_dict):
    async def await_all_results_async(coros_dict):
        tasks = {
            name: asyncio.create_task(coro, name=name)
            for name, coro in coros_dict.items()
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        final_results = {}
        for task, ret in zip(tasks.values(), results):
            if isinstance(ret, Exception):
                print(f"Task {task.get_name()} failed: {ret}")
                continue
            final_results[task.get_name()] = {
                'stdout': ret.stdout.decode().rstrip(),
                'stderr': ret.stderr.decode().rstrip(),
                'returncode': ret.returncode,
            }
        return final_results
    return asyncio.run(await_all_results_async(coros_dict))


def async_sequence(repos, promises, indent=4):
    async def _runner():
        tasks = (
            asyncio.create_task(
                _sequence(repo_name, repo, horizontal_position=idx))
            for idx, (repo_name, repo) in enumerate(repos.items())
        )
        return await asyncio.wait(tasks)

    def get_args(method, path, repo_name, repo):
        match method:
            case Git.fetch_async:
                return (path, repo_name, repo.remote, repo.branch)
            case Git.reset_async:
                return (path, True)
            case Git.clean_async:
                return (path, )
            case Git.checkout_async:
                return (path, repo.branch)
            case Git.pull_async:
                return (path, repo.remote, repo.branch)

    async def _sequence(repo_name, repo, horizontal_position):
        for method in promises:
            path = odev.paths.repo(repo_name)
            args = get_args(method, path, repo_name, repo)

            args_str = ' '.join([str(arg) for arg in args[1:]])
            operation = re.sub("_async$", "", method.__name__)
            indent_str = ' ' * horizontal_position * indent
            print(f"{indent_str}({path.name}) {operation} {args_str}")

            ret = await method(*get_args(method, path, repo_name, repo))
            if ret.returncode != 0:
                print(ret.stderr.decode())
                return
    return asyncio.run(_runner())


# Database name --------------------------------------------
def select_db_name():
    return select(
        "database",
        "use",
        PgSql.db_names(),
        questionary.autocomplete,
        default=odev.projects.defaults['db_name'],
    )

# Venv -----------------------------------------------------

def select_venv(workspace):
    venvs = [str(f) for f in Path(odev.project.path).glob(".venv*") if f.is_dir()]
    return (
        select("venv", "select", venvs, questionary.autocomplete)
        or workspace.venv_path
    )


# Questionary helpers --------------------------------------

def input_text(text):
    return questionary.text(text, style=custom_style, qmark=consts.QMARK).ask()


def checkbox(subject, action, choices):
    return select(subject, action, choices, questionary.checkbox)


def select(
    subject,
    action,
    choices,
    select_function=questionary.rawselect,
    context=None,
    default=None
):
    prefix = f"{context} > " if context else ''
    default_str = f" ({default})" if default else ''
    result = select_function(
        f"{prefix}Which {subject} do you want to {action}?{default_str}",
        choices=choices,
        style=custom_style,
        qmark=consts.QMARK,
    ).ask()
    if result is None:
        sys.exit(1)
    elif result == '' and default:
        return default
    elif result and isinstance(result, str):
        result = result.strip()
    elif result and isinstance(result, tuple | list):
        result = [x.strip() for x in result]
    return result


def confirm(action):
    return questionary.confirm(f"Are you sure you want to {action}?",
                               style=custom_style,
                               qmark=consts.QMARK).ask()
