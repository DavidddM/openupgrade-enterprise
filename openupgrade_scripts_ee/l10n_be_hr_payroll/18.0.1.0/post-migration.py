# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.upgrade.lib import certificate


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
    """Migrate the ONSS certificate and key of each company.

    17.0 keeps the PEM certificate file in ``onss_pem_certificate`` and the
    key file in ``onss_key`` (attachments, filestore or database); 17.0 signs
    with the private key found in the certificate file, decrypted with
    ``onss_pem_passphrase`` (legacy column since pre-migration). The key file
    is used when it fits the certificate, the key embedded in the certificate
    file otherwise, so 18.0 finds a usable ``private_key_id``.
    """
    passphrase = openupgrade.get_legacy_name("onss_pem_passphrase")
    if not openupgrade.column_exists(env.cr, "res_company", passphrase):
        passphrase = None
    query = sql.SQL(
        """
        SELECT id, id AS company_id, 'ONSS certificate ' || name AS name,
            'ONSS private key ' || name AS key_name, {} AS key_password
        FROM res_company
        WHERE id IN (
            SELECT res_id FROM ir_attachment
            WHERE res_model = 'res.company'
                AND res_field IN ('onss_pem_certificate', 'onss_key')
        )
        ORDER BY id
        """
    ).format(sql.Identifier(passphrase) if passphrase else sql.SQL("NULL"))
    certificate.migrate(
        env, "res.company", query, "onss_pem_certificate", key="onss_key"
    )
    certificate.link_companies(env, "onss_certificate_id", "onss_pem_certificate")


@openupgrade.migrate()
def migrate(env, version):
    _move_fiscal_voluntary_rate(env)
    _migrate_onss_certificates(env)
