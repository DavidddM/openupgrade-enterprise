# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_sla_sale_lines_to_products(env):
    """Migrate helpdesk.sla Many2many from sale.order.line to product.template.

    17.0: sale_line_ids (M2M → sale.order.line,
          table: helpdesk_sla_sale_order_line_rel)
    18.0: product_ids (M2M → product.template,
          table: helpdesk_sla_product_template_rel)

    For each SLA, extract distinct product_template_id from linked sale order
    lines and populate the new relation table.
    """
    if not openupgrade.table_exists(env.cr, "helpdesk_sla_sale_order_line_rel"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO helpdesk_sla_product_template_rel
            (helpdesk_sla_id, product_template_id)
        SELECT DISTINCT
            rel.helpdesk_sla_id,
            pp.product_tmpl_id
        FROM helpdesk_sla_sale_order_line_rel rel
        JOIN sale_order_line sol ON sol.id = rel.sale_order_line_id
        JOIN product_product pp ON pp.id = sol.product_id
        WHERE pp.product_tmpl_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_sla_sale_lines_to_products(env)
