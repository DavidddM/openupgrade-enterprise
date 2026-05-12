# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_property_xmlids(env):
    """Drop the xmlids of the 17.0 ir.property defaults of the extra prices.

    18.0 has no ir.property model, so the records cannot be deleted through
    the ORM; only their xmlids go. The ir_property rows stay for the shared
    company-dependent step, which turns them into ir.default values.
    """
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'sale_renting' AND model = 'ir.property'
            AND name IN ('property_extra_hourly', 'property_extra_daily')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    """Clean up after the rental extra prices.

    ``extra_hourly`` and ``extra_daily`` stay company-dependent; their values
    are converted by ``odoo.upgrade.lib.company_dependent`` in the base
    end-migration of this repository.
    """
    _delete_property_xmlids(env)
