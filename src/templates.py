# Part of Odoo. See LICENSE file for full copyright and licensing details.

from repo import Repo


main_repos = ('odoo', 'enterprise')
template_repos = {
    'odoo': Repo(
        'odoo',
        'origin',
        'master',
        ["addons", "odoo/addons"]
    ),
    'enterprise': Repo(
        'enterprise',
        'origin',
        'master',
        ['.']
    ),
    'documentation': Repo(
        'documentation',
        'origin',
        'master',
        []
    ),
    'runbot': Repo(
        'runbot',
        'origin',
        '13.0',
        []
    ),
    'upgrade': Repo(
        'upgrade',
        'origin',
        'master',
        []
    ),
    'iap-apps': Repo(
        'iap-apps',
        'origin',
        'master',
        []
    ),
    'tutorials': Repo(
        'tutorials',
        'origin',
        '17.0',
        ['.']
    )
}

post_hook_template = """# Part of Odoo. See LICENSE file for full copyright and licensing details.

self = locals().get('self', object())
"""
