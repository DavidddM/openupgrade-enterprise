# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _link_sla_products(env):
    """Give each SLA policy the services that pointed at it in 17.0.

    17.0 keeps the policy on the product: ``product.template.sla_id``, a
    company-dependent field stored in ir_property, which links the SLA to the
    order lines of that product when an order is confirmed. 18.0 drops the
    field and the order line link and keeps the services on the policy
    (``helpdesk.sla.product_ids``). Each product value of each company becomes
    one link; links to records that no longer exist are skipped.
    """
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO helpdesk_sla_product_template_rel
            (helpdesk_sla_id, product_template_id)
        SELECT DISTINCT sla.id, pt.id
        FROM ir_property p
        JOIN ir_model_fields f ON f.id = p.fields_id
            AND f.model = 'product.template' AND f.name = 'sla_id'
        JOIN helpdesk_sla sla
            ON sla.id = NULLIF(SPLIT_PART(p.value_reference, ',', 2), '')::integer
        JOIN product_template pt
            ON pt.id = NULLIF(SPLIT_PART(p.res_id, ',', 2), '')::integer
        WHERE p.res_id LIKE 'product.template,%'
            AND p.value_reference LIKE 'helpdesk.sla,%'
        ON CONFLICT DO NOTHING
        """,
    )
    env.cr.execute(
        """
        SELECT p.company_id, p.value_reference
        FROM ir_property p
        JOIN ir_model_fields f ON f.id = p.fields_id
            AND f.model = 'product.template' AND f.name = 'sla_id'
        WHERE p.res_id IS NULL AND p.value_reference IS NOT NULL
        """
    )
    for company_id, reference in env.cr.fetchall():
        _logger.warning(
            "helpdesk_sale_timesheet: default SLA policy %s of company %s applied to"
            " every service in 17.0 and has no 18.0 equivalent; set the services"
            " on the policy by hand",
            reference,
            company_id,
        )


def _report_order_line_links(env):
    """Log the 17.0 order line links that no product policy explains.

    18.0 can only attach a policy to a whole service, so such a link (set by
    hand on the policy, or left from a product whose policy changed later) is
    not turned into a product link, which would apply the policy to every
    future ticket of that service.
    """
    if not openupgrade.table_exists(env.cr, "helpdesk_sla_sale_order_line_rel"):
        return
    env.cr.execute(
        """
        SELECT rel.helpdesk_sla_id, pp.product_tmpl_id,
            array_agg(DISTINCT rel.sale_order_line_id ORDER BY rel.sale_order_line_id)
        FROM helpdesk_sla_sale_order_line_rel rel
        JOIN sale_order_line sol ON sol.id = rel.sale_order_line_id
        JOIN product_product pp ON pp.id = sol.product_id
        WHERE NOT EXISTS (
            SELECT 1 FROM helpdesk_sla_product_template_rel r
            WHERE r.helpdesk_sla_id = rel.helpdesk_sla_id
                AND r.product_template_id = pp.product_tmpl_id
        )
        GROUP BY rel.helpdesk_sla_id, pp.product_tmpl_id
        ORDER BY rel.helpdesk_sla_id, pp.product_tmpl_id
        """
    )
    for sla_id, template_id, line_ids in env.cr.fetchall():
        _logger.warning(
            "helpdesk_sale_timesheet: SLA policy %s was linked to order lines %s"
            " of product template %s, which has no such policy; not linked to"
            " the product",
            sla_id,
            line_ids,
            template_id,
        )


@openupgrade.migrate()
def migrate(env, version):
    """Move the SLA policies of the services from the products to the policies.

    Runs before the base end-migration removes the ir.property model; the
    insert ignores existing links, so a second run changes nothing.
    """
    if openupgrade.table_exists(env.cr, "ir_property"):
        _link_sla_products(env)
    _report_order_line_links(env)
