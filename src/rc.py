# Part of Odoo. See LICENSE file for full copyright and licensing details.

import configparser
from pathlib import Path


class Rc:

    def __init__(self, rc_fullpath):
        config = configparser.ConfigParser()
        config.read(rc_fullpath)
        self.options = config['options']

    def check_db_name(self, db_name):
        valid = db_name == self.db_name
        print(f"Database check {valid and 'OK' or 'NOK'}: workspace->{db_name} rc_file->{self.db_name}")
        assert(valid)

    @property
    def db_name(self):
        return self.options['db_name']

    @property
    def addons(self):
        return self._addons()

    def _addons(self, basepath=''):
        addons = [Path(x) for x in self.options['addons_path'].split(',')]
        if basepath:
            addons = [str(Path(x).relative_to(Path(basepath))) for x in addons]
        return addons
