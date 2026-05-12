# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_property_xmlids(env):
    """Drop the xmlid of the 17.0 ir.property default of the preparation time.

    18.0 has no ir.property model, so the record cannot be deleted through the
    ORM; only its xmlid goes. The ir_property row stays for the shared
    company-dependent step, which turns it into an ir.default value.
    """
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'sale_stock_renting' AND model = 'ir.property'
            AND name = 'property_padding_time'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    """Clean up after the rental preparation time.

    ``preparation_time`` stays company-dependent; its values are converted by
    ``odoo.upgrade.lib.company_dependent`` in the base end-migration of this
    repository.
    """
    _delete_property_xmlids(env)
