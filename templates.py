# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from repo import Repo

template_repos = {
    'odoo': Repo(
        'odoo',
        'git@github.com:odoo-dev/odoo',
        'git@github.com:odoo/odoo',
        'origin',
        'master'
    ),
    'enterprise': Repo(
        'enterprise',
        'git@github.com:odoo-dev/enterprise',
        'git@github.com:odoo/enterprise',
        'origin',
        'master'
    ),
    'documentation': Repo(
        'documentation',
        'git@github.com:odoo/documentation.git',
        'git@github.com:odoo/documentation.git',
        'origin',
        'master'
    ),
    'runbot': Repo(
        'runbot',
        'git@github.com:odoo/runbot.git',
        'git@github.com:odoo/runbot.git',
        'origin',
        '13.0'
    ),
    'upgrade': Repo(
        'runbot',
        'git@github.com:odoo/upgrade.git',
        'git@github.com:odoo/upgrade.git',
        'origin',
        'master'
    ),
    'iap-apps': Repo(
        'runbot',
        'git@github.com:odoo/iap-apps.git',
        'git@github.com:odoo/iap-apps.git',
        'origin',
        'master'
    )
}