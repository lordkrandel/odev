# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import os
import re


class JsonMixin():

    @classmethod
    def load_json(cls, fullpath):
        if not os.path.exists(fullpath):
            return None
        with open(fullpath, "r", encoding="utf-8") as f:
            content = f.read() or "{}"
        content = re.sub(r"#.*\n", "", content)
        data = json.loads(content)
        return cls.from_json(data) or cls()

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def to_json(self):
        data = {k: v.to_json() if isinstance(v, JsonMixin) else str(v)
                for k, v in self.__dict__.items()}
        return json.dumps(data, indent=4)

    def save_json(self, fullpath):
        data = self.to_json()
        with open(fullpath, 'w+', encoding='utf-8') as f:
            f.write(data)

    def __str__(self):
        return self.to_json()
