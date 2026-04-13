import shutil
import fileinput
from typing import Optional

from typer import Argument, Context

import pl
import sys
import tools
from commands.common import WorkspaceNameArgument, helps, set_target
from commands.git import status, reset
from odev import odev
from templates import template_repos
from workspace import Workspace


@odev.workspace.command()
def last_used():
    """
        Print the last_used workspace
    """
    if not odev.project:
        sys.exit(1)
    print(odev.project.last_used)


def _switch(workspace_name, ask_reset=True):
    workspace_file = odev.paths.workspace_file(workspace_name)
    workspace = Workspace.load_json(workspace_file)
    if not status(extended=False) and ask_reset and reset():
        return

    last_used = odev.project.last_used
    print(f"{last_used} -> {workspace_name} (updated)...")

    pl.run(
        "git -C {path} clean -xdf",
        "git -C {path} fetch {remote} {branch}",
        "git -C {path} switch -C {branch} --track {remote}/{branch}",
        # "git -C {path} rebase --abort",
        # "git -C {path} fetch --progress --verbose  {remote} {branch}",
        # "git -C {path} clean -xdf",
        # "git -C {path} switch -C {branch} --track {remote}/{branch}",
        # "git -C {path} pull {remote} {branch}",
        # "git -C {path} clean -xdf",
        repos=odev.workspace.repos
    )
    tools.set_last_used(workspace_name)
    odev.workspace = workspace


@odev.workspace.command()
def load(workspace_name: Optional[str] = WorkspaceNameArgument(default=None)):
    """
        Load given workspace into the session.
    """
    _switch(workspace_name)


@odev.workspace.command()
def update(ctx: Context, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Updates given workspace and reloads the current one.
        With asynchronous methods.
    """
    last_used = odev.project.last_used
    _switch(workspace_name)
    if last_used:
        last_workspace_file = odev.paths.workspace_file(last_used)
        last_workspace = Workspace.load_json(last_workspace_file)
        last_workspace.set_path(odev.paths.project)
        last_repos = last_workspace.repos
        pl.run(
            "git -C {path} checkout {branch}",
            repos=last_repos,
        )
        tools.set_last_used(last_used)


@odev.workspace.command()
def dupe(workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
                   dest_workspace_name: Optional[str] = Argument(None, help="Destination name"),
                   _load: bool = False):
    """
        Duplicate a workspace.
    """
    if not dest_workspace_name:
        dest_workspace_name = (tools.input_text("What name for your workspace?") or '').strip()
        if not dest_workspace_name:
            return
    dest_workspace_name = tools.cleanup_colon(dest_workspace_name)
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

    set_target(dest_workspace_name)
    tools.workspace_install(dest_workspace_name)
    if _load:
        load(dest_workspace_name)


@odev.workspace.command()
def create(
    ctx: Context,
    db_name: Optional[str] = Argument(None, help=helps['db_name']),
    modules_csv: Optional[str] = Argument(None, help=helps['modules_csv']),
    venv_path: Optional[str] = Argument(None, help=helps['venv_path']),
    repos_csv: Optional[str] = Argument(None, help=helps['repos_csv']),
):
    """
        Create a new workspace from a series of selections.
    """

    new_workspace_name = None
    if not (workspace := tools.workspace_prepare(
        new_workspace_name,
        db_name,
        venv_path,
        repos=[template_repos[name] for name in (repos_csv or '').split(',') if name.strip()],
        modules_csv=modules_csv,
    )):
        return

    tools.workspace_install(workspace)

    workspace_file = odev.paths.workspace_file(workspace.name)
    with fileinput.FileInput(workspace_file, inplace=True, backup='.bak') as f:
        for line in f:
            if workspace.name in line and "branch" in line:
                print(f'{line.rstrip()} # "{workspace.name}",')
            elif 'remote' in line and '"dev"' not in line:
                print(f'{line.rstrip()} # "dev",')
            else:
                print(line, end="")

    return odev.workspace
