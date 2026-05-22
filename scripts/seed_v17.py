# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Seed a 17.0 database with the data the 18.0 migration scripts transform.

Run by scripts/run_e2e_test.sh as SEED_PY through ``odoo-bin shell`` on 17.0,
after the batch modules are installed. Every block belongs to one 17.0 module
and runs only when that module is installed; it goes through the 17.0 ORM, so
the stored values, attachments and computed fields are those of a real
database, and it records the ids and the values 18.0 must show in the table
``oue18_seed`` (k, v), which scripts/verify_v18.sql reads after the upgrade.
``block.<name>`` holds the 18.0 name of the block's module. Each recorded value
is echoed as a ``SEEDED key=value`` line; the script commits once at the end
and skips a block that already ran. The function of each block says what it
seeds and why.
"""

import base64
import datetime
import hashlib
import json

import pytz

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo import Command, fields
from odoo.tools import convert_file

PASSWORD = "oue18-seed"
LOST_PASSWORD = "oue18-not-stored"
CL_RUT = "76086428-5"
HIGH_DOCUMENT_ID = 900001
PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGA"
    "WjR9awAAAABJRU5ErkJggg=="
)


def installed(env, name):
    """Return whether the module is installed on this database."""
    return bool(
        env["ir.module.module"].search_count(
            [("name", "=", name), ("state", "=", "installed")]
        )
    )


def record(env, key, value):
    """Store one expected value in oue18_seed and echo it."""
    env.cr.execute(
        "INSERT INTO oue18_seed (k, v) VALUES (%s, %s)"
        " ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v",
        (key, str(value)),
    )
    print("SEEDED %s=%s" % (key, value))


def done(env, block):
    """Return whether a block already ran on this database."""
    env.cr.execute("SELECT 1 FROM oue18_seed WHERE k = %s", ("block.%s" % block,))
    return bool(env.cr.fetchone())


def sha1(data):
    """Hex SHA-1, the checksum Odoo stores on an attachment."""
    return hashlib.sha1(data).hexdigest()


def make_certificate(country, common_name, serial_number=None):
    """Self-signed RSA 2048 certificate valid from yesterday for ten years."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    attributes = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OUE18 seed"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ]
    if serial_number:
        attributes.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, serial_number))
    subject = x509.Name(attributes)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return key, cert


def pem_key(key, password=None):
    """PKCS#8 PEM of a private key, encrypted when a password is given."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        (
            serialization.BestAvailableEncryption(password.encode())
            if password
            else serialization.NoEncryption()
        ),
    )


def pem_certificate(cert):
    """PEM of a certificate."""
    return cert.public_bytes(serialization.Encoding.PEM)


def pkcs12_content(key, cert, name):
    """PKCS#12 bundle of key and certificate, encrypted with PASSWORD."""
    return pkcs12.serialize_key_and_certificates(
        name.encode(),
        key,
        cert,
        None,
        serialization.BestAvailableEncryption(PASSWORD.encode()),
    )


def utc_text(value):
    """Datetime as 18.0 stores it: naive UTC, seconds."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def record_certificate(env, prefix, old_id, cert, content, key=None):
    """Record the 17.0 id and what 18.0 certificate.certificate should compute."""
    if old_id is not None:
        record(env, "%s.cert_old_id" % prefix, old_id)
    record(env, "%s.cert_serial" % prefix, cert.serial_number)
    record(
        env,
        "%s.cert_cn" % prefix,
        cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
    )
    record(
        env,
        "%s.cert_sha256" % prefix,
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
    )
    record(env, "%s.cert_not_before" % prefix, utc_text(cert.not_valid_before_utc))
    record(env, "%s.cert_not_after" % prefix, utc_text(cert.not_valid_after_utc))
    record(env, "%s.content_sha1" % prefix, sha1(content))
    record(env, "%s.pem_sha1" % prefix, sha1(pem_certificate(cert)))
    if key is not None:
        record(env, "%s.key_pem_sha1" % prefix, sha1(pem_key(key)))


def record_storage(env, prefix, model, field, res_id):
    """Record whether the field's attachment is in the filestore."""
    env.cr.execute(
        "SELECT store_fname IS NOT NULL, db_datas IS NULL FROM ir_attachment"
        " WHERE res_model = %s AND res_field = %s AND res_id = %s",
        (model, field, res_id),
    )
    storage = env.cr.fetchone()
    record(env, "%s.content_in_filestore" % prefix, bool(storage and all(storage)))


def link_users(env, company):
    """Give the superuser and admin access to the company."""
    for user in env.user | env.ref("base.user_admin"):
        user.company_ids = [Command.link(company.id)]


def make_company(env, name, country_code, chart=None):
    """Root company of the given country, with its chart of accounts if given."""
    company = env["res.company"].create(
        {"name": name, "country_id": env.ref("base.%s" % country_code).id}
    )
    link_users(env, company)
    if chart:
        env["account.chart.template"].try_loading(chart, company, install_demo=False)
    return company


def seed_mx(env):
    """Certificate, posted invoice pointing at it, a sent CFDI document, an addenda.

    18.0 replaces l10n_mx_edi.certificate by certificate.certificate and the
    foreign key of the invoices switches with it. 17.0 code never writes
    ``l10n_mx_edi_certificate_id`` itself, so the seed writes it as data
    carried from older versions holds it. The customer gets an addenda, a
    flagged QWeb view in 17.0 and an l10n_mx_edi.addenda record in 18.0.
    """
    company = make_company(env, "OUE18 MX", "mx", "mx")
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    key, cert = make_certificate("MX", "OUE18 MX CSD")
    der = cert.public_bytes(serialization.Encoding.DER)
    certificate = env["l10n_mx_edi.certificate"].create(
        {
            "content": base64.b64encode(der),
            "key": base64.b64encode(
                key.private_bytes(
                    serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8,
                    serialization.BestAvailableEncryption(PASSWORD.encode()),
                )
            ),
            "password": PASSWORD,
            "company_id": company.id,
        }
    )
    partner = env["res.partner"].create(
        {
            "name": "OUE18 MX customer",
            "country_id": env.ref("base.mx").id,
            "company_id": company.id,
        }
    )
    move = env["account.move"].create(
        {
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.today(),
            "l10n_mx_edi_certificate_id": certificate.id,
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "OUE18 service",
                        "quantity": 1.0,
                        "price_unit": 100.0,
                    }
                )
            ],
        }
    )
    move.action_post()
    addenda = env["ir.ui.view"].create(
        {
            "name": "OUE18 addenda",
            "type": "qweb",
            "arch": '<t t-name="l10n_mx_edi.oue18_addenda">'
            '<Addenda><oue18 order="1"/></Addenda></t>',
            "l10n_mx_edi_addenda_flag": True,
        }
    )
    partner.l10n_mx_edi_addenda = addenda
    document = env["l10n_mx_edi.document"].create(
        {
            "move_id": move.id,
            "invoice_ids": [Command.set(move.ids)],
            "state": "invoice_sent",
            "sat_state": "not_defined",
            "datetime": fields.Datetime.now(),
            "message": "OUE18: CFDI signed with the seeded certificate",
        }
    )
    env.flush_all()
    env.cr.execute(
        "SELECT l10n_mx_edi_certificate_id FROM account_move WHERE id = %s", (move.id,)
    )
    assert (
        env.cr.fetchone()[0] == certificate.id
    ), "account_move.l10n_mx_edi_certificate_id not stored"
    record(env, "mx.company_id", company.id)
    record_certificate(env, "mx", certificate.id, cert, der, key)
    record(env, "mx.cert_serial17", certificate.serial_number)
    record(env, "mx.move_id", move.id)
    record(env, "mx.move_name", move.name)
    record(env, "mx.move_state", move.state)
    record(env, "mx.document_id", document.id)
    record(env, "mx.cfdi_state", move.l10n_mx_edi_cfdi_state)
    record(env, "mx.partner_id", partner.id)
    record(env, "mx.addenda_view", addenda.id)


def seed_company_certificate(env, prefix, country_code, chart, model, field, extra):
    """Company with a PKCS#12 certificate of the given 17.0 model set on `field`."""
    company = make_company(env, "OUE18 %s" % prefix.upper(), country_code, chart)
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    key, cert = make_certificate(
        prefix.upper(), "OUE18 %s certificate" % prefix.upper()
    )
    content = pkcs12_content(key, cert, "oue18-%s" % prefix)
    vals = {
        "content": base64.b64encode(content),
        "password": PASSWORD,
        "company_id": company.id,
    }
    vals.update(extra)
    certificate = env[model].create(vals)
    company[field] = certificate
    env.flush_all()
    env.cr.execute("SELECT %s FROM res_company WHERE id = %%s" % field, (company.id,))
    assert env.cr.fetchone()[0] == certificate.id, "res_company.%s not stored" % field
    record(env, "%s.company_id" % prefix, company.id)
    record_certificate(env, prefix, certificate.id, cert, content, key)
    record(env, "%s.cert_password" % prefix, PASSWORD)
    record_storage(env, prefix, model, "content", certificate.id)


def seed_cl(env):
    """SII certificate (PKCS#12 file, passphrase, owner, token, subject RUT)."""
    company = make_company(env, "OUE18 CL", "cl", "cl")
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    key, cert = make_certificate("CL", "OUE18 CL firma", CL_RUT)
    content = pkcs12_content(key, cert, "oue18-cl")
    token_time = fields.Datetime.now().replace(microsecond=0)
    certificate = env["l10n_cl.certificate"].create(
        {
            "signature_filename": "oue18-cl.pfx",
            "signature_key_file": base64.b64encode(content),
            "signature_pass_phrase": PASSWORD,
            "company_id": company.id,
            "user_id": env.ref("base.user_admin").id,
            "last_token": "OUE18-CL-TOKEN",
            "token_time": token_time,
        }
    )
    env.flush_all()
    assert certificate.subject_serial_number == CL_RUT, (
        "subject serial number not computed: %s" % certificate.subject_serial_number
    )
    record(env, "cl.company_id", company.id)
    record_certificate(env, "cl", certificate.id, cert, content, key)
    record(env, "cl.cert_password", PASSWORD)
    record(env, "cl.user_id", certificate.user_id.id)
    record(env, "cl.last_token", certificate.last_token)
    record(env, "cl.token_time", utc_text(token_time))
    record(env, "cl.subject_serial_number", certificate.subject_serial_number)
    record(env, "cl.name", certificate.signature_filename)
    record_storage(
        env, "cl", "l10n_cl.certificate", "signature_key_file", certificate.id
    )


def seed_ar(env):
    """AFIP PEM certificate and key on a company, and a key-only company."""
    company = make_company(env, "OUE18 AR", "ar", "ar_ri")
    key, cert = make_certificate("AR", "OUE18 AR AFIP")
    certificate, private_key = pem_certificate(cert), pem_key(key)
    company.write(
        {
            "l10n_ar_afip_ws_key": base64.b64encode(private_key),
            "l10n_ar_afip_ws_crt": base64.b64encode(certificate),
        }
    )
    env.flush_all()
    record(env, "ar.company_id", company.id)
    record_certificate(env, "ar", None, cert, certificate, key)
    record(env, "ar.key_content_sha1", sha1(private_key))
    record(env, "ar.crt_fname", company.l10n_ar_afip_ws_crt_fname)
    record_storage(env, "ar", "res.company", "l10n_ar_afip_ws_crt", company.id)
    second = make_company(env, "OUE18 AR2", "ar")
    second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second.l10n_ar_afip_ws_key = base64.b64encode(pem_key(second_key))
    env.flush_all()
    record(env, "ar2.company_id", second.id)
    record(env, "ar2.key_pem_sha1", sha1(pem_key(second_key)))


def seed_nl(env):
    """Digipoort certificate, key and root certificate on two companies."""
    company = make_company(env, "OUE18 NL", "nl", "nl")
    key, cert = make_certificate("NL", "OUE18 NL Digipoort")
    _root_key, root = make_certificate("NL", "OUE18 NL SBR root")
    company.write(
        {
            "l10n_nl_reports_sbr_cert": base64.b64encode(pem_certificate(cert)),
            "l10n_nl_reports_sbr_key": base64.b64encode(pem_key(key)),
            "l10n_nl_reports_sbr_cert_filename": "oue18-nl.pem",
            "l10n_nl_reports_sbr_key_filename": "oue18-nl.key",
            "l10n_nl_reports_sbr_server_root_cert": base64.b64encode(
                pem_certificate(root)
            ),
        }
    )
    second = make_company(env, "OUE18 NL2", "nl")
    second_key, second_cert = make_certificate("NL", "OUE18 NL2 Digipoort")
    encrypted = pem_key(second_key, LOST_PASSWORD)
    second.write(
        {
            "l10n_nl_reports_sbr_cert": base64.b64encode(pem_certificate(second_cert)),
            "l10n_nl_reports_sbr_key": base64.b64encode(encrypted),
            "l10n_nl_reports_sbr_cert_filename": "oue18-nl2.pem",
            "l10n_nl_reports_sbr_key_filename": "oue18-nl2.key",
        }
    )
    env.flush_all()
    record(env, "nl.company_id", company.id)
    record_certificate(env, "nl", None, cert, pem_certificate(cert), key)
    record(env, "nl.cert_filename", "oue18-nl.pem")
    record(env, "nl.key_filename", "oue18-nl.key")
    record_storage(env, "nl", "res.company", "l10n_nl_reports_sbr_cert", company.id)
    record(env, "nl_root.company_id", company.id)
    record_certificate(env, "nl_root", None, root, pem_certificate(root))
    record(env, "nl2.company_id", second.id)
    record_certificate(env, "nl2", None, second_cert, pem_certificate(second_cert))
    record(env, "nl2.key_content_sha1", sha1(encrypted))


