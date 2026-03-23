# Part of Odoo. See LICENSE file for full copyright and licensing details.

import configparser
from io import StringIO
from pathlib import Path


class Rc:

    def __init__(self, config_list=None):
        config = configparser.ConfigParser(allow_no_value=True)
        config.read_file(StringIO("\n".join(config_list or [])))
        self.options = config['options']

    def check_db_name(self, db_name):
        valid = db_name == self.db_name
        print(f"Database check {valid and 'OK' or 'NOK'}: workspace->{db_name} rc_file->{self.db_name}")
        assert(valid)

    @property
    def db_name(self):
        return self.options['db_name']
