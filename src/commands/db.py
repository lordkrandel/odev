from typing import Optional

from typer import Argument

from commands.common import WorkspaceNameArgument
from odev import odev
from pgsql import PgSql


@odev.db.command()
def clear(db_name: Optional[str] = Argument(None, help="Database name"),
             workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Clear database by dropping and recreating it.
    """
    return PgSql.erase(db_name or odev.workspace.db_name)


@odev.db.command()
def dump(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Dump the DB for the selected workspace.
    """
    dump_fullpath = odev.paths.workspace(odev.workspace.name) / odev.workspace.db_dump_file
    print(f"Dumping {odev.workspace.db_name} -> {dump_fullpath}")
    PgSql.dump(odev.workspace.db_name, dump_fullpath)


@odev.db.command()
def restore(workspace_name: Optional[str] = WorkspaceNameArgument()):
    """
         Restore the DB for the selected workspace.
    """
    dump_fullpath = odev.paths.workspace(workspace_name) / odev.workspace.db_dump_file
    print(f"Restoring {odev.workspace.db_name} <- {dump_fullpath}")
    PgSql.restore(odev.workspace.db_name, dump_fullpath)
