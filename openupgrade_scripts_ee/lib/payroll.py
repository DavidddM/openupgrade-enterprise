# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Payroll records 18.0 no longer ships while 17.0 payslips still use them."""

import logging

from psycopg2 import sql

_logger = logging.getLogger(__name__)

MODELS = ("hr.salary.rule", "hr.salary.rule.category", "hr.payslip.input.type")


def _dropped(env):
    """Records of MODELS the end of this update would delete, by model.

    Odoo deletes the records of an updated module whose updatable xmlid the
    update did not load (``ir.model.data._process_end``). Returns
    ``{model: {res_id: ir_model_data id}}``.
    """
    loaded = env.registry.loaded_xmlids
    env.cr.execute(
        """
        SELECT d.id, d.module || '.' || d.name, d.model, d.res_id
        FROM ir_model_data d
        JOIN ir_module_module m ON m.name = d.module AND m.state = 'installed'
        WHERE d.model IN %s AND d.res_id IS NOT NULL
            AND NOT coalesce(d.noupdate, false)
        """,
        (MODELS,),
    )
    dropped = {model: {} for model in MODELS}
    for imd_id, xmlid, model, res_id in env.cr.fetchall():
        if xmlid not in loaded:
            dropped[model][res_id] = imd_id
    return dropped


def _restricting_columns(cr, table):
    """(table, column) pairs whose foreign key to ``table`` refuses a delete."""
    cr.execute(
        """
        SELECT c.conrelid::regclass::text, a.attname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.confrelid = %s::regclass
            AND c.confdeltype IN ('r', 'a') AND cardinality(c.conkey) = 1
        """,
        (table,),
    )
    return cr.fetchall()


def keep_used_records(env):
    """Archive and stop updating the dropped payroll records payslips still use.

    A salary rule a 17.0 payslip line refers to, a category such a line or a
    remaining rule uses, an input type a payslip input uses: the end of the
    update cannot delete them (foreign keys), logs the refused DELETE as an
    error and leaves them active and updatable, so a rule 18.0 dropped keeps
    running on the new payslips of its 17.0 structure. They are archived where
    the model can be and their xmlids no longer updated; the unused ones are
    deleted as before. Must run after every module's data is loaded and before
    that cleanup, i.e. in an end-migration. A second run changes nothing.
    """
    cr = env.cr
    dropped = _dropped(env)
    tables = {env[model]._table: model for model in MODELS}
    references = {
        model: _restricting_columns(cr, env[model]._table) for model in MODELS
    }
    kept = {model: set() for model in MODELS}
    changed = True
    while changed:
        changed = False
        for model in MODELS:
            pending = set(dropped[model]) - kept[model]
            for ref_table, column in references[model]:
                if not pending:
                    break
                ref_model = tables.get(ref_table)
                deleted = (
                    set(dropped[ref_model]) - kept[ref_model] if ref_model else set()
                )
                cr.execute(
                    sql.SQL(
                        "SELECT DISTINCT {column} FROM {table}"
                        " WHERE {column} = ANY(%s) AND NOT (id = ANY(%s))"
                    ).format(
                        column=sql.Identifier(column),
                        table=sql.Identifier(ref_table),
                    ),
                    (list(pending), list(deleted) or [0]),
                )
                used = {res_id for (res_id,) in cr.fetchall()}
                if used:
                    kept[model] |= used
                    pending -= used
                    changed = True
    for model, ids in kept.items():
        if not ids:
            continue
        records = env[model].browse(sorted(ids))
        imd_ids = tuple(dropped[model][res_id] for res_id in ids)
        cr.execute(
            "UPDATE ir_model_data SET noupdate = true WHERE id IN %s", (imd_ids,)
        )
        if "active" in records._fields:
            cr.execute(
                sql.SQL("UPDATE {} SET active = false WHERE id IN %s").format(
                    sql.Identifier(records._table)
                ),
                (tuple(ids),),
            )
            records.invalidate_recordset(["active"])
        _logger.info(
            "%s %s records 18.0 no longer ships kept for the payslips that use them"
            "%s: %s",
            len(ids),
            model,
            ", archived" if "active" in records._fields else "",
            ", ".join(str(res_id) for res_id in sorted(ids)),
        )
