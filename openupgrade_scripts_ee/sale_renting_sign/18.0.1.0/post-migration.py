# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Link the signature requests of rental orders through ``reference_doc``.

    17.0 linked a request to its rental order with ``sign.request.sale_order_id``;
    18.0 drops that field and finds the requests of an order through the
    generic ``reference_doc`` of sign (``sale.order,<id>``), which sign creates
    empty. Requests already linked to another document keep that link.
    """
    if not openupgrade.column_exists(env.cr, "sign_request", "sale_order_id"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sign_request
        SET reference_doc = 'sale.order,' || sale_order_id
        WHERE sale_order_id IS NOT NULL AND reference_doc IS NULL
        """,
    )