def seed_be(env):
    """ONSS PEM certificate with its encrypted key, passphrase and key file."""
    for prefix, stale_key_file in (("be", False), ("be2", True)):
        company = make_company(env, "OUE18 %s" % prefix.upper(), "be")
        key, cert = make_certificate("BE", "OUE18 %s ONSS" % prefix.upper())
        bundle = pem_certificate(cert) + pem_key(key, PASSWORD)
        key_file = pem_key(
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            if stale_key_file
            else key
        )
        company.write(
            {
                "onss_pem_certificate": base64.b64encode(bundle),
                "onss_key": base64.b64encode(key_file),
                "onss_pem_passphrase": PASSWORD,
                "onss_expeditor_number": "OUE18%s" % prefix.upper(),
            }
        )
        env.flush_all()
        record(env, "%s.company_id" % prefix, company.id)
        record_certificate(env, prefix, None, cert, bundle, key)
        record(env, "%s.cert_password" % prefix, PASSWORD)
        record(env, "%s.stale_key_file" % prefix, stale_key_file)
        record_storage(env, prefix, "res.company", "onss_pem_certificate", company.id)


def seed_plm(env):
    """Two ECOs whose displayed image id collides with, or misses, product_document.

    18.0 points the displayed image at product.document instead of
    mrp.document. "low" takes the id of an existing product.document when
    mrp_document is empty, so a foreign key check alone would pass on a wrong
    row; "high" gets an id no product_document row has, so an unmapped value
    breaks the foreign key.
    """
    template = env["product.template"].create(
        {"name": "OUE18 PLM product", "type": "consu"}
    )
    product_document = env["product.document"].create(
        {
            "name": "oue18-plm-specification.txt",
            "datas": base64.b64encode(b"OUE18 product document"),
            "res_model": "product.template",
            "res_id": template.id,
        }
    )
    eco_type = env.ref("mrp_plm.ecotype0")
    stage = env["mrp.eco.stage"].search([("type_ids", "in", eco_type.id)], limit=1)
    env.cr.execute("SELECT count(*), coalesce(max(id), 0) FROM mrp_document")
    count, max_id = env.cr.fetchone()
    env.cr.execute("SELECT pg_get_serial_sequence('mrp_document', 'id')")
    sequence = env.cr.fetchone()[0]
    if count == 0 and max_id < product_document.id:
        env.cr.execute("SELECT setval(%s, %s, false)", (sequence, product_document.id))
    ecos = {}
    for label in ("low", "high"):
        if label == "high":
            env.cr.execute("SELECT setval(%s, %s, false)", (sequence, HIGH_DOCUMENT_ID))
        eco = env["mrp.eco"].create(
            {
                "name": "OUE18 ECO %s id" % label,
                "type_id": eco_type.id,
                "stage_id": stage.id,
                "type": "product",
                "product_tmpl_id": template.id,
            }
        )
        document = env["mrp.document"].create(
            {
                "name": "oue18-eco-%s.png" % label,
                "datas": PNG_1PX,
                "res_model": "mrp.eco",
                "res_id": eco.id,
            }
        )
        eco.displayed_image_id = document
        ecos[label] = (eco, document)
    env.flush_all()
    record(env, "plm.product_document_id", product_document.id)
    for label, (eco, document) in ecos.items():
        record(env, "plm.eco_%s_id" % label, eco.id)
        record(env, "plm.doc_%s_id" % label, document.id)
        record(env, "plm.att_%s_id" % label, document.ir_attachment_id.id)
        record(env, "plm.att_%s_checksum" % label, document.ir_attachment_id.checksum)
        record(env, "plm.att_%s_mimetype" % label, document.ir_attachment_id.mimetype)
    record(env, "plm.collision", ecos["low"][1].id == product_document.id)
    assert ecos["high"][1].id == HIGH_DOCUMENT_ID, (
        "high mrp.document did not get id %s" % HIGH_DOCUMENT_ID
    )


def cd_companies(env):
    """Companies of the company-dependent blocks: main (a), b and c (no value).

    b gets the generic chart when accounting is installed, so it has accounts
    and journals of its own; c never gets a value, so the empty case is seen.
    Created once and reused by every block.
    """
    env.cr.execute(
        "SELECT k, v FROM oue18_seed WHERE k IN ('cd.company_b_id', 'cd.company_c_id')"
    )
    seeded = dict(env.cr.fetchall())
    main_company = env.ref("base.main_company")
    if seeded:
        return (
            main_company,
            env["res.company"].browse(int(seeded["cd.company_b_id"])),
            env["res.company"].browse(int(seeded["cd.company_c_id"])),
        )
    chart = "generic_coa" if installed(env, "account") else None
    if chart and not main_company.chart_template:
        env["account.chart.template"].try_loading(
            chart, main_company, install_demo=False
        )
    company_b = make_company(env, "OUE18 CD B", "us", chart)
    company_c = make_company(env, "OUE18 CD C", "us")
    record(env, "cd.company_a_id", main_company.id)
    record(env, "cd.company_b_id", company_b.id)
    record(env, "cd.company_c_id", company_c.id)
    return main_company, company_b, company_c


def seed_cd_followup(env):
    """Follow-up date and responsible of one partner, per company."""
    company_a, company_b, _company_c = cd_companies(env)
    user_b = env["res.users"].create(
        {
            "name": "OUE18 CD follow-up B",
            "login": "oue18-cd-followup-b",
            "company_id": company_b.id,
            "company_ids": [Command.set((company_a | company_b).ids)],
        }
    )
    partner = env["res.partner"].create({"name": "OUE18 CD follow-up partner"})
    values = {
        company_a: ("2025-03-03", env.ref("base.user_admin")),
        company_b: ("2025-04-14", user_b),
    }
    for company, (date, user) in values.items():
        partner.with_company(company).write(
            {"followup_next_action_date": date, "followup_responsible_id": user.id}
        )
    env.flush_all()
    record(env, "fu.partner_id", partner.id)
    for label, company in (("a", company_a), ("b", company_b)):
        record(env, "fu.date_%s" % label, values[company][0])
        record(env, "fu.user_%s" % label, values[company][1].id)


def seed_cd_payroll(env):
    """Salary journal of a structure and accounts of a rule, per company."""
    company_a, company_b, _company_c = cd_companies(env)
    structure = env.ref("hr_payroll.default_structure")
    rule = env["hr.salary.rule"].create(
        {
            "name": "OUE18 CD rule",
            "code": "OUE18CD",
            "struct_id": structure.id,
            "category_id": env.ref("hr_payroll.BASIC").id,
            "amount_select": "fix",
            "amount_fix": 1.0,
        }
    )
    plan = env["account.analytic.plan"].create({"name": "OUE18 CD plan"})
    record(env, "pay.structure_id", structure.id)
    record(env, "pay.rule_id", rule.id)
    for label, company in (("a", company_a), ("b", company_b)):
        accounts = env["account.account"].search(
            [("company_id", "=", company.id), ("deprecated", "=", False)],
            order="code",
        )
        expense = accounts.filtered(lambda a: a.account_type == "expense")[:1]
        liability = accounts.filtered(lambda a: a.account_type == "liability_current")[
            :1
        ]
        journal = env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "general")],
            order="id",
            limit=1,
        )
        analytic = env["account.analytic.account"].create(
            {
                "name": "OUE18 CD analytic %s" % label,
                "plan_id": plan.id,
                "company_id": company.id,
            }
        )
        assert expense and liability and journal, (
            "company %s has no chart for the payroll seed" % company.id
        )
        structure.with_company(company).journal_id = journal
        rule.with_company(company).write(
            {
                "account_debit": expense.id,
                "account_credit": liability.id,
                "analytic_account_id": analytic.id,
            }
        )
        record(env, "pay.journal_%s" % label, journal.id)
        record(env, "pay.debit_%s" % label, expense.id)
        record(env, "pay.credit_%s" % label, liability.id)
        record(env, "pay.analytic_%s" % label, analytic.id)
    env.flush_all()


def seed_cd_fsm(env):
    """Worksheet template of a field service product, per company."""
    company_a, company_b, _company_c = cd_companies(env)
    template_a = env.ref("industry_fsm_report.fsm_worksheet_template")
    template_b = (
        env["worksheet.template"]
        .with_context(worksheet_no_generation=True)
        .create({"name": "OUE18 CD worksheet B", "res_model": "project.task"})
    )
    product = env["product.template"].create(
        {"name": "OUE18 CD field service", "type": "service", "sale_ok": True}
    )
    product.with_company(company_a).worksheet_template_id = template_a
    product.with_company(company_b).worksheet_template_id = template_b
    env.flush_all()
    record(env, "fsm.product_id", product.id)
    record(env, "fsm.template_a", template_a.id)
    record(env, "fsm.template_b", template_b.id)


def seed_cd_rental(env):
    """Extra hour and day prices of a rental product, per company, and a default."""
    company_a, company_b, _company_c = cd_companies(env)
    product = env["product.template"].create(
        {"name": "OUE18 CD rental", "type": "consu", "rent_ok": True}
    )
    values = {company_a: (5.5, 40.0), company_b: (7.25, 60.0)}
    for company, (hourly, daily) in values.items():
        product.with_company(company).write(
            {"extra_hourly": hourly, "extra_daily": daily}
        )
    env["ir.property"]._set_default("extra_hourly", "product.template", 3.0, company_b)
    env.flush_all()
    record(env, "rent.product_id", product.id)
    for label, company in (("a", company_a), ("b", company_b)):
        record(env, "rent.hourly_%s" % label, values[company][0])
        record(env, "rent.daily_%s" % label, values[company][1])
    record(env, "rent.default_hourly_b", 3.0)
    record_refs(
        env,
        "rent",
        ["sale_renting.property_extra_hourly", "sale_renting.property_extra_daily"],
    )


def seed_cd_stock_rental(env):
    """Preparation time of a storable rental product, per company."""
    company_a, company_b, _company_c = cd_companies(env)
    product = env["product.template"].create(
        {"name": "OUE18 CD stock rental", "type": "product", "rent_ok": True}
    )
    values = {company_a: 1.5, company_b: 2.25}
    for company, hours in values.items():
        product.with_company(company).preparation_time = hours
    env.flush_all()
    record(env, "srent.product_id", product.id)
    record(env, "srent.prep_a", values[company_a])
    record(env, "srent.prep_b", values[company_b])
    record_refs(env, "srent", ["sale_stock_renting.property_padding_time"])


def seed_cd_sla(env):
    """SLA policy of a service per company, and a policy linked by hand to a line.

    x (company a) and y (company b) are the policy of service s in their
    company; z is linked to an order line of service t, which has no policy.
    """
    company_a, company_b, _company_c = cd_companies(env)
    policies = {}
    for label, company in (("x", company_a), ("y", company_b), ("z", company_a)):
        team = env["helpdesk.team"].create(
            {
                "name": "OUE18 CD team %s" % label,
                "company_id": company.id,
                "use_sla": True,
            }
        )
        policies[label] = env["helpdesk.sla"].create(
            {
                "name": "OUE18 CD SLA %s" % label,
                "team_id": team.id,
                "stage_id": team.stage_ids[-1:].id,
                "time": 8.0,
            }
        )
    service = env["product.template"].create(
        {"name": "OUE18 CD SLA service", "type": "service", "sale_ok": True}
    )
    service.with_company(company_a).sla_id = policies["x"]
    service.with_company(company_b).sla_id = policies["y"]
    other = env["product.template"].create(
        {"name": "OUE18 CD SLA other", "type": "service", "sale_ok": True}
    )
    order = env["sale.order"].create(
        {
            "partner_id": env["res.partner"]
            .create({"name": "OUE18 CD SLA customer"})
            .id,
            "company_id": company_a.id,
            "order_line": [
                Command.create(
                    {"product_id": other.product_variant_id.id, "product_uom_qty": 1}
                )
            ],
        }
    )
    policies["z"].sale_line_ids = [Command.set(order.order_line.ids)]
    env.flush_all()
    record(env, "sla.service_id", service.id)
    record(env, "sla.other_id", other.id)
    record(env, "sla.line_id", order.order_line.id)
    for label, policy in policies.items():
        record(env, "sla.%s_id" % label, policy.id)


def seed_de(env):
    """DATEV numbers of two companies and DATEV identifiers of three partners."""
    company_a, _company_b, company_c = cd_companies(env)
    company_de = make_company(env, "OUE18 DE", "de", "de_skr03")
    numbers = {company_de: ("1001001", "10010"), company_a: ("2002002", "20020")}
    for company, (consultant, client) in numbers.items():
        company.with_company(company).write(
            {
                "l10n_de_datev_consultant_number": consultant,
                "l10n_de_datev_client_number": client,
            }
        )
    shared = env["res.partner"].create(
        {
            "name": "OUE18 DATEV shared",
            "l10n_de_datev_identifier": 70001,
            "l10n_de_datev_identifier_customer": 10001,
        }
    )
    own = env["res.partner"].create(
        {
            "name": "OUE18 DATEV DE only",
            "company_id": company_de.id,
            "l10n_de_datev_identifier": 70002,
        }
    )
    empty = env["res.partner"].create({"name": "OUE18 DATEV none"})
    env.flush_all()
    record(env, "de.company_id", company_de.id)
    record(env, "de.consultant_de", numbers[company_de][0])
    record(env, "de.client_de", numbers[company_de][1])
    record(env, "de.consultant_a", numbers[company_a][0])
    record(env, "de.client_a", numbers[company_a][1])
    record(env, "de.empty_company_id", company_c.id)
    record(env, "de.shared_id", shared.id)
    record(env, "de.own_id", own.id)
    record(env, "de.empty_id", empty.id)


