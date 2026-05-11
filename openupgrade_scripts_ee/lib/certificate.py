# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Shared migration of the 17.0 localization certificates to 18.0.

17.0 kept certificates in per-module models or in Binary fields of res.company;
18.0 uses certificate.certificate and certificate.key of the certificate module.
The module scripts say where their 17.0 data lives and call ``migrate``: the
records are created through the ORM, so every stored compute of the certificate
module runs, and the 17.0 -> 18.0 mapping is kept in a legacy table, so a second
run creates nothing and ``relink`` / ``link_companies`` can rewrite the links.
"""

import base64
import binascii
import logging
import re

import psycopg2
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from openupgradelib import openupgrade
from psycopg2 import sql

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAP_TABLE = openupgrade.get_legacy_name("certificate_map")
CERTIFICATE = "certificate.certificate"
KEY = "certificate.key"
_FAILURES = (UserError, ValueError, TypeError, psycopg2.Error)
_PEM_PRIVATE_KEY = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----.+?-----END [A-Z ]*PRIVATE KEY-----", re.S
)


def _ensure_map_table(cr):
    """Create the legacy table that maps a 17.0 binary field to its 18.0 record."""
    cr.execute(
        sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {} (
                source_model varchar NOT NULL,
                source_field varchar NOT NULL,
                source_id integer NOT NULL,
                target_model varchar NOT NULL,
                target_id integer NOT NULL,
                PRIMARY KEY (source_model, source_field, source_id)
            )
            """
        ).format(sql.Identifier(MAP_TABLE))
    )


def _mapped(env, target_model, source):
    """Return the 18.0 record already created for ``source``, if it still exists."""
    env.cr.execute(
        sql.SQL(
            "SELECT target_id FROM {} WHERE source_model = %s AND source_field = %s"
            " AND source_id = %s AND target_model = %s"
        ).format(sql.Identifier(MAP_TABLE)),
        (*source, target_model),
    )
    row = env.cr.fetchone()
    return env[target_model].browse(row[0]).exists() if row else env[target_model]


def _column_bytes(value):
    """Raw bytes of a Binary column (``attachment=False`` stores the base64 text)."""
    if not value:
        return None
    data = bytes(value)
    try:
        return base64.b64decode(b"".join(data.split()), validate=True) or None
    except binascii.Error:
        return data


def _source_bytes(env, model, field, row):
    """Raw bytes of a 17.0 Binary field, from its column or its attachment.

    The attachment is read through the ORM, so the bytes come from the
    filestore (``store_fname``) or from ``db_datas``, whichever 17.0 used.
    """
    if not field:
        return None
    if field in row:
        return _column_bytes(row[field])
    attachment = env["ir.attachment"].search(
        [
            ("res_model", "=", model),
            ("res_field", "=", field),
            ("res_id", "=", row["id"]),
        ],
        limit=1,
    )
    return attachment.raw or None


def _public_key(content):
    """Public key of a DER or PEM certificate, None for anything else."""
    for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
        try:
            return loader(content).public_key()
        except ValueError:
            continue
    return None


def _private_key(content, password):
    """Load a DER or PEM private key, None when it does not load with password."""
    for loader in (
        serialization.load_der_private_key,
        serialization.load_pem_private_key,
    ):
        try:
            return loader(content, password.encode() if password else None)
        except (ValueError, TypeError, UnsupportedAlgorithm):
            continue
    return None


def _spki(public_key):
    """DER SubjectPublicKeyInfo of a public key, to compare two keys."""
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _pick_key(certificate, key, password):
    """Return ``(content, password, matches)`` for the certificate.key to create.

    Candidates are the key file, then a private key embedded in a PEM
    certificate file, each with and without the stored password, because
    certificate.key fails to load an unencrypted key given a password. The
    first one that loads and fits the certificate wins; without any, the key
    file is kept as is so the user can fix its password in 18.0.
    """
    public = _public_key(certificate) if certificate else None
    embedded = _PEM_PRIVATE_KEY.search(certificate or b"")
    candidates = [key, embedded and embedded.group(0)]
    for content in filter(None, candidates):
        for secret in dict.fromkeys((password or None, None)):
            private = _private_key(content, secret)
            if private is None:
                continue
            if public is not None and _spki(private.public_key()) != _spki(public):
                continue
            return content, secret, public is not None
    return key, password or None, False


def _fits(certificate, private_key):
    """Whether an existing certificate.key belongs to the certificate bytes."""
    public = _public_key(certificate)
    pem = private_key.with_context(bin_size=False).pem_key
    loaded = _private_key(base64.b64decode(pem), None) if pem else None
    return bool(public and loaded and _spki(loaded.public_key()) == _spki(public))


def _create(env, target_model, source, vals, label):
    """Create the 18.0 record of one 17.0 source and record the mapping.

    Each record gets its own savepoint: a failure rolls back that record only
    and is logged as a WARNING naming the 17.0 source, so one broken
    certificate does not stop the upgrade. Returns an empty record then.
    """
    try:
        with env.cr.savepoint():
            record = env[target_model].create(vals)
            env.cr.execute(
                sql.SQL(
                    "INSERT INTO {} (source_model, source_field, source_id,"
                    " target_model, target_id) VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT (source_model, source_field, source_id)"
                    " DO UPDATE SET target_model = EXCLUDED.target_model,"
                    " target_id = EXCLUDED.target_id"
                ).format(sql.Identifier(MAP_TABLE)),
                (*source, target_model, record.id),
            )
    except _FAILURES as error:
        _logger.warning(
            "%s %s, field %s (%s): %s not created, set it up by hand in 18.0: %s",
            source[0],
            source[2],
            source[1],
            label,
            target_model,
            error,
        )
        return env[target_model]
    _logger.info(
        "%s %s, field %s (%s): created %s %s",
        source[0],
        source[2],
        source[1],
        label,
        target_model,
        record.id,
    )
    return record


