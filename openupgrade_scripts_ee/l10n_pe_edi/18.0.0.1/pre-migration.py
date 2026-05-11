# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.upgrade.lib import schema


@openupgrade.migrate()
def migrate(env, version):
    """Move the 17.0 certificate ids of the companies out of the module load.

    res.company.l10n_pe_edi_certificate_id points at l10n_pe_edi.certificate in
    17.0 and at certificate.certificate in 18.0; the module load recomputes the
    new column (no certificate yet), and the post-migration restores each
    company's 17.0 choice from the legacy column once the certificates exist.
    """
    schema.detach_column(env.cr, "res_company", "l10n_pe_edi_certificate_id")
