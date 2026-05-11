# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import certificate


def _migrate_ar_certificates(env):
    """Migrate the AFIP certificate and key of each company.

    17.0 keeps them in the Binary fields ``l10n_ar_afip_ws_crt`` (PEM
    certificate) and ``l10n_ar_afip_ws_key`` (unencrypted PEM key) of
    res.company, which are attachments (filestore or database), not columns.
    A company may hold only the key (certificate request not answered yet), so
    the key gets its own link; the certificate gets the key as private key
    when they match.
    """
    certificate.migrate(
        env,
        "res.company",
        """
        SELECT id, id AS company_id,
            NULLIF(l10n_ar_afip_ws_crt_fname, '') AS name,
            'AFIP private key ' || name AS key_name
        FROM res_company
        WHERE id IN (
            SELECT res_id FROM ir_attachment
            WHERE res_model = 'res.company'
                AND res_field IN ('l10n_ar_afip_ws_crt', 'l10n_ar_afip_ws_key')
        )
        ORDER BY id
        """,
        "l10n_ar_afip_ws_crt",
        key="l10n_ar_afip_ws_key",
    )
    certificate.link_companies(env, "l10n_ar_afip_ws_crt_id", "l10n_ar_afip_ws_crt")
    certificate.link_companies(env, "l10n_ar_afip_ws_key_id", "l10n_ar_afip_ws_key")


@openupgrade.migrate()
def migrate(env, version):
    _migrate_ar_certificates(env)