def migrate(env, model, query, content, key=None, values=()):
    """Create the 18.0 certificate (and private key) of every row of ``query``.

    ``query`` returns one row per 17.0 record of ``model`` with the columns
    ``id`` and ``company_id`` and optionally ``name``, ``active``,
    ``pkcs12_password``, ``key_name`` and ``key_password``. ``content`` and
    ``key`` are the 17.0 Binary fields of the certificate and of its separate
    private key; when the query returns a column with that name the bytes are
    read from it (``attachment=False``), otherwise from the field's attachment.
    The query columns named in ``values`` are copied onto the certificate.
    PKCS#12 certificates need no ``key``: certificate.certificate extracts it.
    """
    _ensure_map_table(env.cr)
    env.cr.execute(query)
    rows = env.cr.dictfetchall()
    results = []
    for row in rows:
        results += _migrate_row(env, model, row, content, key, values)
    _logger.info(
        "%s: %s 17.0 rows, %s 18.0 records created, %s already migrated, %s failed",
        model,
        len(rows),
        sum(1 for record, new in results if record and new),
        sum(1 for record, new in results if record and not new),
        sum(1 for record, _new in results if not record),
    )


def _migrate_row(env, model, row, content, key, values):
    """Create the missing key and certificate of one 17.0 row.

    The mapping is read before the 17.0 bytes: Odoo deletes the attachments
    of the removed 17.0 models at the end of the upgrade, so a later run must
    not depend on them. Returns ``(record, created)`` pairs; an empty record
    means the creation failed and was logged.
    """
    label = "company %s" % row["company_id"]
    name = row.get("name") or "%s %s" % (model, row["id"])
    certificate_source = (model, content, row["id"])
    key_source = (model, key, row["id"])
    record = _mapped(env, CERTIFICATE, certificate_source)
    private_key = _mapped(env, KEY, key_source) if key else env[KEY]
    results = [(found, False) for found in (private_key, record) if found]
    certificate = None if record else _source_bytes(env, model, content, row)
    key_bytes = None if private_key else _source_bytes(env, model, key, row)
    if not (results or certificate or key_bytes):
        _logger.warning(
            "%s %s, field %s (%s): no content in 17.0, nothing to migrate",
            model,
            row["id"],
            content,
            label,
        )
        return results
    matches = bool(certificate and private_key and _fits(certificate, private_key))
    if key_bytes:
        key_content, key_password, matches = _pick_key(
            certificate, key_bytes, row.get("key_password")
        )
        key_vals = {
            "name": row.get("key_name") or "%s.key" % name,
            "content": base64.b64encode(key_content),
            "password": key_password or False,
            "company_id": row["company_id"],
        }
        private_key = _create(env, KEY, key_source, key_vals, label)
        results.append((private_key, True))
    if not certificate:
        return results
    vals = {
        "name": name,
        "content": base64.b64encode(certificate),
        "pkcs12_password": row.get("pkcs12_password") or False,
        "active": row.get("active", True) is not False,
        "company_id": row["company_id"],
    }
    vals.update({field: row[field] for field in values})
    if private_key and matches:
        vals["private_key_id"] = private_key.id
    record = _create(env, CERTIFICATE, certificate_source, vals, label)
    results.append((record, True))
    if record and private_key and not matches:
        _logger.warning(
            "%s %s, field %s (%s): private key %s does not load or does not match"
            " the certificate, left unlinked",
            model,
            row["id"],
            key,
            label,
            private_key.id,
        )
    return results


def _relink(env, table, column, model, field, source_column):
    """Set ``table.column`` to the 18.0 record mapped from ``source_column``."""
    query = sql.SQL(
        """
        UPDATE {table} t
        SET {column} = m.target_id
        FROM {map} m
        WHERE m.source_model = %s AND m.source_field = %s
            AND m.source_id = t.{source}
            AND t.{column} IS DISTINCT FROM m.target_id
        """
    ).format(
        table=sql.Identifier(table),
        column=sql.Identifier(column),
        map=sql.Identifier(MAP_TABLE),
        source=sql.Identifier(source_column),
    )
    openupgrade.logged_query(env.cr, query, (model, field))
    env.invalidate_all()


def relink(env, table, column, model, field):
    """Remap a many2one detached in pre-migration to the migrated certificates.

    Rows whose 17.0 certificate could not be migrated keep an empty link and
    are listed in a WARNING.
    """
    legacy = openupgrade.get_legacy_name(column)
    if not openupgrade.column_exists(env.cr, table, legacy):
        return
    _ensure_map_table(env.cr)
    _relink(env, table, column, model, field, legacy)
    env.cr.execute(
        sql.SQL(
            """
            SELECT array_agg(t.id ORDER BY t.id)
            FROM {table} t
            WHERE t.{legacy} IS NOT NULL AND t.{column} IS NULL
            """
        ).format(
            table=sql.Identifier(table),
            legacy=sql.Identifier(legacy),
            column=sql.Identifier(column),
        )
    )
    missing = env.cr.fetchone()[0]
    if missing:
        _logger.warning(
            "%s.%s: no migrated certificate for the 17.0 value of rows %s",
            table,
            column,
            missing,
        )


def link_companies(env, column, field):
    """Point ``res_company.column`` at the record migrated from its ``field``."""
    _ensure_map_table(env.cr)
    _relink(env, "res_company", column, "res.company", field, "id")
