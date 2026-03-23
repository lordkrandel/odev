# Part of Odoo. See LICENSE file for full copyright and licensing details.

from json_mixin import JsonMixin


class Repo(JsonMixin):
    def __init__(self, remote, branch, **kwargs):
        self.remote = remote
        self.branch = branch
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.path = None

    def __copy__(self):
        repo = Repo(self.remote, self.branch)
        if self.path:
            repo.path = str(self.path)
        return repo

    def to_json_excluded(self):
        return ['path'] + super().to_json_excluded()

    @classmethod
    def from_json(cls, data):
        base_data = (
            str(v)
            for k, v in data.items()
            if k in ('remote', 'branch')
        )
        return Repo(
            *base_data,
            **{
                k: v
                for k, v in data.items()
                if k not in base_data
            }
        )
