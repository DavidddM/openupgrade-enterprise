# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_table_renames = [
    ("account_report_footnote", "account_report_annotation"),
]

_field_renames = [
    ("account.report", "account_report", "footnotes_ids", "annotations_ids"),
]

_xmlid_renames = [
    (
        "account_reports.access_account_report_footnote_readonly",
        "account_reports.access_account_report_annotation_readonly",
    ),
    (
        "account_reports.access_account_report_footnote",
        "account_reports.access_account_report_annotation",
    ),
    (
        "account_reports.access_account_report_footnote_invoice",
        "account_reports.access_account_report_annotation_invoice",
    ),
    (
        "account_reports.account_financial_report_totalincome0",
        "account_reports.account_financial_report_revenue0",
    ),
    (
        "account_reports.account_financial_report_totalincome0_balance",
        "account_reports.account_financial_report_revenue0_balance",
    ),
    (
        "account_reports.account_financial_report_income0",
        "account_reports.account_financial_report_operating_income0",
    ),
    (
        "account_reports.account_financial_report_income0_balance",
        "account_reports.account_financial_report_operating_income0_balance",
    ),
]


def _rename_footnote_model(env):
    openupgrade.rename_models(
        env.cr,
        [("account.report.footnote", "account.report.annotation")],
    )


def _add_annotation_columns(env):
    if not openupgrade.column_exists(env.cr, "account_report_annotation", "date"):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE account_report_annotation
            ADD COLUMN date DATE
            """,
        )
    if not openupgrade.column_exists(
        env.cr, "account_report_annotation", "fiscal_position_id"
    ):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE account_report_annotation
            ADD COLUMN fiscal_position_id INTEGER
            """,
        )


def _rename_opening_date_filter_keys(env):
    """Rename default_opening_date_filter selection keys last_* → previous_*.

    In 17.0, account.report used last_month/last_quarter/last_year/last_tax_period.
    In 18.0, these were renamed to previous_month/previous_quarter/previous_year/
    previous_tax_period.

    The community OpenUpgrade account/18.0.1.3 pre-migration has this conversion
    backwards (previous_* → last_*, which is a no-op on 17.0 data). Without
    correction, the ORM crashes during flush/recompute with:
        ValueError: Wrong value for account.report.default_opening_date_filter: 'last_month'

    We compensate here because account_reports extends account.report and its 18.0
    data files depend on previous_* values. This runs after the community account
    script and before the ORM flush. If the community script is ever fixed, the
    WHERE clause simply matches zero rows.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report
        SET default_opening_date_filter = 'previous_' || substr(
            default_opening_date_filter, 6)
        WHERE left(default_opening_date_filter, 5) = 'last_'
        """,
    )


def _preserve_tax_closing_end_date(env):
    if openupgrade.column_exists(env.cr, "account_move", "tax_closing_end_date"):
        openupgrade.copy_columns(
            env.cr,
            {"account_move": [("tax_closing_end_date", None, None)]},
        )


def _update_report_line_codes(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_line
        SET code = 'REV'
        WHERE code = 'INC'
        AND id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_totalincome0'
            AND model = 'account.report.line'
        )
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_line
        SET code = 'INC'
        WHERE code = 'OPINC'
        AND id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_income0'
            AND model = 'account.report.line'
        )
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_line
        SET code = 'OEXP'
        WHERE code = 'DEP'
        AND id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_depreciation0'
            AND model = 'account.report.line'
        )
        """,
    )


def _flatten_report_line_hierarchy(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_line
        SET parent_id = NULL
        WHERE parent_id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name IN (
                'account_financial_report_totalincome0',
                'account_financial_report_gross_profit0',
                'account_financial_report_less_expenses0'
            )
            AND model = 'account.report.line'
        )
        """,
    )


def _delete_obsolete_report_lines(env):
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "account_reports.account_financial_report_less_expenses0",
        ],
    )


def _update_expression_engines(env):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_expression
        SET engine = 'domain',
            formula = $$[('account_id.account_type', '=', 'income')]$$,
            subformula = '-sum'
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_totalincome0_balance'
            AND model = 'account.report.expression'
        )
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_line
        SET groupby = NULL
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_income0'
            AND model = 'account.report.line'
        )
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_report_expression
        SET engine = 'aggregation',
            formula = 'REV.balance - COS.balance - EXP.balance',
            subformula = NULL
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_reports'
            AND name = 'account_financial_report_income0_balance'
            AND model = 'account.report.expression'
        )
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_tables(env.cr, _table_renames)
    _rename_footnote_model(env)
    _add_annotation_columns(env)
    openupgrade.rename_fields(env, _field_renames)
    _update_report_line_codes(env)
    _update_expression_engines(env)
    _flatten_report_line_hierarchy(env)
    openupgrade.rename_xmlids(env.cr, _xmlid_renames)
    _delete_obsolete_report_lines(env)
    _preserve_tax_closing_end_date(env)
    _rename_opening_date_filter_keys(env)
