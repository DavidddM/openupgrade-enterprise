# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import certificate


def _migrate_ec_certificates(env):
    """Migrate l10n_ec_edi.certificate to certificate.certificate.

    17.0 stores the PKCS#12 file in the ``content`` attachment (filestore or
    database) and its password in ``password``; 18.0 extracts the private key
    itself. The companies' certificate link, detached in pre-migration, is
    then remapped to the new certificates.
    """
    if not openupgrade.table_exists(env.cr, "l10n_ec_edi_certificate"):
        return
    certificate.migrate(
        env,
        "l10n_ec_edi.certificate",
        """
        SELECT id, company_id, file_name AS name, active,
            password AS pkcs12_password
        FROM l10n_ec_edi_certificate
        ORDER BY id
        """,
        "content",
    )
    certificate.relink(
        env,
        "res_company",
        "l10n_ec_edi_certificate_id",
        "l10n_ec_edi.certificate",
        "content",
    )


@openupgrade.migrate()
def migrate(env, version):
    _migrate_ec_certificates(env)
