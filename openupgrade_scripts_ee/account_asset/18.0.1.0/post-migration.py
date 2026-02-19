# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _populate_asset_model_m2m(env):
    """Populate the new Many2many from the old Many2one.

    In 17.0: account.account.asset_model (Many2one -> account.asset)
    In 18.0: account.account.asset_model_ids (Many2many -> account.asset)
    """
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO account_account_account_asset_rel
            (account_account_id, account_asset_id)
        SELECT id, {old_column}
        FROM account_account
        WHERE {old_column} IS NOT NULL
        ON CONFLICT DO NOTHING
        """.format(old_column=openupgrade.get_legacy_name("asset_model")),
    )


@openupgrade.migrate()
def migrate(env, version):
    _populate_asset_model_m2m(env)
