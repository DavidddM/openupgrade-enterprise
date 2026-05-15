# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2 import sql

_settings = [
    ("l10n_au_keypay.l10n_au_kp_api_key", "employment_hero_api_key"),
    ("l10n_au_keypay.l10n_au_kp_base_url", "employment_hero_base_url"),
]


def _company_settings(env):
    """Give every company that uses Employment Hero the 17.0 API key and URL.

    17.0 kept one API key and one payroll URL for the whole database in system
    parameters; 18.0 reads them from each company and refuses to sync a
    company without them. Companies with the integration enabled or a business
    id get the 17.0 values where they have none.
    """
    for key, column in _settings:
        openupgrade.logged_query(
            env.cr,
            sql.SQL(
                """
                UPDATE res_company company
                SET {column} = param.value
                FROM ir_config_parameter param
                WHERE param.key = %s
                    AND coalesce(param.value, '') <> ''
                    AND company.{column} IS NULL
                    AND (company.employment_hero_enable
                        OR company.employment_hero_identifier IS NOT NULL)
                """
            ).format(column=sql.Identifier(column)),
            (key,),
        )


def _cron_code(env):
    """Point the 17.0 payrun cron at the 18.0 method.

    The cron is noupdate data, so the 18.0 file does not rewrite it; its 17.0
    code calls a method 18.0 renamed. Code a user changed stays as it is.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_act_server action
        SET code = 'model._eh_payroll_cron_fetch_payrun()'
        FROM ir_cron cron, ir_model_data imd
        WHERE imd.module = 'l10n_employment_hero'
            AND imd.name = 'employment_hero_sync_cron'
            AND imd.model = 'ir.cron'
            AND cron.id = imd.res_id
            AND action.id = cron.ir_actions_server_id
            AND btrim(action.code) = 'model._kp_payroll_cron_fetch_payrun()'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _company_settings(env)
    _cron_code(env)
