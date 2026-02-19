# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _populate_asset_vehicle_id(env):
    """Pre-populate vehicle_id on account_asset from linked move lines.

    In 17.0: vehicle_id was a non-stored compute on account.asset
    In 18.0: vehicle_id is now store=True

    We add the column and fill it via SQL from the original_move_line_ids M2M
    (asset_move_line_rel) joined to account_move_line.vehicle_id, avoiding a
    potentially slow ORM recompute on upgrade.
    """
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE account_asset
        ADD COLUMN IF NOT EXISTS vehicle_id integer
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_asset aa
        SET vehicle_id = sub.vehicle_id
        FROM (
            SELECT rel.asset_id, MIN(aml.vehicle_id) AS vehicle_id
            FROM asset_move_line_rel rel
            JOIN account_move_line aml ON aml.id = rel.line_id
            WHERE aml.vehicle_id IS NOT NULL
            GROUP BY rel.asset_id
        ) sub
        WHERE aa.id = sub.asset_id
            AND aa.vehicle_id IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _populate_asset_vehicle_id(env)