def seed_ec_cd(env):
    """Second EC company, withholding taxes per company and the EC chart groups.

    The taxpayer type and a product get different withholding taxes in the two
    EC companies and none in the main company. For both EC companies the ids
    of the three chart groups 18.0 turns into accounts are recorded.
    """
    env.cr.execute("SELECT v FROM oue18_seed WHERE k = 'ec.company_id'")
    company_ec = env["res.company"].browse(int(env.cr.fetchone()[0]))
    company_ec2 = make_company(env, "OUE18 EC2", "ec", "ec")
    record(env, "ec2.company_id", company_ec2.id)
    taxpayer = env.ref("l10n_ec_edi.l10n_ec_taxpayer_type_01")
    product = env["product.template"].create(
        {"name": "OUE18 EC withhold product", "type": "service"}
    )
    record(env, "ec_cd.taxpayer_id", taxpayer.id)
    record(env, "ec_cd.product_id", product.id)
    for prefix, company, first, second in (
        ("ec", company_ec, 0, 1),
        ("ec2", company_ec2, 1, 0),
    ):
        taxes = {}
        for kind in ("withhold_income_purchase", "withhold_vat_purchase"):
            taxes[kind] = env["account.tax"].search(
                [
                    ("company_id", "=", company.id),
                    ("tax_group_id.l10n_ec_type", "=", kind),
                ],
                order="id",
            )
            assert len(taxes[kind]) > 1, "company %s lacks %s taxes" % (
                company.id,
                kind,
            )
        income = taxes["withhold_income_purchase"]
        vat = taxes["withhold_vat_purchase"]
        taxpayer.with_company(company).write(
            {
                "profit_withhold_tax_id": income[first].id,
                "vat_goods_withhold_tax_id": vat[first].id,
                "vat_services_withhold_tax_id": vat[second].id,
            }
        )
        product.with_company(company).l10n_ec_withhold_tax_id = income[second]
        record(env, "ec_cd.profit_%s" % prefix, income[first].id)
        record(env, "ec_cd.vat_goods_%s" % prefix, vat[first].id)
        record(env, "ec_cd.vat_services_%s" % prefix, vat[second].id)
        record(env, "ec_cd.product_tax_%s" % prefix, income[second].id)
        for template_id in ("ec51020205", "ec51030205", "ec52010405"):
            group = env.ref("account.%s_%s" % (company.id, template_id))
            assert group._name == "account.group", "%s is %s" % (template_id, group)
            record(env, "ec_chart.%s.%s" % (prefix, template_id), group.id)
    env.flush_all()


def raw_value(env, table, column, res_id):
    """Column value as stored (a translated field comes back as a dict)."""
    env.cr.execute('SELECT "%s" FROM "%s" WHERE id = %%s' % (column, table), (res_id,))
    return env.cr.fetchone()[0]


def id_list(records):
    """Sorted comma list of record ids, the form the verify compares."""
    return ",".join(str(i) for i in sorted(records.ids))


def seed_social(env):
    """Template and post with images on the 17.0 default image relations."""
    attachments = env["ir.attachment"].create(
        [
            {
                "name": "oue18-social-%s.png" % index,
                "datas": PNG_1PX,
                "mimetype": "image/png",
            }
            for index in (1, 2, 3)
        ]
    )
    template = env["social.post.template"].create(
        {
            "message": "OUE18 social template",
            "image_ids": [Command.set(attachments[:2].ids)],
        }
    )
    post = env["social.post"].create(
        {
            "message": "OUE18 social post",
            "image_ids": [Command.set(attachments[1:].ids)],
        }
    )
    env.flush_all()
    for table, column, res_id in (
        (
            "ir_attachment_social_post_template_rel",
            "social_post_template_id",
            template.id,
        ),
        ("ir_attachment_social_post_rel", "social_post_id", post.id),
    ):
        env.cr.execute(
            'SELECT count(*) FROM "%s" WHERE "%s" = %%s' % (table, column), (res_id,)
        )
        assert env.cr.fetchone()[0] == 2, "%s holds no image of %s" % (table, res_id)
    record(env, "social.template_id", template.id)
    record(env, "social.template_images", id_list(attachments[:2]))
    record(env, "social.template_message", template.message)
    record(env, "social.post_id", post.id)
    record(env, "social.post_images", id_list(attachments[1:]))
    record(env, "social.post_message", post.message)


def seed_worksheet(env):
    """Templates for no company, one company and two companies."""
    company_a, company_b, _company_c = cd_companies(env)
    templates = env["worksheet.template"].with_context(worksheet_no_generation=True)
    specs = {
        "none": (env["res.company"], ""),
        "one": (company_b, company_b.id),
        "two": (company_a | company_b, ""),
    }
    for label, (companies, expected) in specs.items():
        template = templates.create(
            {
                "name": "OUE18 worksheet %s" % label,
                "res_model": "res.partner",
                "company_ids": [Command.set(companies.ids)],
            }
        )
        record(env, "wks.%s_id" % label, template.id)
        record(env, "wks.%s_company" % label, expected)
    env.flush_all()
    env.cr.execute(
        "SELECT count(*) FROM res_company_worksheet_template_rel"
        " WHERE worksheet_template_id IN %s",
        (tuple(templates.search([("name", "like", "OUE18 worksheet")]).ids),),
    )
    record(env, "wks.rel_rows", env.cr.fetchone()[0])


def seed_accountant(env):
    """Deferred journal and computation method of three companies."""
    companies = dict(zip("abc", cd_companies(env)))
    methods = {"a": "day", "b": "full_months", "c": None}
    for label, company in companies.items():
        journal = env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "general")],
            order="id",
            limit=1,
        )
        values = {"deferred_journal_id": journal.id}
        if methods[label]:
            values["deferred_amount_computation_method"] = methods[label]
        company.write(values)
        record(env, "acct.company_%s" % label, company.id)
        record(env, "acct.journal_%s" % label, journal.id or "")
        record(
            env, "acct.method_%s" % label, company.deferred_amount_computation_method
        )
    env.flush_all()


def seed_planning(env):
    """Shift templates and the end hour and day span 17.0 computes for them.

    Besides the 17.0 computed end_time and duration_days, records the number of
    working days the 17.0 shift touches (``span``), read from the 17.0 calendar
    the way the template compute plans it: today at the start hour in the
    planning timezone, plus ``duration`` working hours. Company a lets
    employees unassign themselves, company b does not (a boolean in 17.0, a
    selection in 18.0).
    """
    calendar = env.company.resource_calendar_id
    tz = pytz.timezone(env["planning.slot"]._get_tz())
    today = datetime.date.today()
    record(env, "plan.calendar", "%s %s %s" % (calendar.id, calendar.tz, tz.zone))
    record(env, "plan.today", today)
    specs = {"t1": (8.0, 8.0), "t2": (13.0, 8.0), "t3": (9.0, 24.0), "t4": (8.0, 4.0)}
    for label, (start, duration) in specs.items():
        template = env["planning.slot.template"].create(
            {"start_time": start, "duration": duration}
        )
        start_dt = tz.localize(
            datetime.datetime.combine(today, datetime.time(int(start)))
        )
        end_dt = calendar.plan_hours(duration, start_dt, compute_leaves=True)
        intervals = calendar._work_intervals_batch(start_dt, end_dt)[False]
        span = len({begin.astimezone(tz).date() for begin, _end, _meta in intervals})
        record(env, "plan.%s_id" % label, template.id)
        record(env, "plan.%s_start" % label, start)
        record(env, "plan.%s_end" % label, template.end_time)
        record(env, "plan.%s_days" % label, template.duration_days)
        record(env, "plan.%s_span" % label, max(span, 1))
    company_a, company_b, _company_c = cd_companies(env)
    company_a.planning_allow_self_unassign = True
    company_b.planning_allow_self_unassign = False
    record(env, "plan.unassign_company", company_a.id)
    record(env, "plan.switch_company", company_b.id)
    env.flush_all()


def seed_budget(env):
    """Budget lines on analytic accounts of three plans, and budgets per state.

    The lines sit on accounts of the project plan, of another root plan and of
    a child of that plan; the copies of the budget are confirmed, validated,
    canceled and done, the 17.0 states 18.0 renames.
    """
    plans = env["account.analytic.plan"]
    project_plan = plans.browse(
        int(env["ir.config_parameter"].get_param("analytic.project_plan"))
    )
    other_plan = plans.create({"name": "OUE18 budget plan"})
    child_plan = plans.create(
        {"name": "OUE18 budget child", "parent_id": other_plan.id}
    )
    budget = env["crossovered.budget"].create(
        {"name": "OUE18 budget", "date_from": "2026-01-01", "date_to": "2026-12-31"}
    )
    for label, plan in (
        ("project", project_plan),
        ("other", other_plan),
        ("child", child_plan),
    ):
        account = env["account.analytic.account"].create(
            {"name": "OUE18 budget %s" % label, "plan_id": plan.id}
        )
        line = env["crossovered.budget.lines"].create(
            {
                "crossovered_budget_id": budget.id,
                "analytic_account_id": account.id,
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "planned_amount": 1000.0,
            }
        )
        record(env, "bud.%s_line" % label, line.id)
        record(env, "bud.%s_account" % label, account.id)
    record(env, "bud.project_plan", project_plan.id)
    record(env, "bud.other_plan", other_plan.id)
    for state in ("confirm", "validate", "cancel", "done"):
        stated = budget.copy({"name": "OUE18 budget %s" % state})
        stated.state = state
        record(env, "bud.state_%s" % state, stated.id)
    env.flush_all()


def seed_documents(env):
    """Workspaces with and without groups, their documents and their users.

    Also two tags of the same name in two facets (unique per facet in 17.0,
    globally in 18.0) and a requested document, of the type 'empty' 18.0
    drops.
    """
    groups = env["res.groups"]
    writers = groups.create({"name": "OUE18 documents writers"})
    readers = groups.create({"name": "OUE18 documents readers"})
    base_user = env.ref("base.group_user")
    doc_user = env.ref("documents.group_documents_user")
    doc_manager = env.ref("documents.group_documents_manager")
    users = {}
    for label, extra in (
        ("writer", doc_user | writers),
        ("reader", doc_user | readers),
        ("outsider", doc_user),
        ("manager", doc_manager),
    ):
        users[label] = env["res.users"].create(
            {
                "name": "OUE18 documents %s" % label,
                "login": "oue18-documents-%s" % label,
                "groups_id": [Command.set((base_user | extra).ids)],
            }
        )
    admin = env.ref("base.user_admin")
    folders = env["documents.folder"]
    folder = {
        "open": folders.create({"name": "OUE18 open"}),
        "restricted": folders.create(
            {
                "name": "OUE18 restricted",
                "group_ids": [Command.set(writers.ids)],
                "read_group_ids": [Command.set(readers.ids)],
            }
        ),
        "own": folders.create(
            {
                "name": "OUE18 own",
                "group_ids": [Command.set(writers.ids)],
                "read_group_ids": [Command.set(readers.ids)],
                "user_specific": True,
                "user_specific_write": True,
            }
        ),
    }
    folder["sub"] = folders.create(
        {"name": "OUE18 open sub", "parent_folder_id": folder["restricted"].id}
    )
    documents = {}
    for label, workspace, owner in (
        ("open", "open", admin),
        ("restricted", "restricted", admin),
        ("sub", "sub", admin),
        ("own_reader", "own", users["reader"]),
        ("own_writer", "own", users["writer"]),
        ("own_admin", "own", admin),
    ):
        documents[label] = env["documents.document"].create(
            {
                "name": "OUE18 %s" % label,
                "type": "url",
                "url": "https://example.com/oue18-%s" % label,
                "folder_id": folder[workspace].id,
                "owner_id": owner.id,
            }
        )
    env.flush_all()
    for label, user in users.items():
        record(env, "doc.user_%s" % label, user.id)
        record(env, "doc.partner_%s" % label, user.partner_id.id)
    for label, workspace in folder.items():
        record(env, "doc.folder_%s" % label, workspace.id)
    for label, document in documents.items():
        record(env, "doc.document_%s" % label, document.id)
    record(env, "doc.managers", id_list(doc_manager.users))
    facets = env["documents.facet"].create(
        [
            {"name": "OUE18 facet %s" % label, "folder_id": folder["open"].id}
            for label in ("one", "two")
        ]
    )
    tags = env["documents.tag"].create(
        [{"name": "OUE18 contract", "facet_id": facet.id} for facet in facets]
    )
    request = env["documents.document"].create(
        {"name": "OUE18 request", "folder_id": folder["open"].id}
    )
    request.tag_ids = [Command.set(tags[1:].ids)]
    env.flush_all()
    assert request.type == "empty", request.type
    record(env, "doc.tags", id_list(tags))
    record(env, "doc.request", request.id)


def seed_appraisal(env):
    """Translated company templates and a department with templates of its own."""
    env["res.lang"]._activate_lang("fr_FR")
    company = env.ref("base.main_company")
    company.write(
        {
            "appraisal_employee_feedback_template": "<p>OUE18 employee feedback</p>",
            "appraisal_manager_feedback_template": "<p>OUE18 manager feedback</p>",
        }
    )
    company.update_field_translations(
        "appraisal_employee_feedback_template",
        {"fr_FR": {"OUE18 employee feedback": "OUE18 retour employé"}},
    )
    custom = env["hr.department"].create(
        {
            "name": "OUE18 appraisal custom",
            "custom_appraisal_templates": True,
            "employee_feedback_template": "<p>OUE18 department employee</p>",
            "manager_feedback_template": "<p>OUE18 department manager</p>",
        }
    )
    plain = env["hr.department"].create({"name": "OUE18 appraisal plain"})
    env.flush_all()
    record(env, "appr.company_id", company.id)
    record(env, "appr.custom_id", custom.id)
    record(env, "appr.plain_id", plain.id)
    for key, table, column, res_id in (
        (
            "company_employee",
            "res_company",
            "appraisal_employee_feedback_template",
            company.id,
        ),
        (
            "company_manager",
            "res_company",
            "appraisal_manager_feedback_template",
            company.id,
        ),
        ("custom_employee", "hr_department", "employee_feedback_template", custom.id),
        ("custom_manager", "hr_department", "manager_feedback_template", custom.id),
    ):
        value = raw_value(env, table, column, res_id)
        assert isinstance(value, dict), "%s.%s is not a translated column" % (
            table,
            column,
        )
        record(env, "appr.%s" % key, json.dumps(value, sort_keys=True))
    stored = raw_value(
        env, "res_company", "appraisal_employee_feedback_template", company.id
    )
    assert stored.get("fr_FR") and stored["en_US"] != stored["fr_FR"], stored


