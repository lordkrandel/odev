import commands
from contextlib import redirect_stdout
import unittest
import io


def decorate_test(wrapped_func):
    def wrap(self, *args, **kwargs):
        f = io.StringIO()
        with redirect_stdout(f):
            expected_stdout = wrapped_func()
        self.assertEqual(expected_stdout, f.getvalue())
    return wrap

class TestClass(unittest.TestCase):
    pass

class TestProjects(TestClass):
    @decorate_test
    def test_empty(self):
        commands.projects()
        return "?"
