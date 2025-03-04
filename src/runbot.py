# Part of Odoo. See LICENSE file for full copyright and licensing details.

import requests
import json
from external import External


class Runbot(External):

    @classmethod
    def make_url(cls, kind, name):
        return f"https://runbot.odoo.com/api/{kind}?name={name}"

    @classmethod
    def _request(cls, kind, name):
        return json.loads(requests.get(Runbot.make_url(kind, name)).content.decode())

    @classmethod
    def branch_info(cls, name):
        return cls._request('branch', name)

    @classmethod
    def bundle_info(cls, name):
        return cls._request('bundle', name)

    @classmethod
    def get_branches(cls, name):
        return {branch['repo'] for branch in cls.bundle_info(name)['branches']}
