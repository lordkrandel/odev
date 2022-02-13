#!/usr/bin/python3
# -*- coding: utf-8 -*-
# pylint: disable=unused-import,wrong-import-position,ungrouped-imports

import consts


while True:
    try:
        from application import odev
    except ValueError as e:
        from project import create_project
        import questionary
        message = "Project not found, do you want to create a new one?"
        if questionary.confirm(message, qmark=consts.QMARK).ask():
            create_project(e.message)
        from application import odev
    import commands
    odev()
