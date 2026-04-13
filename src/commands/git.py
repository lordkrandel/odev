import sys
from typing import Optional

import pl
import tools
from commands.common import WorkspaceNameArgument
from odev import odev
from git import Git
from invoke import UnexpectedExit
from templates import main_repos


@odev.git.command()
def clean():
    """
        Git clean all repos
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    pl.run(
        "git -C {path} clean -xdf",
        repos=odev.workspace.repos,
    )


@odev.git.command()
def reset(
    ask: bool = True,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    """
        Git reset on all workspaces, hard by default
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    if not ask or tools.strtobool(tools.input_text("Do you wanna reset all changes? (Y/n)")) in (True, 'default'):
        pl.run(
            "git -C {path} reset --hard",
            repos=odev.workspace.repos,
        )
        return False
    return True


@odev.git.command()
def status(
    extended: bool = True,
    workspace_name: Optional[str] = WorkspaceNameArgument(default='last')
):
    """
        Display status for all repos for current workspace.
    """
    if extended:
        print(f"{odev.project.path} - {odev.workspace.name}")
    for repo_name, repo in odev.workspace.repos.items():
        path = odev.paths.repo(repo_name)
        if not path.is_dir():
            print(f"Repository {repo_name} hasn't been cloned yet.")
            continue
        ret = Git.status(path, extended=extended, name=repo_name)
        if not extended and ret.stdout:
            return False
    return True


@odev.git.command()
def diff(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-diffs all repositories.
    """
    if not odev.project:
        sys.exit("Project not found in folder")
    pl.run(
        "git -C {path} status --untracked-files --short",
        "git -C {path} diff",
        "git -C {path} diff --cached",
        repos=odev.workspace.repos,
    )


@odev.git.command()
def fetch(origin: bool = False, workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-fetches multiple repositories.
    """
    workspace = odev.workspace if not origin else None
    for repo_name, repo in tools.select_repositories("fetch", workspace, checked=main_repos).items():
        print(f"Fetching {repo_name}...")
        path = odev.paths.repo(repo_name)
        if origin:
            Git.fetch(path, repo_name, "origin", "")
    else:
            Git.fetch(path, repo_name, repo.remote, repo.branch)


@odev.git.command()
def pull(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
        Git-pulls selected repos for current workspace.
    """
    for repo_name in tools.select_repositories("pull", odev.workspace, checked=main_repos):
        print(f"Pulling {repo_name}...")
        repo = odev.workspace.repos[repo_name]
        Git.pull(odev.paths.repo(repo_name), repo.remote, repo.branch)


def _checkout_repo(repo_name, repo, force_create=False):
    path = odev.paths.repo(repo_name)
    target = f"{repo_name} {repo.remote}/{repo.branch}"
    try:
        print(f"Fetching {target}...")
        Git.fetch(path, repo_name, repo.remote, repo.branch)
    except UnexpectedExit:
        if not force_create:
            raise
        print(f"Creating {target}...")
        Git.checkout(path, repo.branch, options="-B")
    print(f"Checking out {target}...")
    Git.checkout(path, repo.branch)
    print(f"Cleaning {path}...")
    Git.clean(path, quiet=True)


@odev.git.command()
def checkout(
    workspace_name: Optional[str] = WorkspaceNameArgument(default=None),
    force_create: bool = False
):
    """
        Git-checkouts multiple repositories.
    """
    repos = (odev.workspace and odev.workspace.repos)
    for repo_name, repo in repos.items():
        print(f"Checkout repo {repo_name} branch {repo.branch}...")
        _checkout_repo(repo_name, repo, force_create=force_create)
    return repos
