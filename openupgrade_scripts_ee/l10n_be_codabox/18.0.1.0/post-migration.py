# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # l10n_be_codabox_is_connected changed from a plain Boolean to a
    # computed+stored field. The compute method calls an external CodaBox API
    # endpoint, which would cause timeouts/errors during migration.
    # Ensure data consistency to prevent the ORM from triggering a recompute:
    # set is_connected = FALSE for companies with no IAP token.
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET l10n_be_codabox_is_connected = FALSE
        WHERE (l10n_be_codabox_iap_token IS NULL
               OR l10n_be_codabox_iap_token = '')
          AND l10n_be_codabox_is_connected IS DISTINCT FROM FALSE
        """,
    )
