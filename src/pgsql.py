# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import os
from paths import ensure
from external import External


class PgSql(External):

    @classmethod
    def dump(cls, db_name, dump_fullpath):
        ensure(os.path.dirname(dump_fullpath))
        return cls.run(f'pg_dump -F p -b -f {dump_fullpath} {db_name}')

    @classmethod
    def restore(cls, db_name, dump_fullpath):
        if not os.path.exists(dump_fullpath):
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
        output = cls.run(f'dropdb --if-exists {db_name}').stdout.strip()
        output += '\n' + cls.run(f'createdb {db_name}').stdout.strip()
        return output
