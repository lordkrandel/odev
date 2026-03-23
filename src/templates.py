# Part of Odoo. See LICENSE file for full copyright and licensing details.

from repo import Repo


main_repos = ('odoo', 'enterprise')

template_repos = {
    'odoo':          Repo('origin', 'master'),
    'enterprise':    Repo('origin', 'master'),
    'documentation': Repo('origin', 'master'),
    'runbot':        Repo('origin', '18.0'),
    'upgrade':       Repo('origin', 'master'),
    'upgrade-util':  Repo('origin', 'master'),
    'iap-apps':      Repo('origin', 'master'),
    'tutorials':     Repo('origin', '19.0')
}

addons_path = {
    'odoo': ["addons", "odoo/addons"],
    'enterprise': ["."],
    'iap-apps': ["iap_common", "iap_extract", "iap_odoo", "iap_services", "iap_website_scraper"],
}

upgrade_path = {
    'upgrade': ['migrations'],
    'upgrade-util': ['src'],
}

origins = {
    'odoo': {
        'origin': 'git@github.com:odoo/odoo',
        'dev': 'git@github.com:odoo-dev/odoo',
    },
    'enterprise': {
        'origin': 'git@github.com:odoo/enteprise',
        'dev': 'git@github.com:odoo-dev/enteprise',
    },
    'upgrade-util': {
        'origin': 'git@github.com:odoo/upgrade-util',
    },
    'upgrade': {
        'origin': 'git@github.com:odoo/upgrade',
    },
    'iap-apps': {
        'origin': 'git@github.com:odoo/iap-apps',
    },
    'documentation': {
        'origin': 'git@github.com:odoo/documentation',
    },
}

post_hook_template = """# Part of Odoo. See LICENSE file for full copyright and licensing details.

self = locals().get('self', object())
"""
