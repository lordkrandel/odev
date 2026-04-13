import sys
from pathlib import Path
from itertools import product
from typing import Optional

import click
from typer import Argument

import pl
import tools
from odev import odev
from templates import origins
from workspace import Workspace


helps = dict(
    extra="Additional command line parameters",
    db_name="Name of the database",
    project_path="Path where to create the project, default is current",
    project_name="Name of the project (md5 of the path)",
    modules_csv="CSV list of modules",
    repos_csv="CSV list of repositories",
    venv_path="Virtualenv path",
    workspace_name="Name of the workspace that holds the database information, omit to use current",
)


def set_target(workspace_name: str = None):
    subcommand = click.get_current_context().parent.invoked_subcommand
    if subcommand is None:
        # If it's autocomplete, don't ask interactively
        return
    if not workspace_name:
        workspace_name = tools.select_workspace("select (default=last)", odev.project)
    elif workspace_name == 'last':
        try:
            workspace_name = odev.project.last_used
        except Exception:
            sys.exit('Cannot read last_used')
    else:
        workspace_name = tools.cleanup_colon(workspace_name)
    workspace_file = odev.paths.workspace_file(workspace_name)
    if not workspace_file.exists():
        sys.exit(f"Workspace file {workspace_file} doesn't exist")
    try:
        odev.workspace = Workspace.load_json(workspace_file)
    except Exception:
        sys.exit(f"Cannot load {workspace_file}")
    if odev.workspace:
        odev.workspace.set_path(odev.paths.project)
        for repo_name, repo in odev.workspace.repos.items():
            if str(odev.paths.starting).startswith(str(odev.paths.relative('') / repo_name)):
                odev.repo = repo
                break
    if workspace_name not in odev.workspaces:
        sys.exit(f"Workspace {workspace_name} not found.")

    return workspace_name


def WorkspaceNameArgument(*args, default='last', **kwargs):

    def workspaces_yield(incomplete: Optional[str] = None):
        return [workspace_name for workspace_name in odev.workspaces if workspace_name.startswith(workspace_name)]

    return Argument(*args, **{
        **kwargs,
        'help': helps['workspace_name'],
        'callback': set_target,
        'default': default,
        'autocompletion': workspaces_yield,
    })


@odev.command()
def update_merge_base_cache(
    workspace_name: Optional[str] = WorkspaceNameArgument()
):
    """
        Update the merge base cache
    """
    have_dev_origin = [k for k, v in origins.items() if 'dev' in v]
    repos = {
        repo_name: repo
        for repo_name, repo in odev.workspace.repos.items()
        if repo_name in have_dev_origin
    }
    pl.run(
        "git -C {path} fetch {remote} {branch}",
        repos=repos,
    )
    pl.run(
        "git -C {path} fetch origin {version}",
        repos=repos,
        versions=odev.merge_cache.versions,
    )
    keys = [
        f"{repo_name}/{version}" 
        for repo_name, version in product(repos, odev.merge_cache.versions)
    ]
    hashes = list(
        clean_line
        for line in pl.run(
            "git -C {path} merge-base origin/master origin/{version}",
            repos=repos,
            versions=odev.merge_cache.versions,
            output=False,
        ).splitlines()
        if (clean_line := line.rstrip())
    )
    results = dict(zip(keys, hashes))
    for key, merge_base in results.items():
        repo, version = key.split('/')
        getattr(odev.merge_cache, repo)[merge_base] = version
    odev.merge_cache.save_json(odev.paths.cache)


@odev.command()
def project_create(
    project_path: Optional[str] = Argument(None, help=helps['project_path']),
    db_name: Optional[str] = Argument(None, help=helps['db_name'])
):
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