def seed_payroll_inputs(env):
    """Two custom salary attachment types, one with its input type, and an attachment.

    17.0 computes a payslip only when every attachment type has an input type
    of the same code, so "ded" comes with one (the usual case); "lone" has none
    (a type created and never paid) and a French name when French is active.
    """
    deduction = env["hr.salary.attachment.type"].create(
        {"name": "OUE18 custom deduction", "code": "OUE18DED", "no_end_date": True}
    )
    input_type = env["hr.payslip.input.type"].create(
        {"name": "OUE18 deduction input", "code": "OUE18DED"}
    )
    lone = env["hr.salary.attachment.type"].create(
        {"name": "OUE18 lone deduction", "code": "OUE18LONE"}
    )
    if env["res.lang"]._lang_get("fr_FR"):
        lone.update_field_translations("name", {"fr_FR": "OUE18 retenue seule"})
    env.flush_all()
    name = raw_value(env, "hr_salary_attachment_type", "name", lone.id)
    assert name["en_US"] == "OUE18 lone deduction", name
    employee = env["hr.employee"].create({"name": "OUE18 attachment employee"})
    attachment = env["hr.salary.attachment"].create(
        {
            "employee_ids": [Command.set(employee.ids)],
            "description": "OUE18 attachment",
            "deduction_type_id": deduction.id,
            "monthly_amount": 50.0,
        }
    )
    env.flush_all()
    record(env, "payin.ded_code", deduction.code)
    record(env, "payin.ded_input_id", input_type.id)
    record(env, "payin.ded_input_name", input_type.name)
    record(env, "payin.lone_code", lone.code)
    record(env, "payin.lone_name", name["en_US"])
    record(env, "payin.lone_name_keys", ",".join(sorted(name)))
    record(env, "payin.attachment_id", attachment.id)


RADIUS_SPECS = {
    "s_m": ("sendcloud", 1500, "product_uom_meter"),
    "s_mi": ("sendcloud", 10, "product_uom_mile"),
    "s_km": ("sendcloud", 30, "product_uom_km"),
    "f_km": ("fedex", 15, "product_uom_km"),
    "f_mi": ("fedex", 10, "product_uom_mile"),
}
RADIUS_EXPECTED = {
    "km": {"s_m": 2, "s_mi": 16, "s_km": 30, "f_km": 15, "f_mi": 16},
    "mi": {"s_m": 1, "s_mi": 10, "s_km": 19, "f_km": 9, "f_mi": 10},
}


def seed_delivery(env):
    """Sendcloud and FedEx carriers with radiuses in m, mi and km."""
    if not (
        installed(env, "website_delivery_sendcloud")
        or installed(env, "website_sale_fedex")
    ):
        return
    system = "mi" if env.cr.dbname.endswith("_mi") else "km"
    env["ir.config_parameter"].set_param(
        "product.volume_in_cubic_feet", "1" if system == "mi" else "0"
    )
    product = env["product.product"].create(
        {"name": "OUE18 delivery", "type": "service"}
    )
    record(env, "dlv.system", system)
    for label, (provider, value, uom) in RADIUS_SPECS.items():
        module = (
            "website_delivery_sendcloud"
            if provider == "sendcloud"
            else "website_sale_fedex"
        )
        if not installed(env, module):
            continue
        values = {
            "name": "OUE18 %s %s" % (provider, label),
            "delivery_type": provider,
            "product_id": product.id,
            "%s_locations_radius_value" % provider: value,
            "%s_locations_radius_unit" % provider: env.ref("uom.%s" % uom).id,
        }
        if provider == "sendcloud":
            values.update(
                sendcloud_public_key="oue18-public", sendcloud_secret_key="oue18-secret"
            )
        carrier = env["delivery.carrier"].create(values)
        record(env, "dlv.%s_id" % label, carrier.id)
        record(env, "dlv.%s_value" % label, RADIUS_EXPECTED[system][label])
    env.flush_all()


def seed_au(env):
    """Horticulture payslip lines, a custom rule and the rules of every structure.

    The horticulture contract also carries a casual loading entered as the
    17.0 form stores it (0.25 for 25 %), a withholding variation and an
    employment basis, which 18.0 moves to the employee; a second contract has
    its loading imported as a percentage (25), which 18.0 no longer accepts.
    """
    module = "l10n_au_hr_payroll"
    removed = [
        "hr_payroll_structure_au_no_tfn",
        "hr_payroll_structure_au_whm",
        "hr_payroll_structure_au_senior",
        "hr_payroll_structure_au_lumpsum",
        "hr_payroll_structure_au_actor",
        "hr_payroll_structure_au_actor_promotional",
        "hr_payroll_structure_au_horticulture",
        "hr_payroll_structure_au_return_to_work",
        "hr_payroll_structure_au_termination",
    ]
    structures = env["hr.payroll.structure"].browse(
        [env.ref("%s.%s" % (module, xmlid)).id for xmlid in removed]
    )
    regular = env.ref("%s.hr_payroll_structure_au_regular" % module)
    horticulture = env.ref("%s.hr_payroll_structure_au_horticulture" % module)
    no_tfn = env.ref("%s.hr_payroll_structure_au_no_tfn" % module)
    custom = env["hr.salary.rule"].create(
        {
            "name": "OUE18 AU custom withholding",
            "code": "WITHHOLD",
            "struct_id": no_tfn.id,
            "category_id": env.ref("hr_payroll.DED").id,
            "amount_select": "fix",
            "amount_fix": 1.0,
        }
    )
    employee = env["hr.employee"].create({"name": "OUE18 AU employee"})
    contract = env["hr.contract"].create(
        {
            "name": "OUE18 AU contract",
            "employee_id": employee.id,
            "wage": 5000.0,
            "structure_type_id": env.ref("%s.structure_type_schedule_2" % module).id,
            "date_start": "2026-01-01",
        }
    )
    payslip = env["hr.payslip"].create(
        {
            "name": "OUE18 AU payslip",
            "employee_id": employee.id,
            "contract_id": contract.id,
            "struct_id": horticulture.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        }
    )
    rules = {
        "withhold": env.ref("%s.l10n_au_withholding_structure_2" % module),
        "basic": horticulture.rule_ids.filtered(lambda r: r.code == "BASIC")[:1],
        "gone": env.ref("%s.l10n_au_allowance_withholding_structure_1" % module),
    }
    assert rules["basic"] and not rules["basic"].get_external_id()[rules["basic"].id]
    for label, rule in rules.items():
        line = env["hr.payslip.line"].create(
            {
                "slip_id": payslip.id,
                "salary_rule_id": rule.id,
                "contract_id": contract.id,
                "employee_id": employee.id,
                "name": rule.name,
                "code": rule.code,
                "category_id": rule.category_id.id,
                "sequence": rule.sequence,
                "amount": 1.0,
                "quantity": 1.0,
                "rate": 100.0,
            }
        )
        record(env, "au.rule_%s" % label, rule.id)
        record(env, "au.line_%s" % label, line.id)
    env.flush_all()
    removed_rules = (
        env["hr.salary.rule"]
        .with_context(active_test=False)
        .search([("struct_id", "in", structures.ids)])
    )
    record(env, "au.regular_id", regular.id)
    record(env, "au.structures", id_list(structures))
    record(env, "au.removed_rules", id_list(removed_rules))
    record(
        env,
        "au.rule_structures",
        ",".join("%s:%s" % (r.id, r.struct_id.id) for r in removed_rules.sorted("id")),
    )
    record(env, "au.custom_rule", custom.id)
    record(env, "au.contract_id", contract.id)
    record(env, "au.payslip_id", payslip.id)
    record(env, "au.regular_rules_17", len(regular.rule_ids))
    contract.write(
        {
            "l10n_au_casual_loading": 0.25,
            "l10n_au_withholding_variation": True,
            "l10n_au_withholding_variation_amount": 15.5,
            "l10n_au_employment_basis_code": "P",
        }
    )
    imported = env["hr.employee"].create({"name": "OUE18 AU imported"})
    imported_contract = env["hr.contract"].create(
        {
            "name": "OUE18 AU imported contract",
            "employee_id": imported.id,
            "wage": 4000.0,
            "structure_type_id": env.ref("%s.structure_type_schedule_1" % module).id,
            "date_start": "2026-01-01",
            "l10n_au_casual_loading": 25.0,
        }
    )
    env.flush_all()
    record(env, "au.employee", employee.id)
    record(env, "au.imported_contract", imported_contract.id)


def seed_mx_stock(env):
    """Customs regimes and hazardous codes of the merged MX stock modules."""
    module = "l10n_mx_edi_stock_extended_30"
    env.cr.execute(
        "SELECT r.code, r.id FROM l10n_mx_edi_customs_regime r"
        " JOIN ir_model_data d ON d.res_id = r.id"
        " AND d.model = 'l10n_mx_edi.customs.regime' AND d.module = %s"
        " ORDER BY r.code",
        (module,),
    )
    regimes = env.cr.fetchall()
    assert len(regimes) == 10, regimes
    imd = env.ref("%s.l10n_mx_edi_customs_regime_imd" % module)
    exd = env.ref("%s.l10n_mx_edi_customs_regime_exd" % module)
    pedimento = env.ref("%s.l10n_mx_edi_customs_document_type_01" % module)
    importer = env["res.partner"].create({"name": "OUE18 MX importer"})
    picking_type = env.ref("stock.picking_type_in")
    locations = {
        "location_id": env.ref("stock.stock_location_suppliers").id,
        "location_dest_id": env.ref("stock.stock_location_stock").id,
    }
    pickings = env["stock.picking"].create(
        [
            {
                "picking_type_id": picking_type.id,
                **locations,
                "partner_id": importer.id,
                "l10n_mx_edi_customs_regime_id": imd.id,
                "l10n_mx_edi_customs_document_type_id": pedimento.id,
                "l10n_mx_edi_pedimento_number": "15  48  3009  0001235",
                "l10n_mx_edi_importer_id": importer.id,
            },
            {
                "picking_type_id": picking_type.id,
                **locations,
                "partner_id": importer.id,
                "l10n_mx_edi_customs_regime_id": imd.id,
                "l10n_mx_edi_customs_regime_ids": [Command.set(exd.ids)],
            },
        ]
    )
    templates = env["product.template"].create(
        [
            {
                "name": "OUE18 MX ammonia",
                "type": "product",
                "unspsc_code_id": env.ref("product_unspsc.unspsc_code_12131500").id,
                "l10n_mx_edi_hazardous_material_code": "1005",
                "l10n_mx_edi_hazard_package_type": "4H2",
                "l10n_mx_edi_material_type": "01",
                "l10n_mx_edi_material_description": "OUE18 raw material",
            },
            {
                "name": "OUE18 MX safe",
                "type": "product",
                "l10n_mx_edi_hazardous_material_code": "0",
            },
            {
                "name": "OUE18 MX unknown code",
                "type": "product",
                "l10n_mx_edi_hazardous_material_code": "ZZ99",
            },
        ]
    )
    env.flush_all()
    record(env, "mxs.regimes", ",".join("%s:%s" % row for row in regimes))
    record(env, "mxs.imd", imd.id)
    record(env, "mxs.exd", exd.id)
    record(env, "mxs.pedimento_type", pedimento.id)
    record(env, "mxs.picking_single", pickings[0].id)
    record(
        env,
        "mxs.picking_single_m2m17",
        id_list(pickings[0].l10n_mx_edi_customs_regime_ids),
    )
    record(env, "mxs.picking_both", pickings[1].id)
    record(
        env,
        "mxs.picking_both_m2m17",
        id_list(pickings[1].l10n_mx_edi_customs_regime_ids),
    )
    record(env, "mxs.tmpl_hazard", templates[0].id)
    record(env, "mxs.tmpl_safe", templates[1].id)
    record(env, "mxs.tmpl_unknown", templates[2].id)


def seed_br_services(env):
    """Cities, service codes and NCM codes of the merged BR services modules."""
    module = "l10n_br_avatax_services"
    company = make_company(env, "OUE18 BR", "br")
    city_sp = env.ref("%s.city_br_001" % module)
    city_rj = env.ref("%s.city_br_002" % module)
    ncm = env.ref("%s.service_1_01" % module)
    partner = env["res.partner"].create(
        {
            "name": "OUE18 BR customer",
            "country_id": env.ref("base.br").id,
            "state_id": city_sp.state_id.id,
            "city_id": city_sp.id,
            "l10n_br_subject_cofins": "Z",
            "l10n_br_iss_simples_rate": 2.5,
        }
    )
    service_code = env["l10n_br.service.code"].create(
        {"code": "OUE18-0101", "city_id": city_rj.id, "company_id": company.id}
    )
    product = (
        env["product.template"]
        .with_company(company)
        .create(
            {
                "name": "OUE18 BR consulting",
                "type": "service",
                "l10n_br_labor": True,
                "l10n_br_service_code_ids": [Command.set(service_code.ids)],
                "l10n_br_property_service_code_origin_id": service_code.id,
            }
        )
    )
    env.flush_all()
    env.cr.execute(
        "SELECT count(*) FROM ir_model_data WHERE module = %s AND model = 'res.city'",
        (module,),
    )
    cities17 = env.cr.fetchone()[0]
    record(env, "brs.company_id", company.id)
    record(env, "brs.cities17", cities17)
    record(env, "brs.city_sp", city_sp.id)
    record(env, "brs.city_rj", city_rj.id)
    record(env, "brs.partner", partner.id)
    record(env, "brs.service_code", service_code.id)
    record(env, "brs.product", product.id)
    record(env, "brs.ncm", ncm.id)
    record(env, "brs.ncm_code", ncm.code)


def seed_riba(env):
    """Italian SIA code of the main company (l10n_it_riba installed on 17.0)."""
    env.company.l10n_it_sia_code = "OUE18"
    module = env["ir.module.module"].search([("name", "=", "l10n_it_riba")])
    record(env, "riba.company_id", env.company.id)
    record(env, "riba.sia", env.company.l10n_it_sia_code)
    record(env, "riba.author17", module.author)


def seed_dashboards(env):
    """Ids of the two 17.0 purchase dashboards."""
    purchase = env.ref(
        "spreadsheet_dashboard_purchase_stock.spreadsheet_dashboard_purchase"
    )
    vendors = env.ref(
        "spreadsheet_dashboard_purchase.spreadsheet_dashboard_vendors",
        raise_if_not_found=False,
    )
    record(env, "dash.purchase", purchase.id)
    record(env, "dash.vendors", vendors.id if vendors else 0)


