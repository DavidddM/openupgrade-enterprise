# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import certificate


def _migrate_mx_certificates(env):
    """Migrate l10n_mx_edi.certificate to certificate.certificate and .key.

    17.0 stores the DER certificate (``content``) and the encrypted PKCS#8 DER
    key (``key``) as base64 text in bytea columns (``attachment=False``); the
    key password is ``password``. The invoices' certificate link, detached in
    pre-migration, is then remapped to the new certificates.
    """
    if not openupgrade.table_exists(env.cr, "l10n_mx_edi_certificate"):
        return
    certificate.migrate(
        env,
        "l10n_mx_edi.certificate",
        """
        SELECT id, company_id, serial_number AS name, content, key,
            password AS key_password
        FROM l10n_mx_edi_certificate
        ORDER BY id
        """,
        "content",
        key="key",
    )
    certificate.relink(
        env,
        "account_move",
        "l10n_mx_edi_certificate_id",
        "l10n_mx_edi.certificate",
        "content",
    )


def _migrate_mx_addenda(env):
    """Migrate addenda from ir.ui.view to l10n_mx_edi.addenda.

    In 17.0: Addendas were stored as ir.ui.view records with
    l10n_mx_edi_addenda_flag=True. Partners referenced them via
    res_partner.l10n_mx_edi_addenda (M2O to ir.ui.view).

    In 18.0: New model l10n_mx_edi.addenda with name and arch fields.
    Partners reference via res_partner.l10n_mx_edi_addenda_id (M2O to
    l10n_mx_edi.addenda).

    Steps:
    1. Check if any addenda views exist (l10n_mx_edi_addenda_flag=True).
    2. Create l10n_mx_edi.addenda records from ir.ui.view records.
       The name and arch_db columns might be JSONB or VARCHAR depending on
       the upgrade state.
    3. Update res_partner references from old view FK (l10n_mx_edi_addenda)
       to new addenda FK (l10n_mx_edi_addenda_id).
    """
    if not openupgrade.column_exists(env.cr, "ir_ui_view", "l10n_mx_edi_addenda_flag"):
        return
    env.cr.execute(
        """
        SELECT COUNT(*) FROM ir_ui_view
        WHERE l10n_mx_edi_addenda_flag = true
        """
    )
    if not env.cr.fetchone()[0]:
        return
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
    env.cr.execute(
        f"""
        SELECT v.id, {name_expr}, v.arch_db
        FROM ir_ui_view v
        WHERE v.l10n_mx_edi_addenda_flag = true
        """
    )
    view_to_addenda = {}
    for view_id, name, arch in env.cr.fetchall():
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
    if not openupgrade.column_exists(env.cr, "res_partner", "l10n_mx_edi_addenda"):
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
