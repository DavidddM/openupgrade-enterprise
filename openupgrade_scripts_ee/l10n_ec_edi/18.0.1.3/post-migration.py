# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_ec_certificates(env):
    """Migrate l10n_ec_edi.certificate records to certificate.certificate.

    In 17.0: l10n_ec_edi defined its own model l10n_ec_edi.certificate
    (table: l10n_ec_edi_certificate) with PKCS12 content and password.
    The binary content is stored via ir_attachment (Binary field with
    attachment=True).

    In 18.0: l10n_ec_edi extends the unified certificate.certificate model.
    """
    if not openupgrade.table_exists(env.cr, "l10n_ec_edi_certificate"):
        return
    env.cr.execute("SELECT COUNT(*) FROM l10n_ec_edi_certificate")
    if not env.cr.fetchone()[0]:
        return
    # Read old certificate metadata + binary content from ir_attachment
    env.cr.execute(
        """
        SELECT
            old.id,
            COALESCE(old.file_name, 'EC Certificate'),
            old.password,
            old.company_id,
            att.db_datas,
            old.create_uid, old.create_date, old.write_uid, old.write_date
        FROM l10n_ec_edi_certificate old
        LEFT JOIN ir_attachment att
            ON att.res_model = 'l10n_ec_edi.certificate'
            AND att.res_id = old.id
            AND att.res_field = 'content'
        """
    )
    for row in env.cr.fetchall():
        (old_id, cert_name, password, company_id,
         content, cr_uid, cr_date, wr_uid, wr_date) = row
        env.cr.execute(
            """
            INSERT INTO certificate_certificate (
                name, pkcs12_password, company_id,
                scope, active,
                create_uid, create_date, write_uid, write_date
            ) VALUES (
                %(name)s, %(password)s, %(company_id)s,
                'general', true,
                %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
            )
            RETURNING id
            """,
            {
                "name": cert_name,
                "password": password,
                "company_id": company_id,
                "cr_uid": cr_uid,
                "cr_date": cr_date,
                "wr_uid": wr_uid,
                "wr_date": wr_date,
            },
        )
        new_cert_id = env.cr.fetchone()[0]
        if content:
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
                    %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
                )
                """,
                {
                    "res_id": new_cert_id,
                    "content": content,
                    "company_id": company_id,
                    "cr_uid": cr_uid,
                    "cr_date": cr_date,
                    "wr_uid": wr_uid,
                    "wr_date": wr_date,
                },
            )
        # Update company reference if column exists
        if openupgrade.column_exists(
            env.cr, "res_company", "l10n_ec_edi_certificate_id"
        ):
            env.cr.execute(
                """
                UPDATE res_company
                SET l10n_ec_edi_certificate_id = %s
                WHERE id = %s
                AND l10n_ec_edi_certificate_id IS NULL
                """,
                (new_cert_id, company_id),
            )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_ec_certificates(env)
