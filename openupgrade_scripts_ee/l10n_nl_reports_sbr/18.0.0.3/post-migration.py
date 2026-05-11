# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import certificate


def _migrate_nl_sbr_certificates(env):
    """Migrate the Digipoort certificate, its key and the SBR root certificate.

    17.0 keeps them in Binary fields of res.company, which are attachments
    (filestore or database), not columns: ``l10n_nl_reports_sbr_cert`` (PEM
    certificate), ``l10n_nl_reports_sbr_key`` (PEM key, encrypted with a
    password 17.0 never stored when the upload was a protected file) and
    ``l10n_nl_reports_sbr_server_root_cert`` (PEM). An encrypted key is kept
    as a certificate.key without password and left unlinked, with a WARNING,
    so the user only has to enter the password in 18.0.
    """
    certificate.migrate(
        env,
        "res.company",
        """
        SELECT id, id AS company_id,
            NULLIF(l10n_nl_reports_sbr_cert_filename, '') AS name,
            NULLIF(l10n_nl_reports_sbr_key_filename, '') AS key_name
        FROM res_company
        WHERE id IN (
            SELECT res_id FROM ir_attachment
            WHERE res_model = 'res.company'
                AND res_field IN ('l10n_nl_reports_sbr_cert', 'l10n_nl_reports_sbr_key')
        )
        ORDER BY id
        """,
        "l10n_nl_reports_sbr_cert",
        key="l10n_nl_reports_sbr_key",
    )
    certificate.migrate(
        env,
        "res.company",
        """
        SELECT id, id AS company_id, 'SBR Root Certificate' AS name
        FROM res_company
        WHERE id IN (
            SELECT res_id FROM ir_attachment
            WHERE res_model = 'res.company'
                AND res_field = 'l10n_nl_reports_sbr_server_root_cert'
        )
        ORDER BY id
        """,
        "l10n_nl_reports_sbr_server_root_cert",
    )
    certificate.link_companies(
        env, "l10n_nl_reports_sbr_cert_id", "l10n_nl_reports_sbr_cert"
    )
    certificate.link_companies(
        env,
        "l10n_nl_reports_sbr_server_root_cert_id",
        "l10n_nl_reports_sbr_server_root_cert",
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_nl_sbr_certificates(env)
