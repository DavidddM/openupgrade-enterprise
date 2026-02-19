# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _handle_iot_channel_abstract(env):
    """Handle iot.channel Model → AbstractModel transition.

    The model iot.channel became an AbstractModel in v18, so we need to drop
    the table and clean up ir_model references before the ORM tries to
    register it without a backing table.
    """
    openupgrade.logged_query(
        env.cr,
        "DROP TABLE IF EXISTS iot_channel CASCADE",
    )
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'iot' AND name = 'model_iot_channel'
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model
        WHERE model = 'iot.channel'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _handle_iot_channel_abstract(env)
