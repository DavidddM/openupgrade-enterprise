# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_renamed_modules = [
    ("account_sepa", "account_iso20022"),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.update_module_names(env.cr, _renamed_modules)
