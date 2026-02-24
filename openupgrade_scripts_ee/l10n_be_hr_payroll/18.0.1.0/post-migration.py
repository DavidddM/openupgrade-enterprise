# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _move_fiscal_voluntary_rate(env):
    """Move fiscal_voluntary_rate from hr.contract to hr.employee.

    Uses the latest open contract (or most recent contract) per employee.
    """
    legacy_rate = openupgrade.get_legacy_name("fiscal_voluntary_rate")
    openupgrade.logged_query(
        env.cr,
        f"""
        UPDATE hr_employee e
        SET fiscal_voluntary_rate = sub.rate
        FROM (
            SELECT DISTINCT ON (c.employee_id)
                c.employee_id,
                c.{legacy_rate} AS rate
            FROM hr_contract c
            WHERE c.{legacy_rate} IS NOT NULL
            AND c.{legacy_rate} > 0
            ORDER BY c.employee_id,
                CASE WHEN c.state = 'open' THEN 0 ELSE 1 END,
                c.date_start DESC NULLS LAST
        ) sub
        WHERE e.id = sub.employee_id
        """,
    )


def _migrate_onss_certificates(env):
    """Create certificate.certificate records from legacy ONSS Binary attachments.

    In v17, ONSS certificates were Binary fields stored as ir_attachment.
    In v18, they are certificate.certificate records linked via M2O.

    Checks that the certificate model is available, finds existing ONSS
    certificate attachments via ORM, and creates certificate.certificate
    records with optional passphrase from the legacy column.
    """
    if "certificate.certificate" not in env:
        _logger.info(
            "certificate.certificate model not available, "
            "skipping ONSS certificate migration"
        )
        return
    if not openupgrade.column_exists(env.cr, "res_company", "onss_certificate_id"):
        return
    attachments = env["ir.attachment"].search(
        [
            ("res_model", "=", "res.company"),
            ("res_field", "=", "onss_pem_certificate"),
        ]
    )
    if not attachments:
        _logger.info("No ONSS certificate attachments found to migrate")
        return
    legacy_pass = openupgrade.get_legacy_name("onss_pem_passphrase")
    Certificate = env["certificate.certificate"]
    for att in attachments:
        company_id = att.res_id
        if not att.datas:
            continue
        vals = {
            "name": att.name or "ONSS Certificate (migrated)",
            "content": att.datas,
            "company_id": company_id,
        }
        # Get passphrase if column exists
        if openupgrade.column_exists(env.cr, "res_company", legacy_pass):
            env.cr.execute(
                f"SELECT {legacy_pass} FROM res_company WHERE id = %s",
                (company_id,),
            )
            row = env.cr.fetchone()
            if row and row[0]:
                vals["pkcs12_password"] = row[0]
        try:
            cert = Certificate.create(vals)
            env.cr.execute(
                "UPDATE res_company SET onss_certificate_id = %s WHERE id = %s",
                (cert.id, company_id),
            )
        except Exception:
            _logger.warning(
                "Could not create certificate for company %s, "
                "manual ONSS certificate setup required.",
                company_id,
                exc_info=True,
            )


@openupgrade.migrate()
def migrate(env, version):
    _move_fiscal_voluntary_rate(env)
    _migrate_onss_certificates(env)
