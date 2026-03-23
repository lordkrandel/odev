# Part of Odoo. See LICENSE file for full copyright and licensing details.
# ruff: noqa: T201

import asyncio
import invoke
from collections import namedtuple
from external import External
import re

AsyncProc = namedtuple('AsyncProc', ['returncode', 'stdout', 'stderr'])
class Git(External):

    @classmethod
    async def git_async(cls, args, path):
        proc = await asyncio.create_subprocess_exec(
            'git', *args,
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        status_code = await proc.wait()
        stdout, stderr = await proc.communicate()
        return AsyncProc(status_code, stdout, stderr)

    @classmethod
    async def clean_async(cls, path='.', quiet=False):
        return await cls.git_async(['clean', f'-xdf{"q" if quiet else ""}'], path)

    @classmethod
    def clean(cls, path='.', quiet=False):
        context = invoke.Context()
        with context.cd(path):
            return context.run(f'git clean -xdf{"q" if quiet else ""}')

    @classmethod
    async def reset_async(cls, path='.', hard=False):
        return await cls.git_async(['reset'] + (['--hard'] if hard else []), path)

    @classmethod
    def reset(cls, path='.', hard=False, quiet=False):
        context = invoke.Context()
        hard_str = '--hard ' if hard else ''
        with context.cd(path):
            return context.run(f"git reset {hard_str}")

    @classmethod
    def get_editor(cls):
        return invoke.Context().run('git config --get core.editor', pty=True, hide=True).stdout.strip()

    @classmethod
    def clone(cls, repository, branch, directory):
        return cls.run(f'git clone --branch {branch} --single-branch {repository} {directory}')

    @classmethod
    def add_remote(cls, name, url, path):
        context = invoke.Context()
        with context.cd(path):
            return context.run(f'git remote add {name} {url}')

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
    def stash(cls, path, message=None):
        message = f"-m '{message}'" if message else ''
        path_str = f"-- {path}" if path else ''
        return invoke.Context().run(f"git stash -a {message} {path_str}")

    @classmethod
    async def checkout_async(cls, path, branch, options=None):
        return await cls.git_async(['checkout', '--progress'] + (options or []) + [branch], path=path)

    @classmethod
    def checkout(cls, path, branch, options=None):
        context = invoke.Context()
        with context.cd(path):
            current_branch = cls.get_current_branch(path)
            if branch != current_branch:
                return context.run('git checkout --progress %s %s' % (options or '', branch))

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
            return context.run('git diff')

    @classmethod
    def diff_with_merge_base(cls, path, base_branch, target_branch="HEAD"):
        merge_base = cls.merge_base(path, base_branch, target_branch)
        context = invoke.Context()
        command = f'git diff --name-only {merge_base}...{target_branch}'
        with context.cd(path):
            return [
                x.strip()
                for x in context.run(command, pty=False, hide='out').stdout.split('\n')
                if x
            ]

    @classmethod
    async def fetch_async(cls, path, repo_name, remote_name, branch_name):
        return await cls.git_async(
            ['fetch', '--progress', '--verbose', remote_name, branch_name],
            path=path
        )

    @classmethod
    def fetch(cls, path, repo_name, remote_name, branch_name, options=None):
        context = invoke.Context()
        with context.cd(path):
            command = f"git fetch --progress --verbose {remote_name} {branch_name} {options or ''}"
            return context.run(command)

    @classmethod
    def push(cls, path, force=False):
        context = invoke.Context()
        with context.cd(path):
            return context.run(f'git push {"-ff" if force else ""}')

    @classmethod
    def pull(cls, path, remote, branch_name):
        context = invoke.Context()
        with context.cd(path):
            return context.run(f'git pull {remote} {branch_name}')

    @classmethod
    async def pull_async(cls, path, remote, branch_name):
        return await cls.git_async(['pull', remote, branch_name], path=path)

    @classmethod
    def worktree_add(cls, branch, path, new=False):
        context = invoke.Context()
        with context.cd(path):
            return context.run(f'git worktree add ../{branch} {branch}')

    @classmethod
    def merge_base(cls, path, branch1, branch2):
        context = invoke.Context()
        command = f'git merge-base {branch1} {branch2}'
        with context.cd(path):
            return context.run(command, pty=True, hide='out').stdout.strip()

    @classmethod
    async def merge_base_async(cls, path, branch1, branch2):
        return await cls.git_async(['merge-base', branch1, branch2], path=path)

    @classmethod
    def all_remote_branches(cls, path, remote, filter_func=None):
        context = invoke.Context()
        command = f"git ls-remote --heads {remote} 'refs/heads/??.?' 'refs/heads/saas-??.?'"
        pattern = r'.*refs/heads/(?P<version>(?:saas-)?(?P<number>\d\d\.\d))$'
        with context.cd(path):
            versions_lines = context.run(command, pty=True, hide='out').stdout.strip()
        versions = {}
        for line in (x.strip() for x in versions_lines.splitlines()):
            if version_data := re.match(pattern, line).groupdict():
                number = float(version_data.get('number'))
                if not filter_func or filter_func(number):
                    versions[number] = version_data.get('version')
        return [x[1] for x in sorted(versions.items())]