def seed_keypay(env):
    """Employment Hero settings, payrun move, matchings and system parameters."""
    company = make_company(env, "OUE18 AU KP", "au", "au")
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    journal = env["account.journal"].search(
        [("company_id", "=", company.id), ("type", "=", "general")], limit=1
    )
    account = env["account.account"].search(
        [("company_id", "=", company.id), ("account_type", "=", "expense")], limit=1
    )
    tax = env["account.tax"].search([("company_id", "=", company.id)], limit=1)
    company.write(
        {
            "l10n_au_kp_enable": True,
            "l10n_au_kp_identifier": "OUE18-BIZ-1",
            "l10n_au_kp_lock_date": "2026-01-01",
            "l10n_au_kp_journal_id": journal.id,
        }
    )
    account.l10n_au_kp_account_identifier = "OUE18-EH-ACC"
    tax.l10n_au_kp_tax_identifier = "OUE18-EH-TAX"
    move = env["account.move"].create(
        {
            "move_type": "entry",
            "journal_id": journal.id,
            "date": "2026-02-01",
            "l10n_au_kp_payrun_identifier": 4242,
        }
    )
    params = env["ir.config_parameter"].sudo()
    params.set_param("l10n_au_keypay.l10n_au_kp_api_key", "oue18-api-key")
    params.set_param(
        "l10n_au_keypay.l10n_au_kp_base_url", "https://oue18.example.test/"
    )
    cron = env.ref("l10n_au_keypay.keypay_sync_cron")
    env.flush_all()
    record(env, "kp.company_id", company.id)
    record(env, "kp.other_company_id", env.ref("base.main_company").id)
    record(env, "kp.journal_id", journal.id)
    record(env, "kp.lock_date", "2026-01-01")
    record(env, "kp.account_id", account.id)
    record(env, "kp.tax_id", tax.id)
    record(env, "kp.move_id", move.id)
    record(env, "kp.cron_id", cron.id)
    record(env, "kp.cron_code17", cron.code.strip())


IOT_ACTIONS = {
    "picture": "picture",
    "skip": "SKIP",
    "pause": "PAUS",
    "prev": "PREV",
    "next": "NEXT",
    "validate": "VALI",
    "cloMO": "CLMO",
    "cloWO": "CLWO",
    "finish": "FINI",
    "record": "RECO",
    "cancel": "CANC",
    "print-op": "PROP",
    "print-slip": "PRSL",
    "print": "PRNT",
    "pack": "PACK",
    "scrap": "SCRA",
}


def seed_iot_triggers(env):
    """One keyboard trigger per 17.0 action."""
    box = env["iot.box"].create({"name": "OUE18 box", "identifier": "oue18-box"})
    device = env["iot.device"].create(
        {
            "iot_id": box.id,
            "name": "OUE18 keyboard",
            "identifier": "oue18-keyboard",
            "type": "keyboard",
        }
    )
    triggers = env["iot.trigger"].create(
        [
            {"device_id": device.id, "key": "k%s" % index, "action": action}
            for index, action in enumerate(IOT_ACTIONS)
        ]
    )
    record(
        env,
        "iot.triggers",
        ",".join(
            "%s:%s" % (trigger.id, IOT_ACTIONS[trigger.action]) for trigger in triggers
        ),
    )


def seed_pricer(env):
    """Pricer tags on a single-variant and on a two-variant template, synced.

    A two-variant template without store is created first, so that template
    and variant ids differ and a tag left on its template id points at a
    variant of another product.
    """
    store = env["pricer.store"].create(
        {
            "name": "OUE18 store",
            "pricer_store_identifier": "oue18-store",
            "pricer_tenant_name": "oue18",
            "pricer_login": "oue18",
            "pricer_password": "oue18",
        }
    )
    attribute = env["product.attribute"].create(
        {
            "name": "OUE18 size",
            "value_ids": [Command.create({"name": "S"}), Command.create({"name": "M"})],
        }
    )
    two_sizes = [
        Command.create(
            {
                "attribute_id": attribute.id,
                "value_ids": [Command.set(attribute.value_ids.ids)],
            }
        )
    ]
    spacer = env["product.template"].create(
        {"name": "OUE18 pricer spacer", "attribute_line_ids": two_sizes}
    )
    double = env["product.template"].create(
        {
            "name": "OUE18 pricer double",
            "pricer_store_id": store.id,
            "attribute_line_ids": two_sizes,
        }
    )
    single = env["product.template"].create(
        {"name": "OUE18 pricer single", "pricer_store_id": store.id}
    )
    assert len(double.product_variant_ids) == 2
    assert single.product_variant_ids.id != single.id, "template id equals variant id"
    assert min(double.product_variant_ids.ids) != double.id
    record(env, "pricer.tmpl_spacer", spacer.id)
    tags = env["pricer.tag"].create(
        [
            {"name": "A4081315787313278", "product_id": single.id},
            {"name": "B4093233954716057", "product_id": double.id},
        ]
    )
    tags.pricer_product_to_link = False
    (single | double).pricer_product_to_create_or_update = False
    env.flush_all()
    record(env, "pricer.store", store.id)
    record(env, "pricer.tag_single", tags[0].id)
    record(env, "pricer.tag_double", tags[1].id)
    record(env, "pricer.variant_single", single.product_variant_ids[:1].id)
    record(env, "pricer.variant_double", min(double.product_variant_ids.ids))
    record(env, "pricer.variants_double", id_list(double.product_variant_ids))
    record(env, "pricer.tmpl_single", single.id)
    record(env, "pricer.tmpl_double", double.id)


def seed_pos_appointment(env):
    """Points of sale with one and with three appointment types."""
    types = env["appointment.type"].create(
        [
            {"name": "OUE18 tables %s" % label, "appointment_tz": "Europe/Brussels"}
            for label in ("archived", "first", "second")
        ]
    )
    types[0].active = False
    configs = env["pos.config"].create(
        [
            {"name": "OUE18 restaurant several", "module_pos_restaurant": True},
            {"name": "OUE18 restaurant one", "module_pos_restaurant": True},
        ]
    )
    configs[0].appointment_type_ids = [Command.set(types.ids)]
    configs[1].appointment_type_ids = [Command.set(types[2].ids)]
    env.flush_all()
    record(env, "posappt.config_several", configs[0].id)
    record(env, "posappt.config_one", configs[1].id)
    record(env, "posappt.expected_several", types[1].id)
    record(env, "posappt.expected_one", types[2].id)


def seed_preparation_orders(env):
    """Preparation orders with and without the take-away flag."""
    orders = env["pos_preparation_display.order"].create(
        [
            {"displayed": True, "pos_take_away": True},
            {"displayed": True, "pos_take_away": False},
        ]
    )
    record(env, "prep.takeaway", orders[0].id)
    record(env, "prep.eat_in", orders[1].id)


def sign_template(env):
    """Sign template on the 17.0 sample contract, customer and employee items."""
    from odoo.tools import file_open

    with file_open("sign/static/demo/sample_contract.pdf", "rb") as pdf:
        attachment = env["ir.attachment"].create(
            {"name": "oue18_contract.pdf", "raw": pdf.read()}
        )
    template = env["sign.template"].create(
        {"name": "OUE18 contract", "attachment_id": attachment.id}
    )
    env["sign.item"].create(
        [
            {
                "type_id": env.ref("sign.sign_item_type_text").id,
                "required": True,
                "responsible_id": env.ref("sign.%s" % role).id,
                "page": 1,
                "posX": 0.2,
                "posY": posy,
                "template_id": template.id,
                "width": 0.15,
                "height": 0.015,
            }
            for role, posy in (
                ("sign_item_role_customer", 0.1),
                ("sign_item_role_employee", 0.3),
            )
        ]
    )
    return template


def sign_request(env, template, partners, reference):
    """Sign request of the template for the partners, without sending mail."""
    roles = [
        env.ref("sign.sign_item_role_customer"),
        env.ref("sign.sign_item_role_employee"),
    ]
    return (
        env["sign.request"]
        .with_context(no_sign_mail=True)
        .create(
            {
                "template_id": template.id,
                "reference": reference,
                "request_item_ids": [
                    Command.create({"partner_id": partner.id, "role_id": role.id})
                    for partner, role in zip(partners, roles)
                ],
            }
        )
    )


def seed_sign(env):
    """Refused, canceled, open and ignored requests."""
    template = sign_template(env)
    partners = env["res.partner"].create(
        [
            {"name": "OUE18 signer %s" % n, "email": "oue18.signer%s@example.com" % n}
            for n in (1, 2)
        ]
    )
    refused = sign_request(env, template, partners, "OUE18 refused")
    refused.request_item_ids[0].write(
        {"state": "refused", "signing_date": fields.Date.today()}
    )
    refused.request_item_ids[1].write({"state": "canceled"})
    refused.write({"state": "refused"})
    canceled = sign_request(env, template, partners, "OUE18 canceled")
    canceled.cancel()
    ignored = sign_request(env, template, partners, "OUE18 ignored")
    ignored.request_item_ids[0].ignored = True
    open_request = sign_request(env, template, partners, "OUE18 open")
    env.flush_all()
    record(env, "sign.template", template.id)
    record(env, "sign.refused", refused.id)
    record(env, "sign.refused_items", id_list(refused.request_item_ids))
    record(env, "sign.refused_item", refused.request_item_ids[0].id)
    record(env, "sign.canceled", canceled.id)
    record(env, "sign.canceled_state17", canceled.state)
    record(env, "sign.ignored", ignored.id)
    record(env, "sign.ignored_item", ignored.request_item_ids[0].id)
    record(env, "sign.open", open_request.id)


def seed_rental_sign(env):
    """A rental order with a signature request and one without order."""
    template = env["sign.template"].search([("name", "=", "OUE18 contract")], limit=1)
    template = template or sign_template(env)
    signers = env["res.partner"].create(
        [
            {"name": "OUE18 renter", "email": "oue18.renter@example.com"},
            {"name": "OUE18 rental desk", "email": "oue18.desk@example.com"},
        ]
    )
    order = env["sale.order"].create(
        {"partner_id": signers[0].id, "is_rental_order": True}
    )
    linked = sign_request(env, template, signers, "OUE18 rental contract")
    linked.sale_order_id = order.id
    unlinked = sign_request(env, template, signers, "OUE18 unlinked contract")
    env.flush_all()
    record(env, "rsign.order", order.id)
    record(env, "rsign.linked", linked.id)
    record(env, "rsign.unlinked", unlinked.id)


def generic_payslip(env, name, company=None, struct=None, type_ref=None):
    """Employee, contract and draft payslip of the given company and structure."""
    company = company or env.company
    env = env(context=dict(env.context, allowed_company_ids=[company.id]))
    employee = env["hr.employee"].create({"name": name, "company_id": company.id})
    contract_values = {
        "name": "%s contract" % name,
        "employee_id": employee.id,
        "company_id": company.id,
        "wage": 4000.0,
        "date_start": "2026-01-01",
    }
    if type_ref:
        contract_values["structure_type_id"] = env.ref(type_ref).id
    contract = env["hr.contract"].create(contract_values)
    struct = (
        struct
        or contract.structure_type_id.default_struct_id
        or env.ref("hr_payroll.default_structure")
    )
    payslip = env["hr.payslip"].create(
        {
            "name": "%s payslip" % name,
            "employee_id": employee.id,
            "contract_id": contract.id,
            "company_id": company.id,
            "struct_id": struct.id,
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        }
    )
    return employee, contract, payslip


def seed_uetr(env):
    """A payslip with a SEPA UETR and one without."""
    _employee, _contract, paid = generic_payslip(env, "OUE18 UETR paid")
    _employee, _contract, unpaid = generic_payslip(env, "OUE18 UETR unpaid")
    paid.sepa_uetr = "0a2e6f62-oue1-4e18-8e18-000000000001"
    env.flush_all()
    record(env, "uetr.paid", paid.id)
    record(env, "uetr.value", paid.sepa_uetr)
    record(env, "uetr.unpaid", unpaid.id)


def seed_recruitment_extract(env):
    """Applicants of one partner in two OCR states, and one without request."""
    partner = env["res.partner"].create(
        {"name": "OUE18 applicant", "email": "oue18.applicant@example.com"}
    )
    applicants = env["hr.applicant"].create(
        [
            {
                "name": "OUE18 CV old",
                "partner_id": partner.id,
                "partner_name": partner.name,
                "email_from": partner.email,
                "extract_state": "done",
                "extract_status": "success",
                "extract_document_uuid": "oue18-cv-old",
            },
            {
                "name": "OUE18 CV new",
                "partner_id": partner.id,
                "partner_name": partner.name,
                "email_from": partner.email,
                "extract_state": "waiting_extraction",
                "extract_status": "processing",
                "extract_document_uuid": "oue18-cv-new",
            },
            {"name": "OUE18 CV none", "partner_name": "OUE18 other applicant"},
        ]
    )
    env.flush_all()
    record(env, "hrx.old", applicants[0].id)
    record(env, "hrx.new", applicants[1].id)
    record(env, "hrx.none", applicants[2].id)


def seed_lu(env):
    """Luxembourg employee, contract, an open, a closed and a computed payslip.

    The computed payslip records the 17.0 totals of the transport fees, the
    gross, taxable and net salary, against which 18.0 recomputes it; its lines
    use 17.0 rules 18.0 no longer ships (the transport fees one among them).
    """
    company = make_company(env, "OUE18 LU", "lu")
    struct = env.ref("l10n_lu_hr_payroll.hr_payroll_structure_lux_employee_salary")
    employee, contract, payslip = generic_payslip(
        env,
        "OUE18 LU employee",
        company,
        struct,
        "l10n_lu_hr_payroll.structure_type_employee_lux",
    )
    employee.write(
        {"l10n_lu_tax_card_number": "29489284", "l10n_lu_travel_expense": 206.25}
    )
    contract.l10n_lu_atn_transport = 130.0
    closed = payslip.copy({"name": "OUE18 LU closed payslip"})
    computed = payslip.copy({"name": "OUE18 LU computed payslip"})
    computed.with_context(allowed_company_ids=[company.id]).compute_sheet()
    env.flush_all()
    env.cr.execute("UPDATE hr_payslip SET state = 'done' WHERE id = %s", (closed.id,))
    totals = {line.code: line.total for line in computed.line_ids}
    record(env, "lu.company_id", company.id)
    record(env, "lu.employee", employee.id)
    record(env, "lu.contract", contract.id)
    record(env, "lu.open_payslip", payslip.id)
    record(env, "lu.closed_payslip", closed.id)
    record(env, "lu.computed_payslip", computed.id)
    for code in ("GROSS", "TRANS_FEES", "TAXABLE", "NET"):
        record(env, "lu.total17_%s" % code, totals.get(code, 0.0))
    record(env, "lu.computed_lines", len(computed.line_ids))
    record(
        env,
        "lu.trans_fees_rule",
        env.ref("l10n_lu_hr_payroll.l10n_lu_employees_transport_fees").id,
    )


