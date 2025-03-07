# Part of Odoo. See LICENSE file for full copyright and licensing details.

from pathlib import Path
from paths import ensure
from external import External


class PgSql(External):

    @classmethod
    def db_names(cls):
        output = cls.run(
            "psql -c 'SELECT datname FROM pg_database;' -d postgres -t -P pager=off",
            hide=True, echo=False,
        ).stdout
        return [x.strip() for x in output.split('\n')]

    @classmethod
    def dump(cls, db_name, dump_fullpath):
        ensure(Path(dump_fullpath).parent)
        return cls.run(f'pg_dump -F p -b -f {dump_fullpath} {db_name}')

    @classmethod
    def restore(cls, db_name, dump_fullpath):
        if not Path(dump_fullpath):
            raise ValueError("Dump file %s not found." % dump_fullpath)
        cls.erase(db_name)
        return cls.run(f'psql -q -d {db_name} -f {dump_fullpath} > /dev/null')

    @classmethod
    def get_modules(cls, db_name):
        print("Modules in db (%s): " % db_name)
        output = cls.run(f'psql -d {db_name} -A -t -c "select name from ir_module_module where state = \'installed\'" -P pager=off')
        return ",".join(output)

    @classmethod
    def erase(cls, db_name):
        return (
            cls.run(f'dropdb --if-exists {db_name}').stdout.strip()
            + '\n'
            + cls.run(f'createdb --encoding=UTF8 --lc-collate=C --template=template0 {db_name}').stdout.strip()
        )
