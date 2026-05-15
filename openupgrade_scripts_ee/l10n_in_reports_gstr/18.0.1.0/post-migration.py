# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """Keep the GST return filing of a company in production.

    17.0 had a production switch for the GST returns
    (``l10n_in_gstr_gst_production_env``) next to the one of the e-invoicing
    (``l10n_in_edi_production_env``, which 18.0 moves to l10n_in); 18.0 files
    the returns with the e-invoicing switch alone. A company in production for
    either service stays in production: e-invoicing never configured gains
    nothing from the switch, while GST returns sent to the sandbox would not be
    filed at all. Companies whose two 17.0 switches differed are listed.
    """
    if not openupgrade.column_exists(
        env.cr, "res_company", "l10n_in_gstr_gst_production_env"
    ):
        return
    env.cr.execute(
        """
        SELECT string_agg(id::text, ', ' ORDER BY id)
        FROM res_company
        WHERE coalesce(l10n_in_gstr_gst_production_env, FALSE)
            <> coalesce(l10n_in_edi_production_env, FALSE)
        """
    )
    differing = env.cr.fetchone()[0]
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET l10n_in_edi_production_env = TRUE
        WHERE l10n_in_gstr_gst_production_env
            AND NOT coalesce(l10n_in_edi_production_env, FALSE)
        """,
    )
    if differing:
        _logger.warning(
            "Companies whose 17.0 GST return and e-invoicing production switches"
            " differed, now both in production: %s",
            differing,
        )
