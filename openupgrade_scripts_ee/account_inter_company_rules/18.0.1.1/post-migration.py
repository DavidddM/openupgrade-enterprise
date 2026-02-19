# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _map_rule_type_to_boolean(env):
    """Map old rule_type selection to new Boolean field.

    In 17.0: rule_type = 'invoice_and_refund' | 'so_and_po' (etc.)
    In 18.0: intercompany_generate_bills_refund (Boolean)
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET intercompany_generate_bills_refund = True
        WHERE {} = 'invoice_and_refund'
        """.format(openupgrade.get_legacy_name("rule_type")),
    )


@openupgrade.migrate()
def migrate(env, version):
    _map_rule_type_to_boolean(env)
