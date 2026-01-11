# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_field_renames = [
    (
        "res.company",
        "res_company",
        "deferred_journal_id",
        "deferred_expense_journal_id",
    ),
    (
        "res.company",
        "res_company",
        "deferred_amount_computation_method",
        "deferred_expense_amount_computation_method",
    ),
]

_xmlid_renames = [
    ("account_accountant.menu_accounting", "accountant.menu_accounting"),
]


def _ensure_accountant_module(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_module_module
        SET state = 'to install'
        WHERE name = 'accountant'
        AND state IN ('uninstalled', 'uninstallable')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _field_renames)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    _ensure_accountant_module(env)