def seed_au_super(env):
    """SuperStream lines with and without member account."""
    company = env.company
    fund_values = [
        {
            "display_name": "OUE18 fund %s" % label,
            "abn": "1100000000%s" % index,
            "address_id": env["res.partner"]
            .create({"name": "OUE18 fund %s" % label})
            .id,
        }
        for index, label in enumerate(("member", "other"))
    ]
    member_fund, other_fund = env["l10n_au.super.fund"].create(fund_values)
    employee, _contract, payslip = generic_payslip(env, "OUE18 AU super")
    account = env["l10n_au.super.account"].create(
        {"employee_id": employee.id, "fund_id": member_fund.id, "member_nbr": "OUE18-1"}
    )
    journal = env["account.journal"].search(
        [("company_id", "=", company.id)], limit=1
    ) or env["account.journal"].create(
        {"name": "OUE18 bank", "code": "OUEB", "type": "general"}
    )
    stream = env["l10n_au.super.stream"].create({"journal_id": journal.id})
    lines = env["l10n_au.super.stream.line"].create(
        [
            {
                "l10n_au_super_stream_id": stream.id,
                "sender_id": employee.id,
                "employee_id": employee.id,
                "payee_id": fund.id,
                "payslip_id": payslip.id,
            }
            for fund in (member_fund, other_fund, member_fund)
        ]
    )
    env.flush_all()
    env.cr.execute(
        "UPDATE l10n_au_super_stream_line SET super_account_id ="
        " CASE WHEN id = %s THEN %s END WHERE id IN %s",
        (lines[2].id, account.id, tuple(lines.ids)),
    )
    record(env, "ausuper.account", account.id)
    record(env, "ausuper.member_fund", member_fund.id)
    record(env, "ausuper.other_fund", other_fund.id)
    record(env, "ausuper.employee", employee.id)
    record(env, "ausuper.payslip_from", payslip.date_from)
    record(env, "ausuper.line_member", lines[0].id)
    record(env, "ausuper.line_other", lines[1].id)
    record(env, "ausuper.line_set", lines[2].id)


def seed_gstr(env):
    """Indian companies with every combination of the two production switches."""
    companies = {}
    for label, gstr, edi in (
        ("gstr", True, False),
        ("edi", False, True),
        ("none", False, False),
    ):
        company = make_company(env, "OUE18 IN %s" % label, "in")
        company.write(
            {
                "l10n_in_gstr_gst_production_env": gstr,
                "l10n_in_edi_production_env": edi,
            }
        )
        companies[label] = company
        record(env, "gstr.%s" % label, company.id)
    env.flush_all()


def record_refs(env, block, xmlids):
    """Record the 17.0 records behind xmlids that a script deletes or renames."""
    for xmlid in xmlids:
        res_id = env.ref(xmlid).id
        record(env, "%s.%s" % (block, xmlid), res_id)


def main_company_chart(env):
    """Main company with a chart of accounts (the generic one when it has none)."""
    company = env.ref("base.main_company")
    if not company.chart_template:
        env["account.chart.template"].try_loading(
            "generic_coa", company, install_demo=False
        )
    return company


def company_account(env, company, account_type):
    """First active account of the type in the company's chart."""
    return env["account.account"].search(
        [
            ("company_id", "=", company.id),
            ("account_type", "=", account_type),
            ("deprecated", "=", False),
        ],
        order="code",
        limit=1,
    )


def company_journal(env, company, journal_type):
    """First journal of the type in the company."""
    return env["account.journal"].search(
        [("company_id", "=", company.id), ("type", "=", journal_type)],
        order="id",
        limit=1,
    )


def seed_asset(env):
    """An asset account linked to an asset model, and one without.

    17.0 links an account to one asset model (``asset_model``); 18.0 links it
    to several (``asset_model_ids``).
    """
    company = main_company_chart(env)
    fixed = company_account(env, company, "asset_fixed")
    expense = company_account(env, company, "expense_depreciation") or (
        company_account(env, company, "expense")
    )
    journal = company_journal(env, company, "general")
    model = env["account.asset"].create(
        {
            "name": "OUE18 asset model",
            "state": "model",
            "method_number": 5,
            "method_period": "12",
            "account_asset_id": fixed.id,
            "account_depreciation_id": fixed.id,
            "account_depreciation_expense_id": expense.id,
            "journal_id": journal.id,
            "company_id": company.id,
        }
    )
    accounts = env["account.account"].create(
        [
            {
                "name": "OUE18 asset account %s" % label,
                "code": "OUE18A%s" % index,
                "account_type": "asset_fixed",
                "company_id": company.id,
                "create_asset": "draft" if label == "linked" else "no",
            }
            for index, label in enumerate(("linked", "plain"))
        ]
    )
    accounts[0].asset_model = model
    env.flush_all()
    record(env, "asset.model", model.id)
    record(env, "asset.account_linked", accounts[0].id)
    record(env, "asset.account_plain", accounts[1].id)


def seed_asset_fleet(env):
    """An asset bought on a vendor bill line of a vehicle.

    17.0 computes the vehicle of an asset from its bill lines without storing
    it; 18.0 stores it.
    """
    company = main_company_chart(env)
    brand = env["fleet.vehicle.model.brand"].create({"name": "OUE18 brand"})
    vehicle_model = env["fleet.vehicle.model"].create(
        {"name": "OUE18 van", "brand_id": brand.id}
    )
    vehicle = env["fleet.vehicle"].create(
        {
            "model_id": vehicle_model.id,
            "license_plate": "OUE-18",
            "company_id": company.id,
        }
    )
    fixed = company_account(env, company, "asset_fixed")
    expense = company_account(env, company, "expense_depreciation") or (
        company_account(env, company, "expense")
    )
    partner = env["res.partner"].create({"name": "OUE18 vehicle dealer"})
    bill = env["account.move"].create(
        {
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": "2026-01-15",
            "company_id": company.id,
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "OUE18 van",
                        "quantity": 1.0,
                        "price_unit": 24000.0,
                        "account_id": fixed.id,
                        "vehicle_id": vehicle.id,
                        "tax_ids": [Command.clear()],
                    }
                )
            ],
        }
    )
    bill.action_post()
    common = {
        "company_id": company.id,
        "account_asset_id": fixed.id,
        "account_depreciation_id": fixed.id,
        "account_depreciation_expense_id": expense.id,
        "journal_id": company_journal(env, company, "general").id,
        "method_number": 5,
        "method_period": "12",
        "acquisition_date": "2026-01-15",
        "prorata_date": "2026-01-15",
    }
    asset, plain = env["account.asset"].create(
        [
            dict(
                common,
                name="OUE18 van asset",
                original_move_line_ids=[Command.set(bill.invoice_line_ids.ids)],
            ),
            dict(common, name="OUE18 asset without vehicle", original_value=500.0),
        ]
    )
    env.flush_all()
    assert asset.vehicle_id == vehicle, "17.0 computes no vehicle for the asset"
    record(env, "fleet.asset", asset.id)
    record(env, "fleet.vehicle", vehicle.id)
    record(env, "fleet.plain", plain.id)


def seed_inter_company(env):
    """Companies that synchronize invoices and bills, and one that does not.

    17.0 has one selection ``rule_type``; 18.0 a boolean per document type.
    """
    for label, rule in (("bills", "invoice_and_refund"), ("none", "not_synchronize")):
        company = make_company(env, "OUE18 IC %s" % label, "us")
        company.rule_type = rule
        record(env, "icr.%s" % label, company.id)
    env.flush_all()


def seed_inter_company_orders(env):
    """Companies that synchronize orders, with and without automatic validation.

    17.0 has one selection ``rule_type`` and confirms generated orders when
    the company has ``auto_validation``; 18.0 has a boolean per document type
    and one ``intercompany_document_state`` that also posts generated bills.
    The last company synchronizes invoices yet carries the flag, which 17.0
    ignored there.
    """
    for label, rule, auto in (
        ("sale", "sale", True),
        ("purchase", "purchase", False),
        ("sale_purchase", "sale_purchase", True),
        ("bills_auto", "invoice_and_refund", True),
    ):
        company = make_company(env, "OUE18 IC %s" % label, "us")
        company.write({"rule_type": rule, "auto_validation": auto})
        record(env, "spicr.%s" % label, company.id)
        posted = auto and rule != "invoice_and_refund"
        record(env, "spicr.%s.state" % label, "posted" if posted else "draft")
    env.flush_all()


def seed_iso20022(env):
    """SEPA identification, LEI, pain versions, a payment UETR and a batch.

    18.0 renames the 17.0 account_sepa fields to iso20022 ones, drops three
    pain versions and adds a charge bearer on batch payments.
    """
    company = main_company_chart(env)
    company.write(
        {
            "sepa_orgid_id": "OUE18ORGID",
            "sepa_orgid_issr": "KBO-BCE",
            "sepa_initiating_party_name": "OUE18 Initiator",
        }
    )
    partner = env["res.partner"].create(
        {"name": "OUE18 LEI partner", "account_sepa_lei": "5493001KJTIIGC8Y1R12"}
    )
    journals = {}
    for index, version in enumerate(
        (
            "pain.001.001.03.se",
            "pain.001.001.03.ch.02",
            "iso_20022",
            "pain.001.001.03.de",
        )
    ):
        journal = env["account.journal"].create(
            {
                "name": "OUE18 SEPA %s" % version,
                "code": "OUS%s" % index,
                "type": "bank",
                "company_id": company.id,
            }
        )
        journal.sepa_pain_version = version
        journals[version] = journal
    bank = company_journal(env, company, "bank")
    payment = env["account.payment"].create(
        {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.id,
            "amount": 75.0,
            "journal_id": bank.id,
            "sepa_uetr": "6f1e0d9c-0e18-4e18-8e18-oue18000001",
        }
    )
    payment.action_post()
    batch = env["account.batch.payment"].create(
        {
            "journal_id": bank.id,
            "batch_type": "outbound",
            "payment_ids": [Command.set(payment.ids)],
            "sct_batch_booking": False,
        }
    )
    env.flush_all()
    record(env, "iso.company", company.id)
    record(env, "iso.partner", partner.id)
    for version, journal in journals.items():
        record(env, "iso.journal.%s" % version, journal.id)
    record(env, "iso.payment", payment.id)
    record(env, "iso.uetr", payment.sepa_uetr)
    record(env, "iso.batch", batch.id)


def seed_reports(env):
    """A report footnote and a custom report whose opening filter is a last_* key.

    18.0 turns footnotes into annotations and renames the last_* opening
    filters to previous_*.
    """
    report = env.ref("account_reports.balance_sheet")
    footnote = env["account.report.footnote"].create(
        {"report_id": report.id, "line_id": "oue18-line", "text": "OUE18 footnote"}
    )
    custom = env["account.report"].create(
        {"name": "OUE18 report", "default_opening_date_filter": "last_quarter"}
    )
    env.flush_all()
    record(env, "rep.footnote", footnote.id)
    record(env, "rep.report", report.id)
    record(env, "rep.custom", custom.id)


def seed_direct_debit(env):
    """A collected payment carrying its mandate, and one without.

    17.0 keeps the mandate on the payment's journal entry (account.payment
    inherits account.move); 18.0 on the payment itself.
    """
    company = main_company_chart(env)
    partner = env["res.partner"].create({"name": "OUE18 debtor"})
    bank_account = env["res.partner.bank"].create(
        {"partner_id": partner.id, "acc_number": "BE68539007547034"}
    )
    journal = env["account.journal"].create(
        {
            "name": "OUE18 SDD bank",
            "code": "OUSDD",
            "type": "bank",
            "company_id": company.id,
            "bank_acc_number": "BE71096123456769",
        }
    )
    mandate = env["sdd.mandate"].create(
        {
            "partner_id": partner.id,
            "partner_bank_id": bank_account.id,
            "payment_journal_id": journal.id,
            "start_date": "2026-01-01",
            "company_id": company.id,
        }
    )
    payments = env["account.payment"].create(
        [
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": partner.id,
                "amount": amount,
                "journal_id": journal.id,
            }
            for amount in (42.0, 43.0)
        ]
    )
    payments[0].sdd_mandate_id = mandate
    env.flush_all()
    env.cr.execute(
        "SELECT sdd_mandate_id FROM account_move WHERE id = %s",
        (payments[0].move_id.id,),
    )
    assert env.cr.fetchone()[0] == mandate.id, "mandate not stored on the move"
    record(env, "sdd.mandate", mandate.id)
    record(env, "sdd.payment", payments[0].id)
    record(env, "sdd.other", payments[1].id)


def seed_appointment(env):
    """Resource appointment types with and without manual confirmation.

    Also records the 17.0 onboarding records 18.0 no longer ships.
    """
    types = env["appointment.type"].create(
        [
            {
                "name": "OUE18 tables %s" % label,
                "schedule_based_on": "resources",
                "appointment_tz": "Europe/Brussels",
                "resource_manual_confirmation": manual,
                "resource_manual_confirmation_percentage": 0.5 if manual else 0.0,
            }
            for label, manual in (("manual", True), ("auto", False))
        ]
    )
    env.flush_all()
    record(env, "appt.manual", types[0].id)
    record(env, "appt.auto", types[1].id)
    record_refs(
        env,
        "appt",
        [
            "appointment.appointment_onboarding_create_appointment_type_step",
            "appointment.appointment_onboarding_preview_invite_step",
            "appointment.appointment_onboarding_configure_calendar_provider_step",
            "appointment.onboarding_onboarding_appointment",
        ],
    )


def seed_appointment_crm(env):
    """A lead an appointment created, tagged as 17.0 tags it."""
    tag = env.ref("appointment_crm.appointment_crm_tag")
    lead = env["crm.lead"].create(
        {"name": "OUE18 appointment lead", "tag_ids": [Command.set(tag.ids)]}
    )
    env.flush_all()
    record(env, "apptcrm.tag", tag.id)
    record(env, "apptcrm.lead", lead.id)


def seed_approvals(env):
    """The 17.0 approval request rules 18.0 no longer ships."""
    record_refs(
        env,
        "approvals",
        [
            "approvals.approval_request_request_owner_rule",
            "approvals.approval_request_write_request_owner_rule",
            "approvals.approval_request_approvers_rule",
        ],
    )


