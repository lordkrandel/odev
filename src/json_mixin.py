import json
from pathlib import Path
import re


class JsonMixin:

    @classmethod
    def load_json(cls, fullpath):
        if not fullpath or not Path(fullpath).exists():
            return {}
        with open(fullpath, encoding="utf-8") as f:
            content = f.read() or "{}"
        content = re.sub(r"#.*\n", "", content)
        data = json.loads(content)
        return cls.from_json(data)

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def to_json_excluded(self):
        return []

    def to_json(self):
        def to_json_inner(subvalue):
            data = {}
            for k, v in subvalue.items():
                if k in self.to_json_excluded():
                    continue
                if isinstance(v, JsonMixin):
                    y = to_json_inner(v.__dict__)
                elif isinstance(v, dict):
                    y = to_json_inner(v)
                elif isinstance(v, list):
                    y = v
                else:
                    y = str(v)
                data[k] = y
            return data
        data = to_json_inner(self.__dict__)
        return json.dumps(data, indent=4)

    def save_json(self, fullpath):
        data = self.to_json()
        with open(fullpath, 'w+', encoding='utf-8') as f:
            f.write(data)

    def __str__(self):
        return self.to_json()
