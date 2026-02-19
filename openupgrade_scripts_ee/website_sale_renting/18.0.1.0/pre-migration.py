# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _add_website_tz_column(env):
    """Pre-add the tz column on the website table with default 'UTC'.

    In 18.0 website_sale_renting adds a required tz field on the website model.
    Pre-creating it avoids NOT NULL constraint violations during the ORM update.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE website ADD COLUMN IF NOT EXISTS tz varchar DEFAULT 'UTC'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _add_website_tz_column(env)
