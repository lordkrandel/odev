# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import invoke
from external import External
import os


class Git(External):

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
                print("   %s %s" % (name.upper(), (45 - len(name)) * '-'))
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
    def checkout(cls, path, branch):
        context = invoke.Context()
        with context.cd(path):
            current_branch = cls.get_current_branch(path)
            if branch != current_branch:
                context.run('git checkout %s' % branch)

    @classmethod
    def get_current_branch(cls, path):
        context = invoke.Context()
        with context.cd(path):
            return context.run('git branch --show-current', pty=True, hide='out').stdout.strip()

    @classmethod
    def get_remote_branches(cls, path):
        context = invoke.Context()
        with context.cd(path):
            entries = context.run('git branch -r', pty=False, hide='out').stdout.split('\n')
            return [x.strip() for x in entries]

    @classmethod
    def fetch(cls, base_path, repo_name, remote_name, branch_name):
        path = os.path.join(base_path, repo_name)
        context = invoke.Context()
        with context.cd(path):
            context.run('git fetch %s %s' % (remote_name, branch_name))

    @classmethod
    def push(cls, path, force=False):
        context = invoke.Context()
        with context.cd(path):
            context.run(f'git push {"-ff" if force else ""}')

    @classmethod
    def pull(cls, path):
        context = invoke.Context()
        with context.cd(path):
            context.run('git pull')

    @classmethod
    def update_master_branch(cls, base_path, repo_name):
        path = os.path.join(base_path, repo_name)
        cls.fetch(base_path, repo_name, 'origin', 'master')
        context = invoke.Context()
        with context.cd(path):
            context.run('git checkout master')
        cls.pull(path)
