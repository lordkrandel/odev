# Part of Odoo. See LICENSE file for full copyright and licensing details.
# ruff: noqa: T201

import invoke
from external import External
from pathlib import Path
import re


class Git(External):

    @classmethod
    def clean(cls, folder='.', quiet=False):
        context = invoke.Context()
        with context.cd(folder):
            context.run(f'git clean -xdf{"q" if quiet else ""}')

    @classmethod
    def get_editor(cls):
        return invoke.Context().run('git config --get core.editor', pty=True, hide=True).stdout.strip()

    @classmethod
    def clone(cls, repository, branch, directory):
        cls.run(f'git clone --branch {branch} --single-branch {repository} {directory}')

    @classmethod
    def add_remote(cls, name, url, path):
        context = invoke.Context()
        with context.cd(path):
            context.run(f'git remote add {name} {url}')

    @classmethod
    def status(cls, path, extended=False, name=False):
        context = invoke.Context()
        with context.cd(path):
            if extended:
                print()
                print(f"   {name}/")
                context.run('git log --format="   %s (%h)" -n 1')
                return context.run('git -c color.status=always status -sb', pty=True)
            else:
                return context.run('git status -s', pty=True, hide='out')

    @classmethod
    def stash(cls, path):
        context = invoke.Context()
        with context.cd(path):
            context.run('git stash -a')

    @classmethod
    def checkout(cls, path, branch, options=None):
        context = invoke.Context()
        with context.cd(path):
            current_branch = cls.get_current_branch(path)
            if branch != current_branch:
                context.run('git checkout %s %s' % (options or '', branch))

    @classmethod
    def get_current_branch(cls, path):
        context = invoke.Context()
        with context.cd(path):
            return context.run('git branch --show-current', pty=True, hide='out').stdout.strip()

    @classmethod
    def get_remote_branches(cls, path, remote=None, worktree=False):
        context = invoke.Context()
        with context.cd(path):
            if worktree:
                command = f'git ls-remote --heads {remote}'
            else:
                command = 'git branch -r' + (('l "' + remote + '/*"') if remote else '')
            entries = context.run(command, pty=False, hide='out').stdout
            if worktree:
                return re.findall('refs/heads/(.*)\n', entries)
            else:
                len_remote = len(remote) + 1 if remote else 0
                return [x.strip()[len_remote:] for x in entries.split('\n')]

    @classmethod
    def diff(cls, path, repo_name):
        context = invoke.Context()
        with context.cd(path):
            print(f'{repo_name}:: {"-" * (80 - len(repo_name))}')
            context.run('git diff')

    @classmethod
    def fetch(cls, path, repo_name, remote_name, branch_name):
        context = invoke.Context()
        with context.cd(path):
            context.run('git fetch %s %s' % (remote_name, branch_name))

    @classmethod
    def push(cls, path, force=False):
        context = invoke.Context()
        with context.cd(path):
            context.run(f'git push {"-ff" if force else ""}')

    @classmethod
    def pull(cls, path, remote, branch_name):
        context = invoke.Context()
        with context.cd(path):
            context.run(f'git pull {remote} {branch_name}')

    @classmethod
    def update_master_branch(cls, base_path, repo_name):
        path = Path(base_path) / repo_name
        cls.fetch(base_path, repo_name, 'origin', 'master')
        context = invoke.Context()
        with context.cd(path):
            context.run('git checkout master')
        cls.pull(path, 'origin', 'master')

    @classmethod
    def worktree_add(cls, branch, path, new=False):
        context = invoke.Context()
        with context.cd(path):
            context.run(f'git worktree add ../{branch} {branch}')
