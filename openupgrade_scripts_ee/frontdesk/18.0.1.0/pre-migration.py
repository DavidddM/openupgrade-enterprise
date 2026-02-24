# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _populate_visitor_company_id(env):
    """Populate required company_id on frontdesk.visitor from its station.

    Falls back to company_id=1 for visitors without a station or stations
    without a company.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE frontdesk_visitor
        ADD COLUMN IF NOT EXISTS company_id integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE frontdesk_visitor fv
        SET company_id = ff.company_id
        FROM frontdesk_frontdesk ff
        WHERE fv.station_id = ff.id
        AND fv.company_id IS NULL
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE frontdesk_visitor
        SET company_id = 1
        WHERE company_id IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _populate_visitor_company_id(env)
