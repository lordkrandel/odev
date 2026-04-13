import re
from datetime import datetime
from typing import Optional

from typer import Context, Argument

import pl
from odev import odev
from commands.common import WorkspaceNameArgument


def get_name(name="QuickSave"):
    return f"{name}_{datetime.now().strftime('%a%d%b%Y_%H%M%S')}"


@odev.slot.command(name="save")
def save(
    ctx: Context,
    workspace_name: Optional[str] = WorkspaceNameArgument(),
    name: Optional[str] = Argument(default="QuickSave"),
):
    pl.run(
        f"git -C {{path}} stash push -u -m '{get_name(name)}'",
        repos=odev.workspace.repos,
    )


@odev.slot.command(name="load")
def load(
    ctx: Context,
    name: Optional[str] = Argument(default='QuickSave'),
    workspace_name: Optional[str] = WorkspaceNameArgument(),
):
    output = pl.run(
        f"git -C {{path}} stash list --grep='{name}'",
        repos=odev.workspace.repos,
        header=False,
        output=False,
    )
    result = [
        {
            k: int(v) if v.isdigit() else v
            for k, v in groups.items()
        }
        for line in output.splitlines()
        if (name in line)
        and (match := re.match(r'stash@{(?P<stash_no>\d+)}: On (?P<branch>.*): (?P<title>.*)$', line))
        and (groups := match.groupdict())
    ]
    for line in result:
        if name == 'QuickSave':
            line['title'] = re.sub(r'_?QuickSave_?', '', line['title'])
        print(f"#{line['stash_no']}: {line['title']} ({line['branch']})")
