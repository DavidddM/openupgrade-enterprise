# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Module data that an update does not create although 18.0 modules rely on it."""

import io
import logging
import re

from lxml import etree

from odoo.tools import convert, file_open

_logger = logging.getLogger(__name__)

_REF = re.compile(r"""\bref\(\s*['"]([\w.]+)['"]\s*\)""")


def _full_xmlid(module, xmlid):
    return xmlid if "." in xmlid else "%s.%s" % (module, xmlid)


def _exists(cr, xmlid):
    module, name = xmlid.split(".", 1)
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s", (module, name)
    )
    return bool(cr.fetchone())


def _references(module, record):
    refs = set()
    for field in record.iter("field"):
        if field.get("ref"):
            refs.add(_full_xmlid(module, field.get("ref")))
        for expression in (field.get("eval") or "", field.text or ""):
            refs.update(_full_xmlid(module, ref) for ref in _REF.findall(expression))
    return refs


def load_missing_records(env, module, filename):
    """Create the records of an 18.0 data file that this database lacks.

    ``forcecreate="0"`` records of a ``noupdate`` block are only created when
    a module is installed; an update from 17.0 skips the ones that are new in
    18.0, and a module installed during the same update that refers to them
    aborts the load. Every missing record of ``module/filename`` whose
    references resolve (in the database or among the records loaded with it)
    is created in init mode, existing records are not touched, functions are
    not called. Returns the xmlids created; a second run creates none.
    """
    with file_open("%s/%s" % (module, filename), "rb") as source:
        tree = etree.parse(source)
    known = set()
    selected = []
    skipped = []
    for record in tree.iter("record"):
        xmlid = _full_xmlid(module, record.get("id"))
        if _exists(env.cr, xmlid):
            continue
        missing = sorted(
            ref
            for ref in _references(module, record)
            if ref not in known and not _exists(env.cr, ref)
        )
        if missing:
            skipped.append("%s (needs %s)" % (xmlid, ", ".join(missing)))
            continue
        known.add(xmlid)
        selected.append(record)
    if skipped:
        _logger.info(
            "%s/%s: records not created, their references are missing: %s",
            module,
            filename,
            "; ".join(skipped),
        )
    if not selected:
        return []
    root = etree.Element("odoo")
    data = etree.SubElement(root, "data", noupdate="1")
    for record in selected:
        data.append(record)
    content = io.BytesIO(etree.tostring(root))
    content.name = "%s/%s" % (module, filename)
    convert.convert_xml_import(env, module, content, {}, mode="init", noupdate=True)
    created = sorted(known)
    _logger.info("%s/%s: created %s", module, filename, ", ".join(created))
    return created
