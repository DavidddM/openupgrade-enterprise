# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """Remove the 'Social' event pages of the removed Twitter wall module.

    17.0 website_event_twitter_wall adds the event menu type 'social' and
    drops its menus with it (``ondelete='cascade'``); 18.0 has neither the
    type nor the page. Merged into website_event, the module would leave a
    website menu to a missing page on every event that showcased a wall. The
    website menus go through the ORM, which removes their event menus.
    """
    env.cr.execute(
        "SELECT menu_id FROM website_event_menu"
        " WHERE menu_type = 'social' AND menu_id IS NOT NULL"
    )
    menus = env["website.menu"].browse([row[0] for row in env.cr.fetchall()])
    menus.exists().unlink()
    openupgrade.logged_query(
        env.cr, "DELETE FROM website_event_menu WHERE menu_type = 'social'"
    )
