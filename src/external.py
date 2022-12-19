# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import invoke
import shutil


class External():

    @classmethod
    def run(cls, command, pty=True, hide=None, echo=True):
        if echo:
            print("$ " + command)
        return invoke.run(command, pty=pty, hide=hide)

    @classmethod
    def edit(cls, editor, target, pty=True, hide=None, echo=False):
        return cls.run(f"{editor} {target}", pty, hide, echo)

    @classmethod
    def which(cls, name):
        """Check whether `name` is on PATH and marked as executable."""
        return bool(shutil.which(name))
