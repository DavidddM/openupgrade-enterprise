# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_ar_certificates(env):
    """Migrate AR AFIP certificate/key from Binary fields to certificate records.

    In 17.0: res.company had Binary fields:
    - l10n_ar_afip_ws_key (PEM private key)
    - l10n_ar_afip_ws_crt (PEM certificate)

    In 18.0: res.company has Many2one fields:
    - l10n_ar_afip_ws_key_id (→ certificate.key)
    - l10n_ar_afip_ws_crt_id (→ certificate.certificate)

    OpenUpgrade preserves the old Binary columns. We create certificate/key
    records and set the new M2O fields.

    For each company with certificate data:
    1. Create a certificate.key record from the private key binary.
    2. Create a certificate.certificate record from the certificate binary.
    3. Set the M2O fields on res.company.
    """
    if not openupgrade.column_exists(
        env.cr, "res_company", "l10n_ar_afip_ws_crt"
    ):
        return
    env.cr.execute(
        """
        SELECT id, l10n_ar_afip_ws_key, l10n_ar_afip_ws_crt,
               l10n_ar_afip_ws_crt_fname
        FROM res_company
        WHERE l10n_ar_afip_ws_crt IS NOT NULL
        """
    )
    for company_id, key_binary, crt_binary, crt_fname in env.cr.fetchall():
        new_key_id = None
        if key_binary:
            env.cr.execute(
                """
                INSERT INTO certificate_key (
                    name, company_id, active,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    'AR AFIP Private Key', %(company_id)s, true,
                    1, NOW(), 1, NOW()
                )
                RETURNING id
                """,
                {"company_id": company_id},
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
            env.cr.execute(
                "UPDATE res_company SET l10n_ar_afip_ws_key_id = %s WHERE id = %s",
                (new_key_id, company_id),
            )
        if crt_binary:
            env.cr.execute(
                """
                INSERT INTO certificate_certificate (
                    name, private_key_id, company_id,
                    scope, active,
                    create_uid, create_date, write_uid, write_date
                ) VALUES (
                    COALESCE(%(name)s, 'AR AFIP Certificate'),
                    %(key_id)s, %(company_id)s,
                    'general', true,
                    1, NOW(), 1, NOW()
                )
                RETURNING id
                """,
                {
                    "name": crt_fname,
                    "key_id": new_key_id,
                    "company_id": company_id,
                },
            )
            new_crt_id = env.cr.fetchone()[0]
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
                    "res_id": new_crt_id,
                    "content": crt_binary,
                    "company_id": company_id,
                },
            )
            env.cr.execute(
                "UPDATE res_company SET l10n_ar_afip_ws_crt_id = %s WHERE id = %s",
                (new_crt_id, company_id),
            )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_ar_certificates(env)
