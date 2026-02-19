# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_nl_sbr_certificates(env):
    """Migrate NL SBR certificate/key from Binary fields to certificate records.

    In 17.0: res.company had Binary fields:
    - l10n_nl_reports_sbr_cert (certificate, DER/PEM/PKCS12)
    - l10n_nl_reports_sbr_key (private key)
    - l10n_nl_reports_sbr_server_root_cert (root CA certificate)

    In 18.0: res.company has Many2one fields:
    - l10n_nl_reports_sbr_cert_id (→ certificate.certificate)
    - l10n_nl_reports_sbr_server_root_cert_id (→ certificate.certificate)

    OpenUpgrade preserves the old Binary columns.
    """
    if not openupgrade.column_exists(
        env.cr, "res_company", "l10n_nl_reports_sbr_cert"
    ):
        return
    env.cr.execute(
        """
        SELECT id, l10n_nl_reports_sbr_cert, l10n_nl_reports_sbr_key,
               l10n_nl_reports_sbr_cert_filename, l10n_nl_reports_sbr_key_filename,
               l10n_nl_reports_sbr_server_root_cert
        FROM res_company
        WHERE l10n_nl_reports_sbr_cert IS NOT NULL
           OR l10n_nl_reports_sbr_server_root_cert IS NOT NULL
        """
    )
    for row in env.cr.fetchall():
        (company_id, cert_binary, key_binary,
         cert_fname, key_fname, root_cert_binary) = row
        new_key_id = None
        # Create certificate.key from private key
        if key_binary:
            env.cr.execute(
                """
                INSERT INTO certificate_key (
                    name, company_id, active,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    COALESCE(%(name)s, 'NL SBR Private Key'),
                    %(company_id)s, true,
                    1, NOW(), 1, NOW()
                )
                RETURNING id
                """,
                {
                    "name": key_fname,
                    "company_id": company_id,
                },
            )
            new_key_id = env.cr.fetchone()[0]
            env.cr.execute(
                """
                INSERT INTO ir_attachment (
                    name, res_model, res_id, res_field, type, db_datas,
                    checksum, company_id,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    'content', 'certificate.key', %(res_id)s, 'content',
                    'binary', %(content)s,
                    md5(%(content)s), %(company_id)s,
                    1, NOW(), 1, NOW()
                )
                """,
                {
                    "res_id": new_key_id,
                    "content": key_binary,
                    "company_id": company_id,
                },
            )
        # Create certificate.certificate from PKI certificate
        if cert_binary:
            env.cr.execute(
                """
                INSERT INTO certificate_certificate (
                    name, private_key_id, company_id,
                    scope, active,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    COALESCE(%(name)s, 'NL SBR Certificate'),
                    %(key_id)s, %(company_id)s,
                    'general', true,
                    1, NOW(), 1, NOW()
                )
                RETURNING id
                """,
                {
                    "name": cert_fname,
                    "key_id": new_key_id,
                    "company_id": company_id,
                },
            )
            new_cert_id = env.cr.fetchone()[0]
            env.cr.execute(
                """
                INSERT INTO ir_attachment (
                    name, res_model, res_id, res_field, type, db_datas,
                    checksum, company_id,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    'content', 'certificate.certificate', %(res_id)s,
                    'content', 'binary', %(content)s,
                    md5(%(content)s), %(company_id)s,
                    1, NOW(), 1, NOW()
                )
                """,
                {
                    "res_id": new_cert_id,
                    "content": cert_binary,
                    "company_id": company_id,
                },
            )
            env.cr.execute(
                """
                UPDATE res_company
                SET l10n_nl_reports_sbr_cert_id = %s
                WHERE id = %s
                """,
                (new_cert_id, company_id),
            )
        # Create certificate.certificate from root CA cert
        if root_cert_binary:
            env.cr.execute(
                """
                INSERT INTO certificate_certificate (
                    name, company_id,
                    scope, active,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    'NL SBR Root Certificate',
                    %(company_id)s,
                    'general', true,
                    1, NOW(), 1, NOW()
                )
                RETURNING id
                """,
                {"company_id": company_id},
            )
            new_root_id = env.cr.fetchone()[0]
            env.cr.execute(
                """
                INSERT INTO ir_attachment (
                    name, res_model, res_id, res_field, type, db_datas,
                    checksum, company_id,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    'content', 'certificate.certificate', %(res_id)s,
                    'content', 'binary', %(content)s,
                    md5(%(content)s), %(company_id)s,
                    1, NOW(), 1, NOW()
                )
                """,
                {
                    "res_id": new_root_id,
                    "content": root_cert_binary,
                    "company_id": company_id,
                },
            )
            env.cr.execute(
                """
                UPDATE res_company
                SET l10n_nl_reports_sbr_server_root_cert_id = %s
                WHERE id = %s
                """,
                (new_root_id, company_id),
            )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_nl_sbr_certificates(env)