def seed_frontdesk(env):
    """Visitors of stations in two companies.

    18.0 stores a required company on each visitor.
    """
    company_a, company_b, _company_c = cd_companies(env)
    admin = env.ref("base.user_admin")
    stations = env["frontdesk.frontdesk"].create(
        [
            {
                "name": "OUE18 station %s" % label,
                "company_id": company.id,
                "responsible_ids": [Command.set(admin.ids)],
            }
            for label, company in (("a", company_a), ("b", company_b))
        ]
    )
    visitors = env["frontdesk.visitor"].create(
        [
            {"name": "OUE18 visitor %s" % label, "station_id": station.id}
            for label, station in zip("ab", stations)
        ]
    )
    env.flush_all()
    for label, visitor, company in zip("ab", visitors, (company_a, company_b)):
        record(env, "fd.visitor_%s" % label, visitor.id)
        record(env, "fd.company_%s" % label, company.id)


def seed_helpdesk(env):
    """The three 17.0 views of the 7-day success action 18.0 renames."""
    record_refs(
        env,
        "hd",
        [
            "helpdesk.helpdesk_ticket_action_7dayssuccess_tree",
            "helpdesk.helpdesk_ticket_action_7dayssuccess_kanban",
            "helpdesk.helpdesk_ticket_action_7dayssuccess_activity",
        ],
    )


def seed_appraisal_survey(env):
    """The appraisal survey rules 18.0 renames, and the survey rules it rewrote.

    17.0 hr_appraisal_survey rewrites the survey manager rules to leave
    appraisals out; 18.0 survey ships its own domain for them, ``noupdate``.
    """
    record_refs(
        env,
        "apsv",
        [
            "hr_appraisal_survey.survey_user_input_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_user_input_line_rule_appraisal_simple_manager",
            "hr_appraisal_survey.survey_question_rule_appraisal_simple_manager",
        ],
    )
    record_refs(
        env,
        "apsv_survey",
        [
            "survey.survey_user_input_rule_survey_manager",
            "survey.survey_user_input_line_rule_survey_manager",
        ],
    )


def seed_salary_configurator(env):
    """Benefits and benefit values with hidden descriptions and colors.

    18.0 inverts ``hide_description`` into ``always_show_description`` and
    turns the green/red value color into a selector highlight.
    """
    structure_type = env["hr.payroll.structure.type"].search([], limit=1)
    benefit_type = env["hr.contract.salary.benefit.type"].search([], limit=1)
    wage = env["ir.model.fields"]._get("hr.contract", "wage")
    benefits = env["hr.contract.salary.benefit"].create(
        [
            {
                "name": "OUE18 benefit %s" % label,
                "benefit_type_id": benefit_type.id,
                "structure_type_id": structure_type.id,
                "res_field_id": wage.id,
                "hide_description": hidden,
            }
            for label, hidden in (("hidden", True), ("shown", False))
        ]
    )
    values = env["hr.contract.salary.benefit.value"].create(
        [
            {
                "name": "OUE18 value %s" % color,
                "benefit_id": benefits[0].id,
                "value": value,
                "color": color,
                "hide_description": hidden,
            }
            for color, value, hidden in (("red", 100.0, True), ("green", 50.0, False))
        ]
    )
    env.flush_all()
    record(env, "salary.benefit_hidden", benefits[0].id)
    record(env, "salary.benefit_shown", benefits[1].id)
    record(env, "salary.value_red", values[0].id)
    record(env, "salary.value_green", values[1].id)


def seed_referral(env):
    """The 17.0 referral points rule 18.0 no longer ships."""
    record_refs(env, "ref", ["hr_referral.hr_referral_points_manager_rule"])


def seed_fsm_report(env):
    """The task report mail template and its report, moved to industry_fsm in 18.0."""
    template = env.ref("industry_fsm_report.mail_template_data_task_report")
    report = env.ref("industry_fsm_report.task_custom_report")
    assert report in template.report_template_ids, template.report_template_ids
    record(env, "fsmr.template", template.id)
    record(env, "fsmr.report", report.id)


def seed_iot_channel(env):
    """The 17.0 IoT websocket channel record and its system parameter.

    18.0 keeps the channel name in the system parameter only and has no table.
    """
    channel = env["iot.channel"].create({"name": "iot_channel-oue18"})
    name = env["iot.channel"].get_iot_channel()
    env.flush_all()
    record(env, "iotch.channel", channel.id)
    record(env, "iotch.name", name)


def seed_codabox(env):
    """Belgian companies marked connected to CodaBox, with and without token.

    18.0 computes the connection flag from the token by calling CodaBox; a
    17.0 flag left on without token is cleared so the upgrade calls nothing.
    The values are written in SQL, as a database that was connected holds
    them: through the ORM the token makes 17.0 call CodaBox as well.
    """
    for label, token in (("stale", None), ("token", "oue18-codabox-token")):
        company = make_company(env, "OUE18 BE CodaBox %s" % label, "be")
        env.flush_all()
        env.cr.execute(
            "UPDATE res_company SET l10n_be_codabox_is_connected = TRUE,"
            " l10n_be_codabox_iap_token = %s WHERE id = %s",
            (token, company.id),
        )
        record(env, "cbx.%s" % label, company.id)
    env.invalidate_all()


CH_INSURANCES = (
    ("social", "l10n.ch.social.insurance", {"institution": "048.000"}),
    (
        "accident",
        "l10n.ch.accident.insurance",
        {"customer": True, "institution": "S14"},
    ),
    (
        "additional",
        "l10n.ch.additional.accident.insurance",
        {"customer": True, "institution": "S14"},
    ),
    ("fund", "l10n.ch.compensation.fund", {"institution": "048.000"}),
    (
        "sickness",
        "l10n.ch.sickness.insurance",
        {"customer": True, "institution": "S14"},
    ),
)


def seed_ch_insurances(env):
    """One Swiss insurance of each kind, with its Swissdec institution.

    17.0 l10n_ch_hr_payroll selects the institution by its Swissdec code and
    computes the code from it; l10n_ch_hr_payroll_elm, installed with it,
    stores the institution name and code in two fields, as 18.0 does once it
    merges the two modules. The seed fills whichever shape the database has.
    """
    for label, model, options in CH_INSURANCES:
        field = env[model]._fields["insurance_company"]
        values = {"name": "OUE18 %s insurance" % label}
        code = options["institution"]
        if field.type == "selection":
            name = dict(field._description_selection(env))[code]
            values["insurance_company"] = code
        else:
            name = "OUE18 %s institution" % label
            values.update(insurance_company=name, insurance_code=code)
        if options.get("customer"):
            values.update(customer_number="OUE18-C", contract_number="OUE18-K")
        insurance = env[model].create(values)
        record(env, "ch.%s" % label, insurance.id)
        record(env, "ch.%s_code" % label, code)
        record(env, "ch.%s_name" % label, name)
        record(env, "ch.%s_shape" % label, field.type)
    env.flush_all()


def seed_ke_disabled(env):
    """Kenyan employees with and without the disability exemption.

    18.0 moves the flag to the generic ``disabled`` field of hr_payroll.
    """
    employees = env["hr.employee"].create(
        [{"name": "OUE18 KE %s" % label} for label in ("disabled", "able")]
    )
    employees[0].l10n_ke_disabled = True
    env.flush_all()
    record(env, "ke.disabled", employees[0].id)
    record(env, "ke.able", employees[1].id)


def seed_mps(env):
    """Companies planning MPS by week, by day and by month.

    17.0 has one number of columns for the company's period; 18.0 one per
    period.
    """
    companies = dict(zip("abc", cd_companies(env)))
    settings = {"a": ("week", 8), "b": ("day", 20), "c": ("month", 6)}
    for label, (period, columns) in settings.items():
        companies[label].write(
            {
                "manufacturing_period": period,
                "manufacturing_period_to_display": columns,
            }
        )
        record(env, "mps.company_%s" % label, companies[label].id)
        record(env, "mps.period_%s" % label, period)
        record(env, "mps.columns_%s" % label, columns)
    env.flush_all()


def seed_project_budget(env):
    """Budget lines carrying the demo xmlids older versions shipped.

    project_account_budget once shipped demo lines named
    ``crossovered_budget_line_0`` to ``_5``; databases that carried demo data
    still hold them, and 18.0 deletes them.
    """
    company = main_company_chart(env)
    plan = env["account.analytic.plan"].create({"name": "OUE18 demo budget plan"})
    account = env["account.analytic.account"].create(
        {"name": "OUE18 demo budget account", "plan_id": plan.id}
    )
    budget = env["crossovered.budget"].create(
        {
            "name": "OUE18 demo budget",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "company_id": company.id,
        }
    )
    lines = env["crossovered.budget.lines"].create(
        [
            {
                "crossovered_budget_id": budget.id,
                "analytic_account_id": account.id,
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "planned_amount": 100.0 * (index + 1),
            }
            for index in range(7)
        ]
    )
    for index, line in enumerate(lines[:6]):
        env["ir.model.data"].create(
            {
                "module": "project_account_budget",
                "name": "crossovered_budget_line_%s" % index,
                "model": "crossovered.budget.lines",
                "res_id": line.id,
                "noupdate": True,
            }
        )
    env.flush_all()
    record(env, "pab.demo_lines", id_list(lines[:6]))
    record(env, "pab.own_line", lines[6].id)


def seed_forecast(env):
    """Shift templates whose project is set per company.

    17.0 stores the project of a shift template per company (ir.property);
    18.0 has one project per template.
    """
    company_a, company_b, _company_c = cd_companies(env)
    projects = env["project.project"].create(
        [
            {"name": "OUE18 forecast %s" % label, "company_id": company.id}
            for label, company in (("a", company_a), ("b", company_b))
        ]
    )
    templates = env["planning.slot.template"].create(
        [{"start_time": 9.0, "duration": 4.0} for _label in "ab"]
    )
    templates[0].with_company(company_a).project_id = projects[0]
    templates[1].with_company(company_b).project_id = projects[1]
    env.flush_all()
    for label, template, project in zip("ab", templates, projects):
        record(env, "fcst.template_%s" % label, template.id)
        record(env, "fcst.project_%s" % label, project.id)


def seed_subscription(env):
    """The 17.0 payment success mail template 18.0 no longer ships."""
    record_refs(env, "sub", ["sale_subscription.email_payment_success"])


def seed_timesheet_leaderboard(env):
    """The leaderboard settings, both on as 17.0 stores them.

    17.0 keeps them as groups implied by every internal user; 18.0 as two
    booleans per company.
    """
    groups = env.ref(
        "sale_timesheet_enterprise.group_timesheet_leaderboard_show_rates"
    ) | env.ref("sale_timesheet_enterprise.group_use_timesheet_leaderboard")
    env.ref("base.group_user").implied_ids = [
        Command.link(group.id) for group in groups
    ]
    env.flush_all()
    env.cr.execute("SELECT id FROM res_company ORDER BY id")
    company_ids = [company_id for (company_id,) in env.cr.fetchall()]
    record(env, "ste.companies", ",".join(str(i) for i in company_ids))


def seed_push_notifications(env):
    """A template and a post with a message, for the push notification copy."""
    template = env["social.post.template"].create({"message": "OUE18 push template"})
    post = env["social.post"].create({"message": "OUE18 push post"})
    env.flush_all()
    record(env, "push.template", template.id)
    record(env, "push.post", post.id)


def seed_spreadsheet_revisions(env):
    """A chain of three revisions of a dashboard a user made.

    17.0 links a revision to its parent by the parent's uuid string; 18.0 by a
    many2one, and renames ``revision_id`` to ``revision_uuid``. The update
    resets the revisions of the dashboards a module ships, so the seed makes
    its own.
    """
    group = env["spreadsheet.dashboard.group"].create({"name": "OUE18 dashboards"})
    dashboard = env["spreadsheet.dashboard"].create(
        {"name": "OUE18 dashboard", "dashboard_group_id": group.id}
    )
    revisions = env["spreadsheet.revision"]
    parent = "START_REVISION"
    for index in (1, 2, 3):
        uuid = "oue18-rev-%s" % index
        revisions |= revisions.create(
            {
                "res_model": "spreadsheet.dashboard",
                "res_id": dashboard.id,
                "commands": json.dumps({"type": "REMOTE_REVISION", "commands": []}),
                "revision_id": uuid,
                "parent_revision_id": parent,
            }
        )
        parent = uuid
    env.flush_all()
    for index, revision in enumerate(revisions, 1):
        record(env, "sheet.rev_%s" % index, revision.id)


def seed_voip(env):
    """VoIP settings of 17.0 and a user who has settings.

    17.0 keeps the PBX settings in system parameters; 18.0 on a provider that
    every user's settings point at.
    """
    params = env["ir.config_parameter"].sudo()
    params.set_param("voip.wsServer", "wss://oue18.example.test:7443")
    params.set_param("voip.pbx_ip", "pbx.oue18.example.test")
    params.set_param("voip.mode", "prod")
    settings = env["res.users.settings"]._find_or_create_for_user(
        env.ref("base.user_admin")
    )
    env.flush_all()
    record(env, "voip.settings", settings.id)


def seed_studio_approval(env):
    """An approval rule of a group (17.0 requires a group with an xmlid).

    18.0 renames the rule's ``group_id`` to ``approval_group_id`` and moves
    the users to notify from the default relation to a named one.
    """
    group = env.ref("base.group_erp_manager")
    notified = env.ref("base.user_admin") | env["res.users"].create(
        {"name": "OUE18 studio notified", "login": "oue18-studio-notified"}
    )
    rule = env["studio.approval.rule"].create(
        {
            "name": "OUE18 approval",
            "model_id": env["ir.model"]._get("res.partner").id,
            "method": "action_archive",
            "group_id": group.id,
            "users_to_notify": [Command.set(notified.ids)],
        }
    )
    env.flush_all()
    env.cr.execute(
        "SELECT res_users_id FROM res_users_studio_approval_rule_rel"
        " WHERE studio_approval_rule_id = %s ORDER BY res_users_id",
        (rule.id,),
    )
    stored = [user_id for (user_id,) in env.cr.fetchall()]
    assert stored == sorted(notified.ids), stored
    record(env, "studio.rule", rule.id)
    record(env, "studio.group", group.id)
    record(env, "studio.notified", ",".join(str(i) for i in stored))


