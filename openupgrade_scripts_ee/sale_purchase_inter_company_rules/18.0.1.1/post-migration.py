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
        """.format(
            ou_rule_type
        ),
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET intercompany_generate_purchase_orders = True
        WHERE {} IN ('purchase', 'sale_purchase')
        """.format(
            ou_rule_type
        ),
    )


def _map_auto_validation(env):
    """Carry the automatic validation of generated orders to the 18.0 state.

    17.0 confirms the orders it generates for a company with
    ``auto_validation``; 18.0 reads ``intercompany_document_state``, which
    also posts the bills account_inter_company_rules generates. 17.0 never
    posted generated bills and only offered the flag with an order rule, so
    only a company that synchronized orders gets 'posted'. The 17.0 column
    stays in place.
    """
    if not openupgrade.column_exists(env.cr, "res_company", "auto_validation"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET intercompany_document_state = 'posted'
        WHERE auto_validation
            AND {} IN ('sale', 'purchase', 'sale_purchase')
        """.format(
            openupgrade.get_legacy_name("rule_type")
        ),
    )


@openupgrade.migrate()
def migrate(env, version):
    _map_rule_type_to_booleans(env)
    _map_auto_validation(env)
