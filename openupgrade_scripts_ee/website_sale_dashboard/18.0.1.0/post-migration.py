# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _delete_obsolete_onboarding_records(env):
    """Delete orphaned onboarding records from removed data/onboarding_data.xml.

    The onboarding_data.xml file was removed in 18.0 and these noupdate records
    would remain as orphans.
    """
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "website_sale_dashboard.onboarding_onboarding_step_payment_provider",
            "website_sale_dashboard.onboarding_onboarding_website_sale_dashboard",
        ],
    )


@openupgrade.migrate()
def migrate(env, version):
    _delete_obsolete_onboarding_records(env)