def seed_sale_dashboard(env):
    """The 17.0 eCommerce dashboard onboarding 18.0 no longer ships."""
    record_refs(
        env,
        "wsd",
        [
            "website_sale_dashboard.onboarding_onboarding_step_payment_provider",
            "website_sale_dashboard.onboarding_onboarding_website_sale_dashboard",
        ],
    )


def seed_rental_website(env):
    """The websites that exist before 18.0 gives each a required timezone."""
    env.cr.execute("SELECT id FROM website ORDER BY id")
    website_ids = [website_id for (website_id,) in env.cr.fetchall()]
    record(env, "wsr.websites", ",".join(str(i) for i in website_ids))


def seed_whatsapp(env):
    """A WhatsApp conversation opened from a record message.

    17.0 keeps the record message the conversation came from and computes
    the 24-hour reply window from the customer's last message; 18.0 stores
    that last customer message instead.
    """
    customer = env["res.partner"].create(
        {"name": "OUE18 WhatsApp customer", "phone": "+32 470 18 18 18"}
    )
    origin = env["mail.message"].create(
        {
            "model": "res.partner",
            "res_id": customer.id,
            "body": "OUE18 template sent",
            "message_type": "comment",
        }
    )
    channel = env["discuss.channel"].create(
        {
            "name": "OUE18 WhatsApp",
            "channel_type": "whatsapp",
            "whatsapp_number": "32470181818",
            "whatsapp_partner_id": customer.id,
            "whatsapp_mail_message_id": origin.id,
        }
    )
    messages = env["mail.message"].create(
        [
            {
                "model": "discuss.channel",
                "res_id": channel.id,
                "author_id": author.id,
                "body": body,
                "message_type": "whatsapp_message",
            }
            for author, body in (
                (customer, "OUE18 first answer"),
                (customer, "OUE18 last answer"),
                (env.ref("base.partner_admin"), "OUE18 reply"),
            )
        ]
    )
    env.flush_all()
    record(env, "wa.channel", channel.id)
    record(env, "wa.origin", origin.id)
    record(env, "wa.last_customer", messages[1].id)


def seed_twitter(env):
    """The 17.0 name of the X (Twitter) media, which 18.0 renames."""
    media = env.ref("social_twitter.social_media_twitter")
    record(env, "twitter.media", media.id)
    record(env, "twitter.name17", media.name)


def seed_be_fiscal_voluntarism(env):
    """A Belgian contract with a voluntary withholding rate.

    18.0 moves the rate from the contract to the employee.
    """
    employee = env["hr.employee"].create({"name": "OUE18 BE voluntary"})
    contract = env["hr.contract"].create(
        {
            "name": "OUE18 BE voluntary contract",
            "employee_id": employee.id,
            "wage": 3000.0,
            "date_start": "2026-01-01",
            "fiscal_voluntarism": True,
            "fiscal_voluntary_rate": 33.5,
        }
    )
    contract.state = "open"
    env.flush_all()
    record(env, "befv.employee", employee.id)
    record(env, "befv.rate", 33.5)


def seed_twitter_wall(env):
    """An event that showcases a Twitter wall in its website menu.

    17.0 adds a 'social' entry to the event menu types; 18.0 has neither the
    wall nor that menu type.
    """
    wall = env["website.twitter.wall"].create({"name": "OUE18 wall"})
    event = env["event.event"].create(
        {
            "name": "OUE18 event with wall",
            "date_begin": "2026-03-02 08:00:00",
            "date_end": "2026-03-02 17:00:00",
            "website_menu": True,
            "twitter_wall_id": wall.id,
        }
    )
    env.flush_all()
    social = env["website.event.menu"].search(
        [("event_id", "=", event.id), ("menu_type", "=", "social")]
    )
    assert event.social_menu and len(social) == 1, (event.social_menu, social)
    others = env["website.event.menu"].search(
        [("event_id", "=", event.id), ("menu_type", "!=", "social")]
    )
    record(env, "tww.wall", wall.id)
    record(env, "tww.event", event.id)
    record(env, "tww.social_menu", social.id)
    record(env, "tww.website_menu", social.menu_id.id)
    record(env, "tww.other_menus", ",".join(str(i) for i in sorted(others.ids)))


EBAY_CRONS = ["ir_cron_sale_ebay_orders_sync", "ir_cron_sale_ebay_stock_sync"]

REMOVED = [
    ("account_consolidation", "account_reports", [], []),
    ("account_taxcloud", "l10n_us", ["account_fiscal_position_taxcloud_us"], []),
    ("sale_account_taxcloud", "sale", [], []),
    ("sale_amazon_taxcloud", "sale_amazon", [], []),
    ("sale_loyalty_taxcloud", "sale_loyalty", [], []),
    ("sale_loyalty_taxcloud_delivery", "sale_loyalty_delivery", [], []),
    ("sale_subscription_taxcloud", "sale_subscription", [], []),
    ("website_sale_account_taxcloud", "website_sale", [], []),
    (
        "sale_ebay",
        "sale_management",
        [
            "product_category_ebay",
            "ebay_GDPR_notification",
            "ebay_last_sync_param",
            "crm_rule_all_salesteam",
            "ir_cron_sale_ebay_orders_recovery",
        ]
        + EBAY_CRONS,
        EBAY_CRONS,
    ),
    ("l10n_account_customer_statements", "account_reports", [], []),
    ("l10n_uk_customer_statements", "l10n_uk", [], []),
    ("l10n_be_us_consolidation_demo", "account_reports", [], []),
    ("l10n_dk_edi", "l10n_dk", [], []),
    (
        "l10n_fr_reports_extended",
        "l10n_fr_reports",
        [
            "model_l10n_fr_reports_send_vat_report_bank_account_line",
            "access_l10n_fr_reports_send_vat_report_bank_account_line",
        ],
        [],
    ),
    ("mrp_subcontracting_studio", "mrp_subcontracting", [], []),
    ("website_twitter", "website", [], []),
    ("website_twitter_wall", "website", [], []),
    ("website_event_twitter_wall", "website_event", [], []),
]


REMOVED_GONE = {
    "account_consolidation": ["company_consolidation_rule", "group_consolidation_user"],
}


def restore_taxcloud_position(env):
    """Load the TaxCloud fiscal position again where a chart load deleted it.

    17.0 deletes the fiscal positions of a company that gets its first chart
    after the module is installed, which is the order of a batch install; a
    database that had its chart first keeps the ``noupdate`` record.
    """
    if not env.ref(
        "account_taxcloud.account_fiscal_position_taxcloud_us",
        raise_if_not_found=False,
    ):
        convert_file(
            env,
            "account_taxcloud",
            "data/account_taxcloud_data.xml",
            {},
            mode="init",
            noupdate=True,
            kind="data",
        )


def seed_removed(env, module, target, keep, crons):
    """A 17.0 module 18.0 removed or folded into another one.

    The base pre-migration merges it into ``target``: its row and its
    ``base.module_*`` xmlid go, its xmlids move to the target, the update
    deletes its updatable data, the records in ``keep`` (``noupdate`` data,
    or data the target ships in 18.0) keep their ids under the target, its
    scheduled actions in ``crons`` are archived, and the groups in
    ``REMOVED_GONE`` go with the rules that only served them.
    """
    if module == "account_taxcloud":
        restore_taxcloud_position(env)
    record(env, "rm", "seeded")
    record(env, "rm.%s" % module, target)
    for name in keep:
        res_id = env.ref("%s.%s" % (module, name)).id
        record(env, "rmkeep.%s.%s" % (module, name), res_id)
    for name in crons:
        cron = env.ref("%s.%s" % (module, name))
        assert cron.active, name
        record(env, "rmcron.%s.%s" % (module, name), cron.id)
    for name in REMOVED_GONE.get(module, []):
        gone = env.ref("%s.%s" % (module, name))
        record(env, "rmgone.%s.%s" % (module, name), "%s,%s" % (gone._name, gone.id))


def main(env):
    """Run every block whose module is installed, then commit."""
    env.cr.execute(
        "CREATE TABLE IF NOT EXISTS oue18_seed (k varchar PRIMARY KEY, v text)"
    )
    blocks = [
        ("mx", "l10n_mx_edi", seed_mx),
        (
            "ec",
            "l10n_ec_edi",
            lambda e: seed_company_certificate(
                e,
                "ec",
                "ec",
                "ec",
                "l10n_ec_edi.certificate",
                "l10n_ec_edi_certificate_id",
                {"file_name": "oue18-ec.p12"},
            ),
        ),
        (
            "pe",
            "l10n_pe_edi",
            lambda e: seed_company_certificate(
                e,
                "pe",
                "pe",
                "pe",
                "l10n_pe_edi.certificate",
                "l10n_pe_edi_certificate_id",
                {},
            ),
        ),
        ("cl", "l10n_cl_edi", seed_cl),
        ("ar", "l10n_ar_edi", seed_ar),
        ("nl", "l10n_nl_reports_sbr", seed_nl),
        ("be", "l10n_be_hr_payroll", seed_be),
        ("plm", "mrp_plm", seed_plm),
        ("ec_cd", "l10n_ec_edi", seed_ec_cd),
        ("fu", "account_followup", seed_cd_followup),
        ("pay", "hr_payroll_account", seed_cd_payroll),
        ("fsm", "industry_fsm_sale_report", seed_cd_fsm),
        ("rent", "sale_renting", seed_cd_rental),
        ("srent", "sale_stock_renting", seed_cd_stock_rental),
        ("sla", "helpdesk_sale_timesheet", seed_cd_sla),
        ("de", "l10n_de_reports", seed_de),
        ("social", "social", seed_social),
        ("wks", "worksheet", seed_worksheet),
        ("acct", "account_accountant", seed_accountant),
        ("plan", "planning", seed_planning),
        ("bud", "account_budget", seed_budget),
        ("doc", "documents", seed_documents),
        ("appr", "hr_appraisal", seed_appraisal),
        ("au", "l10n_au_hr_payroll", seed_au),
        ("dlv", "delivery", seed_delivery),
        ("mxs", "l10n_mx_edi_stock_extended_30", seed_mx_stock, "l10n_mx_edi_stock"),
        ("brs", "l10n_br_avatax_services", seed_br_services, "l10n_br_avatax"),
        ("riba", "l10n_it_riba", seed_riba),
        ("dash", "spreadsheet_dashboard_purchase_stock", seed_dashboards),
        ("kp", "l10n_au_keypay", seed_keypay, "l10n_employment_hero"),
        ("iot", "mrp_workorder_iot", seed_iot_triggers),
        ("pricer", "pos_pricer", seed_pricer),
        ("posappt", "pos_restaurant_appointment", seed_pos_appointment),
        ("prep", "pos_self_order_preparation_display", seed_preparation_orders),
        ("sign", "sign", seed_sign),
        ("rsign", "sale_renting_sign", seed_rental_sign),
        ("uetr", "hr_payroll_account_sepa", seed_uetr, "hr_payroll_account_iso20022"),
        ("hrx", "hr_recruitment_extract", seed_recruitment_extract),
        ("lu", "l10n_lu_hr_payroll", seed_lu),
        ("ausuper", "l10n_au_hr_payroll_account", seed_au_super),
        ("gstr", "l10n_in_reports_gstr", seed_gstr),
        ("asset", "account_asset", seed_asset),
        ("fleet", "account_asset_fleet", seed_asset_fleet),
        ("icr", "account_inter_company_rules", seed_inter_company),
        ("spicr", "sale_purchase_inter_company_rules", seed_inter_company_orders),
        ("iso", "account_sepa", seed_iso20022, "account_iso20022"),
        ("rep", "account_reports", seed_reports),
        ("sdd", "account_sepa_direct_debit", seed_direct_debit),
        ("appt", "appointment", seed_appointment),
        ("apptcrm", "appointment_crm", seed_appointment_crm),
        ("approvals", "approvals", seed_approvals),
        ("fd", "frontdesk", seed_frontdesk),
        ("hd", "helpdesk", seed_helpdesk),
        ("apsv", "hr_appraisal_survey", seed_appraisal_survey),
        ("salary", "hr_contract_salary", seed_salary_configurator),
        ("ref", "hr_referral", seed_referral),
        ("fsmr", "industry_fsm_report", seed_fsm_report),
        ("iotch", "iot", seed_iot_channel),
        ("cbx", "l10n_be_codabox", seed_codabox),
        ("ch", "l10n_ch_hr_payroll", seed_ch_insurances),
        ("ke", "l10n_ke_hr_payroll", seed_ke_disabled),
        ("befv", "l10n_be_hr_payroll", seed_be_fiscal_voluntarism),
        ("mps", "mrp_mps", seed_mps),
        ("pab", "project_account_budget", seed_project_budget),
        ("fcst", "project_forecast", seed_forecast),
        ("sub", "sale_subscription", seed_subscription),
        ("ste", "sale_timesheet_enterprise", seed_timesheet_leaderboard),
        ("push", "social_push_notifications", seed_push_notifications),
        ("twitter", "social_twitter", seed_twitter),
        ("sheet", "spreadsheet_edition", seed_spreadsheet_revisions),
        ("voip", "voip", seed_voip),
        ("studio", "web_studio", seed_studio_approval),
        ("wsd", "website_sale_dashboard", seed_sale_dashboard),
        ("wsr", "website_sale_renting", seed_rental_website),
        ("wa", "whatsapp", seed_whatsapp),
        ("tww", "website_event_twitter_wall", seed_twitter_wall, "website_event"),
    ]
    blocks += [
        (
            "rm_%s" % module,
            module,
            lambda e, m=module, t=target, k=keep, c=crons: seed_removed(e, m, t, k, c),
            target,
        )
        for module, target, keep, crons in REMOVED
    ]
    blocks.append(("payin", "hr_payroll", seed_payroll_inputs))
    for block, module, function, *module18 in blocks:
        if not installed(env, module):
            print("SKIPPED %s (%s not installed)" % (block, module))
            continue
        if done(env, block):
            print("SKIPPED %s (already seeded)" % block)
            continue
        function(env)
        record(env, "block.%s" % block, module18[0] if module18 else module)
    env.cr.commit()
    print("SEED_PY_OK")


main(globals()["env"])
