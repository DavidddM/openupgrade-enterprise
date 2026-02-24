# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_cl_certificates(env):
    """Migrate l10n_cl.certificate records to certificate.certificate.

    In 17.0: l10n_cl_edi defined its own model l10n_cl.certificate
    (table: l10n_cl_certificate) with PKCS12 content and passphrase.

    In 18.0: l10n_cl_edi extends the unified certificate.certificate model
    with Chile-specific fields (user_id, last_token, token_time, etc.).

    The old table is preserved by OpenUpgrade. We copy data to the new
    table, including the l10n_cl extension fields (user_id, last_token,
    token_time, subject_serial_number). Content is a Binary field stored
    as ir_attachment in 18.0, so we insert the record first, then create
    an ir_attachment.
    """
    if not openupgrade.table_exists(env.cr, "l10n_cl_certificate"):
        return
    env.cr.execute("SELECT COUNT(*) FROM l10n_cl_certificate")
    if not env.cr.fetchone()[0]:
        return
    env.cr.execute(
        """
        SELECT
            COALESCE(old.signature_filename, 'CL Certificate'),
            old.certificate,
            old.signature_pass_phrase,
            old.company_id,
            old.user_id,
            old.last_token,
            old.token_time,
            old.subject_serial_number,
            true,
            old.create_uid, old.create_date, old.write_uid, old.write_date
        FROM l10n_cl_certificate old
        WHERE old.certificate IS NOT NULL
        """
    )
    for row in env.cr.fetchall():
        (cert_name, content, passphrase, company_id,
         user_id, last_token, token_time, subject_serial_number,
         active, cr_uid, cr_date, wr_uid, wr_date) = row
        env.cr.execute(
            """
            INSERT INTO certificate_certificate (
                name, pkcs12_password, company_id,
                user_id, last_token, token_time, subject_serial_number,
                scope, active,
                create_uid, create_date, write_uid, write_date
            ) VALUES (
                %(name)s, %(passphrase)s, %(company_id)s,
                %(user_id)s, %(last_token)s, %(token_time)s,
                %(subject_serial_number)s,
                'general', %(active)s,
                %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
            )
            RETURNING id
            """,
            {
                "name": cert_name,
                "passphrase": passphrase,
                "company_id": company_id,
                "user_id": user_id,
                "last_token": last_token,
                "token_time": token_time,
                "subject_serial_number": subject_serial_number,
                "active": active,
                "cr_uid": cr_uid,
                "cr_date": cr_date,
                "wr_uid": wr_uid,
                "wr_date": wr_date,
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


@openupgrade.migrate()
def migrate(env, version):
    _migrate_cl_certificates(env)
