# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import invoke
from external import External


class Gh(External):

    @classmethod
    def exists(cls):
        return External.which('gh')

    @classmethod
    def make_url(cls, action, owner, repo_name, subaction, *args):
        return f"gh api /{action}/{owner}/{repo_name}" \
             + (f"/{subaction}/{'/'.join([str(arg) for arg in args])}" if subaction and args else '')

    @classmethod
    async def get_pr_info(cls, owner, repo_name, pr_number):
        url = Gh.make_url('repos', owner, repo_name, 'pulls', pr_number)
        return invoke.Context().run(url, warn=True, asynchronous=True)

    @classmethod
    async def get_branch_info(cls, owner, repo_name, branch):
        url = Gh.make_url('repos', owner, repo_name, 'branches', branch)
        return invoke.Context().run(url, warn=True, asynchronous=True)
