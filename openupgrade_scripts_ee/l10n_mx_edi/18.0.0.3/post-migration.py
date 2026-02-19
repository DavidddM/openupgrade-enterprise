# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _migrate_mx_certificates(env):
    """Migrate l10n_mx_edi.certificate records to certificate.certificate.

    In 17.0: l10n_mx_edi had its own model l10n_mx_edi.certificate with
    separate CER (content) and KEY (key) binary fields.

    In 18.0: The unified certificate.certificate model is used. The private
    key is stored in a separate certificate.key record linked via
    private_key_id.
    """
    if not openupgrade.table_exists(env.cr, "l10n_mx_edi_certificate"):
        return
    env.cr.execute("SELECT COUNT(*) FROM l10n_mx_edi_certificate")
    if not env.cr.fetchone()[0]:
        return
    # Step 1: Create certificate.key records from the old 'key' binary field.
    # Store mapping via a temporary column.
    openupgrade.logged_query(
        env.cr,
        """
        ALTER TABLE l10n_mx_edi_certificate
        ADD COLUMN IF NOT EXISTS ou_new_key_id INTEGER
        """,
    )
    env.cr.execute(
        """
        SELECT id, key, password, company_id, create_uid, create_date,
               write_uid, write_date
        FROM l10n_mx_edi_certificate
        WHERE key IS NOT NULL
        """
    )
    for row in env.cr.fetchall():
        old_id, key_content, password, company_id, cr_uid, cr_date, wr_uid, wr_date = row
        env.cr.execute(
            """
            INSERT INTO certificate_key (
                name, password, company_id, active,
                create_uid, create_date, write_uid, write_date
            ) VALUES (
                'MX Private Key', %(password)s,
                %(company_id)s, true,
                %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
            )
            RETURNING id
            """,
            {
                "password": password,
                "company_id": company_id,
                "cr_uid": cr_uid,
                "cr_date": cr_date,
                "wr_uid": wr_uid,
                "wr_date": wr_date,
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
                %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
            )
            """,
            {
                "res_id": new_key_id,
                "content": key_content,
                "company_id": company_id,
                "cr_uid": cr_uid,
                "cr_date": cr_date,
                "wr_uid": wr_uid,
                "wr_date": wr_date,
            },
        )
        env.cr.execute(
            "UPDATE l10n_mx_edi_certificate SET ou_new_key_id = %s WHERE id = %s",
            (new_key_id, old_id),
        )
    # Step 2: Create certificate.certificate records from old CER content.
    # MX certificates use DER/CER format (not PKCS12), so no pkcs12_password.
    # Note: content is a Binary field stored as ir_attachment in 18.0,
    # so we insert the record first, then create an ir_attachment.
    env.cr.execute(
        """
        SELECT
            COALESCE(old.serial_number, 'MX Certificate'),
            old.content,
            old.ou_new_key_id,
            old.company_id,
            old.create_uid, old.create_date, old.write_uid, old.write_date
        FROM l10n_mx_edi_certificate old
        WHERE old.content IS NOT NULL
        """
    )
    for row in env.cr.fetchall():
        (cert_name, content, key_id, company_id,
         cr_uid, cr_date, wr_uid, wr_date) = row
        env.cr.execute(
            """
            INSERT INTO certificate_certificate (
                name, private_key_id, company_id,
                scope, active,
                create_uid, create_date, write_uid, write_date
            ) VALUES (
                %(name)s, %(key_id)s, %(company_id)s,
                'general', true,
                %(cr_uid)s, %(cr_date)s, %(wr_uid)s, %(wr_date)s
            )
            RETURNING id
            """,
            {
                "name": cert_name,
                "key_id": key_id,
                "company_id": company_id,
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


def _migrate_mx_addenda(env):
    """Migrate addenda from ir.ui.view to l10n_mx_edi.addenda.

    In 17.0: Addendas were stored as ir.ui.view records with
    l10n_mx_edi_addenda_flag=True. Partners referenced them via
    res_partner.l10n_mx_edi_addenda (M2O to ir.ui.view).

    In 18.0: New model l10n_mx_edi.addenda with name and arch fields.
    Partners reference via res_partner.l10n_mx_edi_addenda_id (M2O to
    l10n_mx_edi.addenda).
    """
    if not openupgrade.column_exists(
        env.cr, "ir_ui_view", "l10n_mx_edi_addenda_flag"
    ):
        return
    # Check if any addenda views exist
    env.cr.execute(
        """
        SELECT COUNT(*) FROM ir_ui_view
        WHERE l10n_mx_edi_addenda_flag = true
        """
    )
    if not env.cr.fetchone()[0]:
        return
    # Create l10n_mx_edi.addenda records from ir.ui.view records.
    # The name column might be JSONB or VARCHAR depending on upgrade state.
    env.cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'ir_ui_view' AND column_name = 'name'
        """
    )
    is_jsonb = env.cr.fetchone()[0] in ("jsonb", "json")
    if is_jsonb:
        name_expr = "COALESCE(v.name->>'en_US', v.name->>0, 'Addenda')"
    else:
        name_expr = "COALESCE(v.name, 'Addenda')"
    # Insert addenda records and build mapping from old view ID to new ID
    env.cr.execute(
        f"""
        SELECT v.id, {name_expr}, v.arch_db
        FROM ir_ui_view v
        WHERE v.l10n_mx_edi_addenda_flag = true
        """
    )
    view_to_addenda = {}
    for view_id, name, arch in env.cr.fetchall():
        # arch_db might be JSONB too
        if isinstance(arch, dict):
            arch_text = arch.get("en_US", next(iter(arch.values()), ""))
        else:
            arch_text = arch or ""
        env.cr.execute(
            """
            INSERT INTO l10n_mx_edi_addenda (name, arch, create_uid, create_date,
                                              write_uid, write_date)
            VALUES (%s, %s, 1, NOW(), 1, NOW())
            RETURNING id
            """,
            (name, arch_text),
        )
        view_to_addenda[view_id] = env.cr.fetchone()[0]
    # Update res_partner references from old view FK to new addenda FK.
    # OpenUpgrade preserves the old column l10n_mx_edi_addenda (FK to ir_ui_view).
    if not openupgrade.column_exists(
        env.cr, "res_partner", "l10n_mx_edi_addenda"
    ):
        return
    for old_view_id, new_addenda_id in view_to_addenda.items():
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE res_partner
            SET l10n_mx_edi_addenda_id = %s
            WHERE l10n_mx_edi_addenda = %s
            """,
            (new_addenda_id, old_view_id),
        )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_mx_certificates(env)
    _migrate_mx_addenda(env)
