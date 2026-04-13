#!/usr/bin/python3

import typer.core
typer.core.rich = None

# load the commands in memory
import commands  # noqa: E402, F401

# start the command handling
from odev import odev  # noqa: E402
odev()
