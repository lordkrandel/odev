import sys
from pathlib import Path
from typing import Optional

from commands.common import WorkspaceNameArgument
from odev import odev


@odev.path.command()
def venv(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Path to the activate script for the current virtual environment.
    """
    print(Path(odev.project.path) / odev.workspace.venv_path)


@odev.path.command()
def hook(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Print the post_hook python full path
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    print(odev.paths.workspace(odev.workspace.name) / Path(odev.workspace.post_hook_script))


@odev.path.command()
def rc(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Print the .odoorc config with default editor.
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    print(odev.paths.project / Path(odev.workspace.rc_file))


@odev.path.command()
def projects():
    """
        Print the projects folder
    """
    print(odev.paths.projects)


@odev.path.command()
def workspaces():
    """
        Output the path of the workspaces folder
    """
    print(f"{odev.paths.config / 'workspaces' / odev.project.name}")


@odev.path.command()
def workspace(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    edit: bool = False,
    name: bool = False,
    file: bool = False
):
    """
        Display currently selected workspace data.
    """
    if not odev.workspace:
        print(f"No workspace named '{workspace_name}' found")
        return
    print(odev.paths.workspace_file(odev.workspace.name))


@odev.path.command()
def base(
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    edit: bool = False,
    name: bool = False,
    file: bool = False
):
    """
        Display currently selected workspace data.
    """
    if not odev.workspace:
        print(f"No workspace named '{workspace_name}' found")
        return
    print(odev.paths.workspace(odev.workspace.name))
