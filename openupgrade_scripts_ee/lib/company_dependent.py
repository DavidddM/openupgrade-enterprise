# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Shared conversion of the enterprise company-dependent fields to 18.0.

17.0 keeps the value of a company-dependent field in ``ir_property`` (one row per
record and company, plus default rows without record); 18.0 keeps it in a jsonb
column of the model's table (``{company_id: value}``) and the defaults in
``ir.default``. The community base end-migration removes the ``ir.property``
model, so ``convert_all`` must run before it, once every module is loaded. Each
field is converted once: the legacy table ``MARKER`` records it, so a second run
reads nothing and changes nothing.
"""

import logging

import psycopg2
from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MARKER = openupgrade.get_legacy_name("company_dependent")

FIELDS = (
    (("account_avatax",), "res.partner", "avalara_exemption_id"),
    (("account_followup",), "res.partner", "followup_next_action_date"),
    (("account_followup",), "res.partner", "followup_responsible_id"),
    (
        ("delivery_ups", "delivery_ups_rest"),
        "res.partner",
        "property_ups_carrier_account",
    ),
    (("hr_payroll_account",), "hr.payroll.structure", "journal_id"),
    (("hr_payroll_account",), "hr.salary.rule", "analytic_account_id"),
    (("hr_payroll_account",), "hr.salary.rule", "account_debit"),
    (("hr_payroll_account",), "hr.salary.rule", "account_credit"),
    (("industry_fsm_sale_report",), "product.template", "worksheet_template_id"),
    (("l10n_be_hr_payroll_fleet",), "fleet.vehicle.model", "can_be_requested"),
    (
        ("l10n_br_avatax",),
        "product.template",
        "l10n_br_property_service_code_origin_id",
    ),
    (("l10n_de_reports",), "res.company", "l10n_de_datev_consultant_number"),
    (("l10n_de_reports",), "res.company", "l10n_de_datev_client_number"),
    (("l10n_ec_edi",), "l10n_ec.taxpayer.type", "profit_withhold_tax_id"),
    (("l10n_ec_edi",), "l10n_ec.taxpayer.type", "vat_goods_withhold_tax_id"),
    (("l10n_ec_edi",), "l10n_ec.taxpayer.type", "vat_services_withhold_tax_id"),
    (("l10n_ec_edi",), "product.template", "l10n_ec_withhold_tax_id"),
    (("sale_renting",), "product.template", "extra_hourly"),
    (("sale_renting",), "product.template", "extra_daily"),
    (("sale_stock_renting",), "product.template", "preparation_time"),
)

COLUMNS = (
    (
        ("l10n_de_reports",),
        "res.partner",
        "l10n_de_datev_identifier",
        openupgrade.get_legacy_name("l10n_de_datev_identifier"),
    ),
    (
        ("l10n_de_reports",),
        "res.partner",
        "l10n_de_datev_identifier_customer",
        openupgrade.get_legacy_name("l10n_de_datev_identifier_customer"),
    ),
)

_VALUE_COLUMNS = {
    "boolean": "value_integer::boolean",
    "integer": "value_integer",
    "float": "value_float",
    "monetary": "value_float",
    "date": "value_datetime::date",
    "datetime": "value_datetime",
}


def _ensure_marker(cr):
    """Create the legacy table that records the converted fields."""
    cr.execute(
        sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {} (
                model varchar NOT NULL,
                field varchar NOT NULL,
                source varchar NOT NULL,
                records integer NOT NULL,
                defaults integer NOT NULL,
                PRIMARY KEY (model, field)
            )
            """
        ).format(sql.Identifier(MARKER))
    )


def _converted(cr, model, field):
    """Return whether the field was already converted on this database."""
    cr.execute(
        sql.SQL("SELECT 1 FROM {} WHERE model = %s AND field = %s").format(
            sql.Identifier(MARKER)
        ),
        (model, field),
    )
    return bool(cr.fetchone())


def _mark(cr, model, field, source, records, defaults):
    """Record a converted field with the number of records and defaults moved."""
    cr.execute(
        sql.SQL(
            "INSERT INTO {} (model, field, source, records, defaults)"
            " VALUES (%s, %s, %s, %s, %s)"
        ).format(sql.Identifier(MARKER)),
        (model, field, source, records, defaults),
    )


def _installed(cr, modules):
    """Return whether one of ``modules`` is installed."""
    cr.execute(
        "SELECT 1 FROM ir_module_module WHERE name IN %s AND state = 'installed'",
        (tuple(modules),),
    )
    return bool(cr.fetchone())


def _target(env, model, field):
    """Return the 18.0 field if it is a company-dependent field of a loaded model."""
    if model not in env.registry:
        return None
    target = env[model]._fields.get(field)
    if target is None or not target.company_dependent or not target.store:
        return None
    return target


def _value_expression(env, target):
    """SQL expression reading the 17.0 value of ``target`` from an ir_property row.

    Many-to-one values whose record no longer exists become NULL, so the 18.0
    column never points at a missing record.
    """
    if target.type == "many2one":
        reference = sql.SQL("NULLIF(SPLIT_PART(value_reference, ',', 2), '')::integer")
        return sql.SQL(
            "CASE WHEN EXISTS (SELECT 1 FROM {table} WHERE id = {ref}) THEN {ref} END"
        ).format(table=sql.Identifier(env[target.comodel_name]._table), ref=reference)
    return sql.SQL(_VALUE_COLUMNS.get(target.type, "value_text"))


