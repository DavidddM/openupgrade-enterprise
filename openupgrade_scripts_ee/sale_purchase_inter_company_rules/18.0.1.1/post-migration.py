# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _map_rule_type_to_booleans(env):
    """Map old rule_type selection to new Boolean fields.

    In 17.0: rule_type = 'sale' | 'purchase' | 'sale_purchase'
    In 18.0: intercompany_generate_sales_orders (Boolean)
             intercompany_generate_purchase_orders (Boolean)

    The old rule_type column was preserved as ou_rule_type by
    account_inter_company_rules pre-migration.
    """
    ou_rule_type = openupgrade.get_legacy_name("rule_type")
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET intercompany_generate_sales_orders = True
        WHERE {} IN ('sale', 'sale_purchase')
        """.format(ou_rule_type),
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET intercompany_generate_purchase_orders = True
        WHERE {} IN ('purchase', 'sale_purchase')
        """.format(ou_rule_type),
    )


@openupgrade.migrate()
def migrate(env, version):
    _map_rule_type_to_booleans(env)
