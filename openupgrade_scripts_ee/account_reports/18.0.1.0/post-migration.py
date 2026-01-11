# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _fill_tax_closing_report_id(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_move am
        SET tax_closing_report_id = ar.id
        FROM account_report ar
        WHERE ar.country_id = (
            SELECT account_fiscal_country_id
            FROM res_company
            WHERE id = am.company_id
        )
        AND ar.root_report_id = (
            SELECT id FROM account_report WHERE id = ar.root_report_id
        )
        AND am.tax_closing_end_date IS NOT NULL
        AND am.tax_closing_report_id IS NULL
        AND ar.availability_condition = 'country'
        """,
    )


def _migrate_tax_closing_activity_res_model(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE mail_activity ma
        SET res_model = 'account.journal',
            res_model_id = (
                SELECT id FROM ir_model WHERE model = 'account.journal'
            ),
            res_id = am.journal_id
        FROM mail_activity_type mat, account_move am
        WHERE ma.activity_type_id = mat.id
        AND mat.category = 'tax_report'
        AND ma.res_model = 'account.move'
        AND ma.res_id = am.id
        """,
    )


def _delete_obsolete_records(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "account_reports.default_followup_trust",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _fill_tax_closing_report_id(env)
    _migrate_tax_closing_activity_res_model(env)
    _delete_obsolete_records(env)