def _field_id(cr, model, field):
    """Return the id of the ir_model_fields row the 17.0 properties point at."""
    cr.execute(
        "SELECT id FROM ir_model_fields WHERE model = %s AND name = %s", (model, field)
    )
    row = cr.fetchone()
    return row[0] if row else None


def _convert_properties(env, model, field, target):
    """Move the ir_property rows of one field into its jsonb column and ir.default.

    A row with a record and a company gives that company's value; a row with a
    record and no company gives the value of every company that has no row of
    its own; a row without record is the company's default (``ir.default``).
    Returns the number of records and defaults written.
    """
    cr = env.cr
    field_id = _field_id(cr, model, field)
    if not field_id:
        return 0, 0
    table = env[model]._table
    value = _value_expression(env, target)
    cr.execute(
        sql.SQL(
            """
            WITH prop AS (
                SELECT NULLIF(SPLIT_PART(res_id, ',', 2), '')::integer AS res,
                    company_id, {value} AS value
                FROM ir_property
                WHERE fields_id = %(field_id)s AND res_id LIKE %(prefix)s
            ), spread AS (
                SELECT res, company_id, value FROM prop WHERE company_id IS NOT NULL
                UNION ALL
                SELECT p.res, c.id, p.value
                FROM prop p CROSS JOIN res_company c
                WHERE p.company_id IS NULL AND NOT EXISTS (
                    SELECT 1 FROM prop q WHERE q.res = p.res AND q.company_id = c.id
                )
            ), agg AS (
                SELECT res, jsonb_object_agg(company_id, value) AS value
                FROM spread GROUP BY res
            )
            UPDATE {table} t SET {column} = agg.value
            FROM agg WHERE t.id = agg.res
            """
        ).format(
            value=value, table=sql.Identifier(table), column=sql.Identifier(field)
        ),
        {"field_id": field_id, "prefix": model + ",%"},
    )
    records = cr.rowcount
    cr.execute(
        sql.SQL(
            "SELECT company_id, {value} FROM ir_property"
            " WHERE fields_id = %s AND res_id IS NULL ORDER BY company_id NULLS FIRST"
        ).format(value=value),
        (field_id,),
    )
    defaults = 0
    for company_id, default in cr.fetchall():
        try:
            with cr.savepoint():
                env["ir.default"].set(model, field, default, company_id=company_id)
            defaults += 1
        except ValidationError as error:
            _logger.warning(
                "company-dependent %s.%s: default %r of company %s not kept: %s",
                model,
                field,
                default,
                company_id,
                error,
            )
    return records, defaults


def _convert_column(env, model, field, legacy, company_column):
    """Fill the jsonb column of a field that was a plain column in 17.0.

    A record with a company gets its 17.0 value for that company, a record
    without company for every company, as 17.0 showed the same value to all of
    them. Empty and zero values stay empty. Returns the number of records and
    of defaults (always 0).
    """
    cr = env.cr
    table = env[model]._table
    if not openupgrade.column_exists(cr, table, legacy):
        return 0, 0
    cr.execute(
        sql.SQL(
            """
            UPDATE {table} t SET {column} = agg.value
            FROM (
                SELECT r.id, jsonb_object_agg(c.id, r.{legacy}) AS value
                FROM {table} r
                JOIN res_company c ON r.{company} IS NULL OR c.id = r.{company}
                WHERE r.{legacy} IS NOT NULL AND r.{legacy} <> 0
                GROUP BY r.id
            ) agg
            WHERE t.id = agg.id
            """
        ).format(
            table=sql.Identifier(table),
            column=sql.Identifier(field),
            legacy=sql.Identifier(legacy),
            company=sql.Identifier(company_column),
        )
    )
    return cr.rowcount, 0


def _run(env, model, field, source, convert, *args):
    """Convert one field in its own savepoint unless the marker has it.

    A failing field is rolled back alone and logged as an error; its 17.0 data
    stays where it was (the ir_property table outlives the upgrade), so the
    other fields are still converted.
    """
    cr = env.cr
    if _converted(cr, model, field):
        _logger.info("company-dependent %s.%s: already converted", model, field)
        return
    try:
        with cr.savepoint():
            records, defaults = convert(env, model, field, *args)
            _mark(cr, model, field, source, records, defaults)
    except psycopg2.Error as error:
        _logger.error(
            "company-dependent %s.%s: not converted, left in %s: %s",
            model,
            field,
            source,
            error,
        )
        return
    _logger.info(
        "company-dependent %s.%s: %s records and %s defaults from %s",
        model,
        field,
        records,
        defaults,
        source,
    )


def convert_all(env):
    """Convert every field of ``FIELDS`` and ``COLUMNS`` whose module is installed.

    A field is skipped when ir_property is gone, when its module is not
    installed, or when the 18.0 registry does not hold it as a stored
    company-dependent field.
    """
    cr = env.cr
    _ensure_marker(cr)
    has_properties = openupgrade.table_exists(cr, "ir_property")
    for modules, model, field in FIELDS:
        target = _target(env, model, field)
        if not has_properties or target is None or not _installed(cr, modules):
            continue
        _run(env, model, field, "ir_property", _convert_properties, target)
    for modules, model, field, legacy in COLUMNS:
        if _target(env, model, field) is None or not _installed(cr, modules):
            continue
        _run(env, model, field, legacy, _convert_column, legacy, "company_id")
    env.invalidate_all()
