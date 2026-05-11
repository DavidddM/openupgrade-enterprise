# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Code shared by the migration scripts of this repository.

Not a module directory: Odoo appends every ``upgrade_path`` entry to
``odoo.upgrade.__path__``, so the scripts import it as ``odoo.upgrade.lib``
whenever they themselves can run.
"""
