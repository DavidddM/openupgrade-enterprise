# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_column_renames = {
    "hr_contract": [
        ("fiscal_voluntary_rate", None),
        ("fiscal_voluntarism", None),
    ],
    "res_company": [
        # onss_pem_passphrase is the only Char field (Binary fields
        # are stored as ir.attachment, no DB column)
        ("onss_pem_passphrase", None),
    ],
}


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_columns(env.cr, _column_renames)
