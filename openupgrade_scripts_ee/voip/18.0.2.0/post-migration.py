# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_voip_config_to_provider(env):
    """Migrate v17 VoIP ir.config_parameter values to the v18 voip.provider record.

    In v17, VoIP settings were stored as ir.config_parameter keys:
    - voip.wsServer → ws_server
    - voip.pbx_ip → pbx_ip
    - voip.mode → mode

    In v18, these are stored on a voip.provider record created by the
    data file (default_voip_provider, noupdate=1).
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE voip_provider vp
        SET ws_server = COALESCE(
                (SELECT value FROM ir_config_parameter
                 WHERE key = 'voip.wsServer'), vp.ws_server),
            pbx_ip = COALESCE(
                (SELECT value FROM ir_config_parameter
                 WHERE key = 'voip.pbx_ip'), vp.pbx_ip),
            mode = CASE
                WHEN (SELECT value FROM ir_config_parameter
                      WHERE key = 'voip.mode') IN ('demo', 'prod')
                THEN (SELECT value FROM ir_config_parameter
                      WHERE key = 'voip.mode')
                ELSE vp.mode
            END
        FROM ir_model_data imd
        WHERE imd.module = 'voip'
        AND imd.name = 'default_voip_provider'
        AND imd.model = 'voip.provider'
        AND vp.id = imd.res_id
        """,
    )


def _assign_voip_provider_to_users(env):
    """Assign the default voip.provider to all existing user settings."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_users_settings rus
        SET voip_provider_id = imd.res_id
        FROM ir_model_data imd
        WHERE imd.module = 'voip'
        AND imd.name = 'default_voip_provider'
        AND imd.model = 'voip.provider'
        AND (rus.voip_provider_id IS NULL OR rus.voip_provider_id = 0)
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_voip_config_to_provider(env)
    _assign_voip_provider_to_users(env)
