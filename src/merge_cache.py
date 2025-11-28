from json_mixin import JsonMixin


class MergeCache(JsonMixin):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
