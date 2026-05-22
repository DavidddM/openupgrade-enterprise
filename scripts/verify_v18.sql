-- =============================================================================
-- OpenUpgrade Enterprise E2E checks on the upgraded 18.0 database.
--
-- Run by scripts/run_e2e_test.sh as VERIFY_SQL after the upgrade. The data
-- comes from scripts/seed_v17.py, which ran on 17.0 and left the ids and the
-- expected values in the table oue18_seed (k, v).
--
-- Output contract: one row per check
--   <n> PASS|FAIL|SKIP <code> <description> | <actual value>
-- then "SUMMARY passed=<n> | failed=<n> | skipped=<n>"; the last block raises
-- when a check failed, so psql exits non-zero.
--
-- A check is pg_temp.check(code, description, needs, query). The query returns
-- one row (ok boolean, actual text): PASS when ok is true; FAIL when ok is false
-- or NULL, when it returns no row or when it raises. needs lists what the check
-- reads: mod:<module> (installed on 18.0; mod:a|b for any of them), seed:<key>
-- (written by the seed, block.<name> when its block ran), tbl:<table>,
-- col:<table>.<column>. Every check names at least one mod: need, the module
-- whose migration it proves; an unmet need gives SKIP, so a check never passes
-- for a module the database does not have.
-- =============================================================================

\set ON_ERROR_STOP 1
\set QUIET 1
\pset pager off
\pset tuples_only on
\pset format unaligned

CREATE TEMP TABLE oue_result (seq serial, code text, name text, result text, actual text);

CREATE FUNCTION pg_temp.s(key text) RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE
    val text;
BEGIN
    IF to_regclass('oue18_seed') IS NULL THEN
        RETURN NULL;
    END IF;
    EXECUTE 'SELECT v FROM oue18_seed WHERE k = $1' INTO val USING key;
    RETURN val;
END $$;

CREATE FUNCTION pg_temp.si(key text) RETURNS integer LANGUAGE sql STABLE AS $$
    SELECT pg_temp.s(key)::integer
$$;

CREATE FUNCTION pg_temp.installed(p_names text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM ir_module_module
        WHERE name = ANY(string_to_array(p_names, '|')) AND state = 'installed')
$$;

CREATE FUNCTION pg_temp.check(p_code text, p_name text, p_requires text[], p_query text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    token text;
    kind text;
    arg text;
    unmet text[] := '{}';
    guarded boolean := false;
    ok boolean;
    actual text;
    rows integer;
BEGIN
    FOREACH token IN ARRAY coalesce(p_requires, '{}'::text[]) LOOP
        kind := split_part(token, ':', 1);
        arg := substr(token, length(kind) + 2);
        guarded := guarded OR kind = 'mod';
        IF (kind = 'seed' AND pg_temp.s(arg) IS NULL)
            OR (kind = 'mod' AND NOT pg_temp.installed(arg))
            OR (kind = 'tbl' AND to_regclass(arg) IS NULL)
            OR (kind = 'col' AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = split_part(arg, '.', 1)
                    AND column_name = split_part(arg, '.', 2))) THEN
            unmet := unmet || token;
        END IF;
    END LOOP;
    IF NOT guarded THEN
        INSERT INTO oue_result (code, name, result, actual) VALUES (p_code, p_name, 'FAIL', 'check names no module');
        RETURN;
    END IF;
    IF cardinality(unmet) > 0 THEN
        INSERT INTO oue_result (code, name, result, actual)
        VALUES (p_code, p_name, 'SKIP', 'needs ' || array_to_string(unmet, ', '));
        RETURN;
    END IF;
    BEGIN
        EXECUTE p_query INTO ok, actual;
        GET DIAGNOSTICS rows = ROW_COUNT;
    EXCEPTION WHEN others THEN
        INSERT INTO oue_result (code, name, result, actual) VALUES (p_code, p_name, 'FAIL', 'error: ' || SQLERRM);
        RETURN;
    END;
    IF rows = 0 THEN
        INSERT INTO oue_result (code, name, result, actual) VALUES (p_code, p_name, 'FAIL', 'no row');
        RETURN;
    END IF;
    INSERT INTO oue_result (code, name, result, actual)
    VALUES (p_code, p_name, CASE WHEN coalesce(ok, false) THEN 'PASS' ELSE 'FAIL' END, coalesce(actual, 'NULL'));
END $$;

-- Target table of the foreign key on p_table.p_column.
CREATE FUNCTION pg_temp.fk_target(p_table text, p_column text) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT string_agg(c.confrelid::regclass::text, ',' ORDER BY c.conname)
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.conrelid = to_regclass(p_table) AND a.attname = p_column
$$;

-- Checksum of the one non-empty attachment of a binary field, or what is wrong.
CREATE FUNCTION pg_temp.att_sha1(p_model text, p_field text, p_id integer) RETURNS text LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN count(*) = 1 AND min(file_size) > 0 THEN min(checksum)
        ELSE format('%s attachment(s), size %s', count(*), coalesce(min(file_size), 0)) END
    FROM ir_attachment WHERE res_model = p_model AND res_field = p_field AND res_id = p_id
$$;

-- The 18.0 record the certificate step made from a 17.0 binary field (NULL if none).
CREATE FUNCTION pg_temp.mapped(p_model text, p_field text, p_id integer) RETURNS integer LANGUAGE plpgsql STABLE AS $$
DECLARE
    target integer;
BEGIN
    IF to_regclass('openupgrade_legacy_18_0_certificate_map') IS NULL THEN
        RETURN NULL;
    END IF;
    EXECUTE 'SELECT target_id FROM openupgrade_legacy_18_0_certificate_map
        WHERE source_model = $1 AND source_field = $2 AND source_id = $3'
        INTO target USING p_model, p_field, p_id;
    RETURN target;
END $$;

-- Every stored compute of a certificate.certificate against the seeded certificate <p>:
-- content and PEM attachments, format, serial, subject CN, validity dates, no loading
-- error, company, active.
CREATE FUNCTION pg_temp.cert_check(p text, p_cert integer, p_format text) RETURNS TABLE (ok boolean, actual text)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT c.id IS NOT NULL AND c.active
            AND pg_temp.att_sha1('certificate.certificate', 'content', c.id) = pg_temp.s(p || '.content_sha1')
            AND pg_temp.att_sha1('certificate.certificate', 'pem_certificate', c.id) = pg_temp.s(p || '.pem_sha1')
            AND c.content_format = p_format
            AND c.serial_number = pg_temp.s(p || '.cert_serial')
            AND c.subject_common_name = pg_temp.s(p || '.cert_cn')
            AND c.date_start = pg_temp.s(p || '.cert_not_before')::timestamp
            AND c.date_end = pg_temp.s(p || '.cert_not_after')::timestamp
            AND coalesce(c.loading_error, '') = ''
            AND c.company_id = pg_temp.si(p || '.company_id'),
        format('certificate=%s company=%s format=%s serial_ok=%s cn=%s dates=%s..%s content_ok=%s pem_ok=%s error=%s active=%s',
            c.id, c.company_id, c.content_format, c.serial_number = pg_temp.s(p || '.cert_serial'), c.subject_common_name,
            c.date_start, c.date_end,
            pg_temp.att_sha1('certificate.certificate', 'content', c.id) = pg_temp.s(p || '.content_sha1'),
            pg_temp.att_sha1('certificate.certificate', 'pem_certificate', c.id) = pg_temp.s(p || '.pem_sha1'),
            coalesce(c.loading_error, 'NULL'), c.active)
    FROM (SELECT p_cert AS id) x LEFT JOIN certificate_certificate c ON c.id = x.id;
END $$;

-- A certificate.key against the seeded private key <p>: private, loaded (pem_key is the
-- SHA-1 of the seeded key's unencrypted PKCS#8 PEM), content kept, no loading error, company.
CREATE FUNCTION pg_temp.key_check(p text, p_key integer) RETURNS TABLE (ok boolean, actual text)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT k.id IS NOT NULL AND k.public IS FALSE AND coalesce(k.loading_error, '') = ''
            AND pg_temp.att_sha1('certificate.key', 'pem_key', k.id) = pg_temp.s(p || '.key_pem_sha1')
            AND pg_temp.att_sha1('certificate.key', 'content', k.id) NOT LIKE '%attachment(s)%'
            AND k.company_id = pg_temp.si(p || '.company_id'),
        format('key=%s company=%s public=%s pem_key_ok=%s password_set=%s error=%s', k.id, k.company_id, k.public,
            pg_temp.att_sha1('certificate.key', 'pem_key', k.id) = pg_temp.s(p || '.key_pem_sha1'),
            k.password IS NOT NULL, coalesce(k.loading_error, 'NULL'))
    FROM (SELECT p_key AS id) x LEFT JOIN certificate_key k ON k.id = x.id;
END $$;

-- 17.0 records a script deletes: the xmlids <block>.<module>.<name> the seed recorded with
-- their record id. None may keep an ir_model_data row, nor a record in p_table unless
-- p_table is NULL (the xmlid alone goes).
CREATE FUNCTION pg_temp.gone(p_block text, p_table text) RETURNS TABLE (ok boolean, actual text)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY EXECUTE format($f$
        SELECT count(*) > 0 AND count(*) FILTER (WHERE d.id IS NOT NULL OR t.id IS NOT NULL) = 0,
            format('17.0 records=%%s xmlids left=%%s records left=%%s', count(*),
                coalesce(string_agg(x.xmlid, ',') FILTER (WHERE d.id IS NOT NULL), 'none'),
                coalesce(string_agg(x.res_id::text, ',') FILTER (WHERE t.id IS NOT NULL), 'none'))
        FROM (SELECT substr(k, length(%L) + 2) AS xmlid, v::integer AS res_id FROM oue18_seed
              WHERE k LIKE %L) x
        LEFT JOIN ir_model_data d ON d.module = split_part(x.xmlid, '.', 1) AND d.name = split_part(x.xmlid, '.', 2)
        LEFT JOIN (SELECT %s AS id FROM %s) t ON t.id = x.res_id
    $f$, p_block, p_block || '.%.%',
        CASE WHEN p_table IS NULL THEN 'NULL::integer' ELSE 'id' END,
        CASE WHEN p_table IS NULL THEN '(SELECT 1) z' ELSE quote_ident(p_table) END);
END $$;

-- The English value of a translated column, or the value of a plain one.
CREATE FUNCTION pg_temp.en(p_value text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN left(p_value, 1) = '{' THEN p_value::jsonb ->> 'en_US' ELSE p_value END
$$;

-- Company-dependent fields: 17.0 ir_property values of p_model.p_field whose company key is
-- missing from the 18.0 jsonb column (NULL when the column or ir_property is absent).
CREATE FUNCTION pg_temp.cd_missing(p_model text, p_field text) RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    tbl text := replace(p_model, '.', '_');
    missing integer;
BEGIN
    IF to_regclass('ir_property') IS NULL OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = tbl AND column_name = p_field AND data_type = 'jsonb'
    ) THEN
        RETURN NULL;
    END IF;
    EXECUTE format($f$
        SELECT count(*) FROM ir_property p
        JOIN ir_model_fields f ON f.id = p.fields_id AND f.model = %L AND f.name = %L
        JOIN %I t ON t.id = split_part(p.res_id, ',', 2)::integer
        WHERE p.res_id LIKE %L AND p.company_id IS NOT NULL AND NOT coalesce(t.%I ? p.company_id::text, false)
    $f$, p_model, p_field, tbl, p_model || ',%', p_field) INTO missing;
    RETURN missing;
END $$;

-- The value of a company-dependent jsonb column for one company (the key is the company id).
CREATE FUNCTION pg_temp.cv(p_value jsonb, p_company text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT p_value ->> p_company
$$;

-- Ids of a many2many relation for one record, as a sorted comma list.
CREATE FUNCTION pg_temp.rel_ids(p_table text, p_column text, p_other text, p_id integer) RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE
    val text;
BEGIN
    IF to_regclass(p_table) IS NULL THEN
        RETURN 'no table ' || p_table;
    END IF;
    EXECUTE format('SELECT coalesce(string_agg(%I::text, '','' ORDER BY %I), '''') FROM %I WHERE %I = $1',
        p_other, p_other, p_table, p_column) INTO val USING p_id;
    RETURN val;
END $$;

-- The 18.0 folder document made from a 17.0 documents.folder id (NULL when none).
CREATE FUNCTION pg_temp.folder_doc(p_key text) RETURNS integer LANGUAGE plpgsql STABLE AS $$
DECLARE
    val integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'documents_document' AND column_name = '_ou_from_folder_id') THEN
        RETURN NULL;
    END IF;
    EXECUTE 'SELECT id FROM documents_document WHERE _ou_from_folder_id = $1' INTO val USING pg_temp.si(p_key);
    RETURN val;
END $$;

-- documents.access rows of a document as "<partner>:<role>" sorted by partner ('' when none).
CREATE FUNCTION pg_temp.doc_access(p_document integer) RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE
    val text;
BEGIN
    EXECUTE 'SELECT coalesce(string_agg(partner_id || '':'' || coalesce(role, ''-''), '','' ORDER BY partner_id), '''')
        FROM documents_access WHERE document_id = $1' INTO val USING p_document;
    RETURN val;
END $$;

-- The rows the 17.0 write group (edit) and read group (view) give on a restricted document.
CREATE FUNCTION pg_temp.doc_groups_access() RETURNS text LANGUAGE sql STABLE AS $$
    SELECT string_agg(r, ',' ORDER BY p) FROM (VALUES
        (pg_temp.si('doc.partner_writer'), pg_temp.s('doc.partner_writer') || ':edit'),
        (pg_temp.si('doc.partner_reader'), pg_temp.s('doc.partner_reader') || ':view')) x(p, r)
$$;

-- Whether the record p_model,p_id exists in the model's table.
CREATE FUNCTION pg_temp.row_exists(p_model text, p_id integer) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE
    tbl text := CASE p_model WHEN 'ir.actions.server' THEN 'ir_act_server' ELSE replace(p_model, '.', '_') END;
    found boolean;
BEGIN
    IF p_id IS NULL OR to_regclass(tbl) IS NULL THEN
        RETURN false;
    END IF;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', tbl) INTO found USING p_id;
    RETURN found;
END $$;

\o /dev/null

-- Base and module map -----------------------------------------------------------------------------

SELECT pg_temp.check('G1', 'base is on 18.0', ARRAY['mod:base'], $q$
    SELECT latest_version LIKE '18.0.%', latest_version FROM ir_module_module WHERE name = 'base'
$q$);
SELECT pg_temp.check('G2', 'no module in an inconsistent state', ARRAY['mod:base'], $q$
    SELECT count(*) = 0, format('modules=%s %s', count(*), coalesce(string_agg(name || ':' || state, ','), ''))
    FROM ir_module_module WHERE state NOT IN ('installed', 'uninstalled', 'uninstallable')
$q$);
SELECT pg_temp.check('G3', 'the module of every seeded block is installed on 18.0 under its 18.0 name', ARRAY['mod:base', 'tbl:oue18_seed'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE m.state IS DISTINCT FROM 'installed') = 0,
        string_agg(s.v || ':' || coalesce(m.state, 'missing'), ',' ORDER BY s.v)
    FROM oue18_seed s LEFT JOIN ir_module_module m ON m.name = s.v
    WHERE s.k LIKE 'block.%'
$q$);
SELECT pg_temp.check('MAP1', 'no module row is left for a 17.0 module 18.0 renamed or merged', ARRAY['mod:base'], $q$
    SELECT count(*) = 0, format('rows=%s %s', count(*), coalesce(string_agg(name || ':' || state, ',' ORDER BY name), ''))
    FROM ir_module_module
    WHERE name IN ('account_sepa', 'hr_payroll_account_sepa', 'account_bacs', 'l10n_au_keypay', 'data_merge',
        'l10n_ch_hr_payroll_elm', 'stock_account_enterprise', 'account_consolidation', 'account_reports_tax_reminder',
        'documents_spreadsheet_account', 'documents_spreadsheet_crm', 'website_sale_renting_product_configurator',
        'l10n_be_codabox_bridge', 'l10n_be_codabox_bridge_wizard', 'l10n_cl_edi_boletas', 'l10n_mx_edi_stock_30',
        'l10n_mx_edi_stock_extended', 'l10n_mx_edi_stock_extended_30', 'l10n_mx_edi_stock_extended_31',
        'l10n_br_avatax_services', 'l10n_br_edi_services', 'l10n_br_edi_sale_services', 'spreadsheet_dashboard_purchase',
        'l10n_in_reports_debit_note', 'l10n_fr_reports_extended', 'account_taxcloud', 'sale_account_taxcloud',
        'sale_amazon_taxcloud', 'sale_loyalty_taxcloud', 'sale_loyalty_taxcloud_delivery', 'sale_subscription_taxcloud',
        'website_sale_account_taxcloud', 'sale_ebay', 'l10n_account_customer_statements', 'l10n_uk_customer_statements',
        'l10n_be_us_consolidation_demo', 'l10n_dk_edi', 'mrp_subcontracting_studio', 'website_twitter',
        'website_twitter_wall', 'website_event_twitter_wall')
$q$);
SELECT pg_temp.check('MAP2', 'l10n_it_riba and the purchase stock dashboard keep one row under their 17.0 name, no OpenUpgrade _oca rename', ARRAY['mod:base'], $q$
    SELECT count(*) FILTER (WHERE name LIKE '%\_oca') = 0
            AND count(*) FILTER (WHERE name = 'l10n_it_riba') = 1
            AND count(*) FILTER (WHERE name = 'spreadsheet_dashboard_purchase_stock') = 1,
        coalesce(string_agg(name || ':' || state, ',' ORDER BY name), 'no row')
    FROM ir_module_module
    WHERE name IN ('l10n_it_riba', 'l10n_it_riba_oca', 'spreadsheet_dashboard_purchase_stock',
        'spreadsheet_dashboard_purchase_oca', 'spreadsheet_dashboard_purchase_stock_oca')
$q$);
SELECT pg_temp.check('MAP3', 'no _oca module of OpenUpgrade is installed or pending', ARRAY['mod:base'], $q$
    SELECT count(*) = 0, format('rows=%s %s', count(*), coalesce(string_agg(o.name || ':' || o.state, ','), ''))
    FROM ir_module_module o
    WHERE o.name LIKE '%\_oca' AND o.state NOT IN ('uninstalled', 'uninstallable')
$q$);
SELECT pg_temp.check('RMV1', 'base: every removed or folded module installed on 17.0 is merged: no row, no xmlid under its name, its target installed', ARRAY['mod:base', 'seed:rm'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE m.id IS NOT NULL OR d.n > 0 OR b.id IS NOT NULL
                OR t.state IS DISTINCT FROM 'installed') = 0,
        format('modules=%s left=%s', count(*), coalesce(string_agg(format('%s:row=%s,xmlids=%s,base=%s,%s=%s', x.name,
                m.state, d.n, b.id, x.target, t.state), ' ') FILTER (WHERE m.id IS NOT NULL OR d.n > 0 OR b.id IS NOT NULL
                OR t.state IS DISTINCT FROM 'installed'), 'none'))
    FROM (SELECT substr(k, 4) AS name, v AS target FROM oue18_seed WHERE k LIKE 'rm.%') x
    LEFT JOIN ir_module_module m ON m.name = x.name
    LEFT JOIN ir_module_module t ON t.name = x.target
    LEFT JOIN LATERAL (SELECT count(*) AS n FROM ir_model_data WHERE module = x.name) d ON TRUE
    LEFT JOIN ir_model_data b ON b.module = 'base' AND b.model = 'ir.module.module' AND b.name = 'module_' || x.name
$q$);
SELECT pg_temp.check('RMV2', 'base: the records a removed or folded module leaves to its target keep their 17.0 ids under the target', ARRAY['mod:base', 'seed:rm'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE d.res_id IS DISTINCT FROM x.res_id OR NOT pg_temp.row_exists(d.model, d.res_id)) = 0,
        format('records=%s wrong=%s', count(*), coalesce(string_agg(format('%s.%s=%s (17.0 %s)', x.target, x.name, d.res_id, x.res_id), ' ')
            FILTER (WHERE d.res_id IS DISTINCT FROM x.res_id OR NOT pg_temp.row_exists(d.model, d.res_id)), 'none'))
    FROM (SELECT split_part(k, '.', 3) AS name, v::integer AS res_id,
            (SELECT v FROM oue18_seed WHERE k = 'rm.' || split_part(s.k, '.', 2)) AS target
          FROM oue18_seed s WHERE k LIKE 'rmkeep.%') x
    LEFT JOIN ir_model_data d ON d.module = x.target AND d.name = x.name
$q$);
SELECT pg_temp.check('RMV3', 'base: the scheduled actions of a removed module that stay with its target are archived', ARRAY['mod:base', 'seed:rm'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE c.id IS NULL OR c.active) = 0,
        format('crons=%s %s', count(*), string_agg(format('%s=%s', x.name, coalesce(c.active::text, 'missing')), ' '))
    FROM (SELECT substr(k, 8) AS name, v::integer AS id FROM oue18_seed WHERE k LIKE 'rmcron.%') x
    LEFT JOIN ir_cron c ON c.id = x.id
$q$);
SELECT pg_temp.check('RMV4', 'base: the groups of a removed module are deleted with the noupdate rules that only served them', ARRAY['mod:base', 'seed:rm'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE pg_temp.row_exists(x.model, x.id)) = 0,
        format('records=%s left=%s', count(*), coalesce(string_agg(x.key, ' ') FILTER (WHERE pg_temp.row_exists(x.model, x.id)), 'none'))
    FROM (SELECT substr(k, 8) AS key, split_part(v, ',', 1) AS model, split_part(v, ',', 2)::integer AS id
          FROM oue18_seed WHERE k LIKE 'rmgone.%') x
$q$);
SELECT pg_temp.check('TWW1', 'website_event: the Social page of an event that showcased a Twitter wall is gone with its website menu, its other menus stay', ARRAY['mod:website_event', 'seed:block.tww'], $q$
    SELECT NOT EXISTS (SELECT 1 FROM website_event_menu WHERE id = pg_temp.si('tww.social_menu') OR menu_type = 'social')
            AND NOT EXISTS (SELECT 1 FROM website_menu WHERE id = pg_temp.si('tww.website_menu'))
            AND (SELECT string_agg(id::text, ',' ORDER BY id) FROM website_event_menu WHERE event_id = pg_temp.si('tww.event'))
                = pg_temp.s('tww.other_menus'),
        format('social event menus=%s website menu left=%s event menus=%s (expected %s)',
            (SELECT count(*) FROM website_event_menu WHERE menu_type = 'social'),
            EXISTS (SELECT 1 FROM website_menu WHERE id = pg_temp.si('tww.website_menu')),
            (SELECT string_agg(id::text, ',' ORDER BY id) FROM website_event_menu WHERE event_id = pg_temp.si('tww.event')),
            pg_temp.s('tww.other_menus'))
$q$);

-- Certificates (l10n_mx_edi, l10n_ec_edi, l10n_pe_edi, l10n_cl_edi, l10n_ar_edi, l10n_nl_reports_sbr,
-- l10n_be_hr_payroll): every 17.0 certificate and key becomes a certificate.certificate and
-- certificate.key with every stored compute, and every 17.0 link points at it.

SELECT pg_temp.check('CRT1', 'every record of the certificate mapping exists and has content, every certificate loads', ARRAY['mod:certificate', 'tbl:openupgrade_legacy_18_0_certificate_map'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE pg_temp.att_sha1(m.target_model, 'content', m.target_id) LIKE '%attachment(s)%'
            OR (m.target_model = 'certificate.certificate' AND (c.id IS NULL OR c.content_format IS NULL
                OR coalesce(c.loading_error, '') <> ''
                OR pg_temp.att_sha1('certificate.certificate', 'pem_certificate', c.id) LIKE '%attachment(s)%'))
            OR (m.target_model = 'certificate.key' AND k.id IS NULL)) = 0,
        format('mapped=%s missing, empty or not loading=%s', count(*), count(*) FILTER (WHERE pg_temp.att_sha1(m.target_model, 'content', m.target_id) LIKE '%attachment(s)%'
            OR (m.target_model = 'certificate.certificate' AND (c.id IS NULL OR c.content_format IS NULL
                OR coalesce(c.loading_error, '') <> ''
                OR pg_temp.att_sha1('certificate.certificate', 'pem_certificate', c.id) LIKE '%attachment(s)%'))
            OR (m.target_model = 'certificate.key' AND k.id IS NULL)))
    FROM openupgrade_legacy_18_0_certificate_map m
    LEFT JOIN certificate_certificate c ON m.target_model = 'certificate.certificate' AND c.id = m.target_id
    LEFT JOIN certificate_key k ON m.target_model = 'certificate.key' AND k.id = m.target_id
$q$);

SELECT pg_temp.check('MX1', 'l10n_mx_edi: every invoice certificate link of 17.0 points at the migrated certificate', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'col:account_move.openupgrade_legacy_18_0_l10n_mx_edi_certificate_id'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE m.l10n_mx_edi_certificate_id IS NULL
            OR m.l10n_mx_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_mx_edi.certificate', 'content',
                m.openupgrade_legacy_18_0_l10n_mx_edi_certificate_id)) = 0
            AND bool_and(m.state = 'posted') FILTER (WHERE m.id = pg_temp.si('mx.move_id')),
        format('moves with a 17.0 certificate=%s not remapped=%s seeded move=%s', count(*), count(*) FILTER (WHERE m.l10n_mx_edi_certificate_id IS NULL
            OR m.l10n_mx_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_mx_edi.certificate', 'content',
                m.openupgrade_legacy_18_0_l10n_mx_edi_certificate_id)),
            string_agg(m.name || ':' || m.state || ':' || coalesce(m.l10n_mx_edi_certificate_id::text, 'none'), ',') FILTER (WHERE m.id = pg_temp.si('mx.move_id')))
    FROM account_move m WHERE m.openupgrade_legacy_18_0_l10n_mx_edi_certificate_id IS NOT NULL
$q$);
SELECT pg_temp.check('MX2', 'l10n_mx_edi: account_move.l10n_mx_edi_certificate_id references certificate_certificate', ARRAY['mod:l10n_mx_edi', 'seed:block.mx'], $q$
    SELECT pg_temp.fk_target('account_move', 'l10n_mx_edi_certificate_id') = 'certificate_certificate',
        coalesce(pg_temp.fk_target('account_move', 'l10n_mx_edi_certificate_id'), 'no foreign key')
$q$);
SELECT pg_temp.check('MX3', 'l10n_mx_edi: the SAT certificate has every stored compute of 18.0 (content, PEM, DER format, serial, subject, dates)', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'tbl:certificate_certificate'], $q$
    SELECT * FROM pg_temp.cert_check('mx', pg_temp.mapped('l10n_mx_edi.certificate', 'content', pg_temp.si('mx.cert_old_id')), 'der')
$q$);
SELECT pg_temp.check('MX4', 'l10n_mx_edi: its private key is the seeded key, decrypted with the 17.0 password', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'tbl:certificate_key'], $q$
    SELECT * FROM pg_temp.key_check('mx', pg_temp.mapped('l10n_mx_edi.certificate', 'key', pg_temp.si('mx.cert_old_id')))
$q$);
SELECT pg_temp.check('MX5', 'l10n_mx_edi: every 17.0 certificate has its certificate and key, linked to each other', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'tbl:l10n_mx_edi_certificate'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE c.id IS NULL OR k.id IS NULL OR c.private_key_id IS DISTINCT FROM k.id) = 0,
        format('17.0 certificates=%s without certificate, key or key link=%s', count(*),
            count(*) FILTER (WHERE c.id IS NULL OR k.id IS NULL OR c.private_key_id IS DISTINCT FROM k.id))
    FROM l10n_mx_edi_certificate o
    LEFT JOIN certificate_certificate c ON c.id = pg_temp.mapped('l10n_mx_edi.certificate', 'content', o.id)
    LEFT JOIN certificate_key k ON k.id = pg_temp.mapped('l10n_mx_edi.certificate', 'key', o.id)
$q$);
SELECT pg_temp.check('MX6', 'l10n_mx_edi: one 18.0 certificate for the one seeded 17.0 certificate', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 1, format('certificates with serial %s in company %s: %s', pg_temp.s('mx.cert_serial'), pg_temp.s('mx.company_id'), count(*))
    FROM certificate_certificate WHERE company_id = pg_temp.si('mx.company_id') AND serial_number = pg_temp.s('mx.cert_serial')
$q$);
SELECT pg_temp.check('MX7', 'l10n_mx_edi: the sent CFDI document is still attached to the invoice', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'tbl:l10n_mx_edi_document'], $q$
    SELECT d.move_id = pg_temp.si('mx.move_id') AND d.state = 'invoice_sent'
            AND EXISTS (SELECT 1 FROM l10n_mx_edi_invoice_document_ids_rel r WHERE r.document_id = d.id AND r.invoice_id = d.move_id),
        format('document=%s move=%s state=%s', d.id, d.move_id, d.state)
    FROM l10n_mx_edi_document d WHERE d.id = pg_temp.si('mx.document_id')
$q$);
SELECT pg_temp.check('MX8', 'l10n_mx_edi: the customer addenda view is an addenda record with its name and template, once', ARRAY['mod:l10n_mx_edi', 'seed:block.mx', 'seed:mx.addenda_view', 'col:res_partner.l10n_mx_edi_addenda_id'], $q$
    SELECT a.name = 'OUE18 addenda' AND a.arch LIKE '%<oue18 order="1"/>%'
            AND (SELECT count(*) FROM l10n_mx_edi_addenda WHERE name = 'OUE18 addenda') = 1,
        format('partner addenda=%s name=%s arch=%s addenda named so=%s', p.l10n_mx_edi_addenda_id, a.name, left(a.arch, 80),
            (SELECT count(*) FROM l10n_mx_edi_addenda WHERE name = 'OUE18 addenda'))
    FROM res_partner p LEFT JOIN l10n_mx_edi_addenda a ON a.id = p.l10n_mx_edi_addenda_id
    WHERE p.id = pg_temp.si('mx.partner_id')
$q$);

SELECT pg_temp.check('EC1', 'l10n_ec_edi: every company certificate link of 17.0 points at the migrated certificate', ARRAY['mod:l10n_ec_edi', 'seed:block.ec', 'col:res_company.openupgrade_legacy_18_0_l10n_ec_edi_certificate_id'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE r.l10n_ec_edi_certificate_id IS NULL
            OR r.l10n_ec_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_ec_edi.certificate', 'content',
                r.openupgrade_legacy_18_0_l10n_ec_edi_certificate_id)) = 0,
        format('companies with a 17.0 certificate=%s not remapped=%s', count(*), count(*) FILTER (WHERE r.l10n_ec_edi_certificate_id IS NULL
            OR r.l10n_ec_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_ec_edi.certificate', 'content',
                r.openupgrade_legacy_18_0_l10n_ec_edi_certificate_id)))
    FROM res_company r WHERE r.openupgrade_legacy_18_0_l10n_ec_edi_certificate_id IS NOT NULL
$q$);
SELECT pg_temp.check('EC2', 'l10n_ec_edi: res_company.l10n_ec_edi_certificate_id references certificate_certificate', ARRAY['mod:l10n_ec_edi', 'seed:block.ec'], $q$
    SELECT pg_temp.fk_target('res_company', 'l10n_ec_edi_certificate_id') = 'certificate_certificate',
        coalesce(pg_temp.fk_target('res_company', 'l10n_ec_edi_certificate_id'), 'no foreign key')
$q$);
SELECT pg_temp.check('EC3', 'l10n_ec_edi: the SRI certificate is the PKCS#12 file with its password and every stored compute of 18.0', ARRAY['mod:l10n_ec_edi', 'seed:block.ec', 'tbl:certificate_certificate'], $q$
    SELECT r.ok AND c.pkcs12_password = pg_temp.s('ec.cert_password'), r.actual || format(' password_ok=%s', c.pkcs12_password = pg_temp.s('ec.cert_password'))
    FROM certificate_certificate c, pg_temp.cert_check('ec', c.id, 'pkcs12') r
    WHERE c.id = pg_temp.mapped('l10n_ec_edi.certificate', 'content', pg_temp.si('ec.cert_old_id'))
$q$);
SELECT pg_temp.check('EC4', 'l10n_ec_edi: 18.0 extracted the seeded private key from the PKCS#12 file and linked it', ARRAY['mod:l10n_ec_edi', 'seed:block.ec', 'tbl:certificate_key'], $q$
    SELECT * FROM pg_temp.key_check('ec', (SELECT private_key_id FROM certificate_certificate
        WHERE id = pg_temp.mapped('l10n_ec_edi.certificate', 'content', pg_temp.si('ec.cert_old_id'))))
$q$);
SELECT pg_temp.check('EC5', 'l10n_ec_edi: one 18.0 certificate for the one seeded 17.0 certificate', ARRAY['mod:l10n_ec_edi', 'seed:block.ec', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 1, format('certificates with serial %s in company %s: %s', pg_temp.s('ec.cert_serial'), pg_temp.s('ec.company_id'), count(*))
    FROM certificate_certificate WHERE company_id = pg_temp.si('ec.company_id') AND serial_number = pg_temp.s('ec.cert_serial')
$q$);
SELECT pg_temp.check('EC6', 'l10n_ec_edi: every 17.0 certificate has its 18.0 record', ARRAY['mod:l10n_ec_edi', 'seed:block.ec', 'tbl:l10n_ec_edi_certificate'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE c.id IS NULL) = 0,
        format('17.0 certificates=%s without 18.0 record=%s', count(*), count(*) FILTER (WHERE c.id IS NULL))
    FROM l10n_ec_edi_certificate o
    LEFT JOIN certificate_certificate c ON c.id = pg_temp.mapped('l10n_ec_edi.certificate', 'content', o.id)
$q$);

SELECT pg_temp.check('PE1', 'l10n_pe_edi: every company certificate link of 17.0 points at the migrated certificate', ARRAY['mod:l10n_pe_edi', 'seed:block.pe', 'col:res_company.openupgrade_legacy_18_0_l10n_pe_edi_certificate_id'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE r.l10n_pe_edi_certificate_id IS NULL
            OR r.l10n_pe_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_pe_edi.certificate', 'content',
                r.openupgrade_legacy_18_0_l10n_pe_edi_certificate_id)) = 0,
        format('companies with a 17.0 certificate=%s not remapped=%s', count(*), count(*) FILTER (WHERE r.l10n_pe_edi_certificate_id IS NULL
            OR r.l10n_pe_edi_certificate_id IS DISTINCT FROM pg_temp.mapped('l10n_pe_edi.certificate', 'content',
                r.openupgrade_legacy_18_0_l10n_pe_edi_certificate_id)))
    FROM res_company r WHERE r.openupgrade_legacy_18_0_l10n_pe_edi_certificate_id IS NOT NULL
$q$);
SELECT pg_temp.check('PE2', 'l10n_pe_edi: res_company.l10n_pe_edi_certificate_id references certificate_certificate', ARRAY['mod:l10n_pe_edi', 'seed:block.pe'], $q$
    SELECT pg_temp.fk_target('res_company', 'l10n_pe_edi_certificate_id') = 'certificate_certificate',
        coalesce(pg_temp.fk_target('res_company', 'l10n_pe_edi_certificate_id'), 'no foreign key')
$q$);
SELECT pg_temp.check('PE3', 'l10n_pe_edi: the SUNAT certificate is the PKCS#12 file with its password and every stored compute of 18.0', ARRAY['mod:l10n_pe_edi', 'seed:block.pe', 'tbl:certificate_certificate'], $q$
    SELECT r.ok AND c.pkcs12_password = pg_temp.s('pe.cert_password'), r.actual || format(' password_ok=%s', c.pkcs12_password = pg_temp.s('pe.cert_password'))
    FROM certificate_certificate c, pg_temp.cert_check('pe', c.id, 'pkcs12') r
    WHERE c.id = pg_temp.mapped('l10n_pe_edi.certificate', 'content', pg_temp.si('pe.cert_old_id'))
$q$);
SELECT pg_temp.check('PE4', 'l10n_pe_edi: 18.0 extracted the seeded private key from the PKCS#12 file and linked it', ARRAY['mod:l10n_pe_edi', 'seed:block.pe', 'tbl:certificate_key'], $q$
    SELECT * FROM pg_temp.key_check('pe', (SELECT private_key_id FROM certificate_certificate
        WHERE id = pg_temp.mapped('l10n_pe_edi.certificate', 'content', pg_temp.si('pe.cert_old_id'))))
$q$);
SELECT pg_temp.check('PE5', 'l10n_pe_edi: one 18.0 certificate for the one seeded 17.0 certificate', ARRAY['mod:l10n_pe_edi', 'seed:block.pe', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 1, format('certificates with serial %s in company %s: %s', pg_temp.s('pe.cert_serial'), pg_temp.s('pe.company_id'), count(*))
    FROM certificate_certificate WHERE company_id = pg_temp.si('pe.company_id') AND serial_number = pg_temp.s('pe.cert_serial')
$q$);
SELECT pg_temp.check('PE6', 'l10n_pe_edi: every 17.0 certificate has its 18.0 record', ARRAY['mod:l10n_pe_edi', 'seed:block.pe', 'tbl:l10n_pe_edi_certificate'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE c.id IS NULL) = 0,
        format('17.0 certificates=%s without 18.0 record=%s', count(*), count(*) FILTER (WHERE c.id IS NULL))
    FROM l10n_pe_edi_certificate o
    LEFT JOIN certificate_certificate c ON c.id = pg_temp.mapped('l10n_pe_edi.certificate', 'content', o.id)
$q$);

SELECT pg_temp.check('CL1', 'l10n_cl_edi: one 18.0 certificate for the one seeded SII certificate', ARRAY['mod:l10n_cl_edi', 'seed:block.cl', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 1, format('certificates with serial %s in company %s: %s', pg_temp.s('cl.cert_serial'), pg_temp.s('cl.company_id'), count(*))
    FROM certificate_certificate WHERE company_id = pg_temp.si('cl.company_id') AND serial_number = pg_temp.s('cl.cert_serial')
$q$);
SELECT pg_temp.check('CL2', 'l10n_cl_edi: the certificate is the PFX file with its passphrase and every stored compute of 18.0', ARRAY['mod:l10n_cl_edi', 'seed:block.cl', 'tbl:certificate_certificate'], $q$
    SELECT r.ok AND c.pkcs12_password = pg_temp.s('cl.cert_password'), r.actual || format(' password_ok=%s', c.pkcs12_password = pg_temp.s('cl.cert_password'))
    FROM certificate_certificate c, pg_temp.cert_check('cl', c.id, 'pkcs12') r
    WHERE c.id = pg_temp.mapped('l10n_cl.certificate', 'signature_key_file', pg_temp.si('cl.cert_old_id'))
$q$);
SELECT pg_temp.check('CL3', 'l10n_cl_edi: 18.0 extracted the seeded private key from the PFX file and linked it', ARRAY['mod:l10n_cl_edi', 'seed:block.cl', 'tbl:certificate_key'], $q$
    SELECT * FROM pg_temp.key_check('cl', (SELECT private_key_id FROM certificate_certificate
        WHERE id = pg_temp.mapped('l10n_cl.certificate', 'signature_key_file', pg_temp.si('cl.cert_old_id'))))
$q$);
SELECT pg_temp.check('CL4', 'l10n_cl_edi: owner, SII token, token time, subject serial number and name carried over', ARRAY['mod:l10n_cl_edi', 'seed:block.cl', 'col:certificate_certificate.last_token'], $q$
    SELECT c.user_id = pg_temp.si('cl.user_id') AND c.last_token = pg_temp.s('cl.last_token')
            AND c.token_time = pg_temp.s('cl.token_time')::timestamp
            AND c.subject_serial_number = pg_temp.s('cl.subject_serial_number') AND c.name = pg_temp.s('cl.name'),
        format('certificate=%s user=%s token=%s time=%s subject_serial=%s name=%s', c.id, c.user_id, c.last_token, c.token_time,
            c.subject_serial_number, c.name)
    FROM certificate_certificate c
    WHERE c.id = pg_temp.mapped('l10n_cl.certificate', 'signature_key_file', pg_temp.si('cl.cert_old_id'))
$q$);
SELECT pg_temp.check('CL5', 'l10n_cl_edi: every 17.0 certificate has its 18.0 record', ARRAY['mod:l10n_cl_edi', 'seed:block.cl', 'tbl:l10n_cl_certificate'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE c.id IS NULL) = 0,
        format('17.0 certificates=%s without 18.0 record=%s', count(*), count(*) FILTER (WHERE c.id IS NULL))
    FROM l10n_cl_certificate o
    LEFT JOIN certificate_certificate c ON c.id = pg_temp.mapped('l10n_cl.certificate', 'signature_key_file', o.id)
$q$);

SELECT pg_temp.check('AR1', 'l10n_ar_edi: the company AFIP certificate link points at the migrated certificate', ARRAY['mod:l10n_ar_edi', 'seed:block.ar', 'col:res_company.l10n_ar_afip_ws_crt_id'], $q$
    SELECT l10n_ar_afip_ws_crt_id IS NOT NULL
            AND l10n_ar_afip_ws_crt_id = pg_temp.mapped('res.company', 'l10n_ar_afip_ws_crt', id),
        format('company=%s certificate=%s mapped=%s', id, l10n_ar_afip_ws_crt_id, pg_temp.mapped('res.company', 'l10n_ar_afip_ws_crt', id))
    FROM res_company WHERE id = pg_temp.si('ar.company_id')
$q$);
SELECT pg_temp.check('AR2', 'l10n_ar_edi: the certificate is the PEM file with its file name and every stored compute of 18.0', ARRAY['mod:l10n_ar_edi', 'seed:block.ar', 'tbl:certificate_certificate'], $q$
    SELECT r.ok AND c.name = pg_temp.s('ar.crt_fname'), r.actual || format(' name=%s', c.name)
    FROM certificate_certificate c, pg_temp.cert_check('ar', c.id, 'pem') r
    WHERE c.id = pg_temp.mapped('res.company', 'l10n_ar_afip_ws_crt', pg_temp.si('ar.company_id'))
$q$);
SELECT pg_temp.check('AR3', 'l10n_ar_edi: the company key link and the certificate private key are the migrated PEM key', ARRAY['mod:l10n_ar_edi', 'seed:block.ar', 'col:res_company.l10n_ar_afip_ws_key_id'], $q$
    SELECT r.ok AND co.l10n_ar_afip_ws_key_id = c.private_key_id
            AND pg_temp.att_sha1('certificate.key', 'content', c.private_key_id) = pg_temp.s('ar.key_content_sha1'),
        r.actual || format(' company_key=%s certificate_key=%s', co.l10n_ar_afip_ws_key_id, c.private_key_id)
    FROM res_company co, certificate_certificate c, pg_temp.key_check('ar', c.private_key_id) r
    WHERE co.id = pg_temp.si('ar.company_id') AND c.id = pg_temp.mapped('res.company', 'l10n_ar_afip_ws_crt', co.id)
$q$);
SELECT pg_temp.check('AR4', 'l10n_ar_edi: the company with a key and no certificate keeps its key, linked', ARRAY['mod:l10n_ar_edi', 'seed:block.ar', 'col:res_company.l10n_ar_afip_ws_key_id'], $q$
    SELECT r.ok AND co.l10n_ar_afip_ws_crt_id IS NULL, r.actual || format(' company=%s certificate=%s', co.id, co.l10n_ar_afip_ws_crt_id)
    FROM res_company co, pg_temp.key_check('ar2', co.l10n_ar_afip_ws_key_id) r
    WHERE co.id = pg_temp.si('ar2.company_id')
$q$);
SELECT pg_temp.check('AR5', 'l10n_ar_edi: one 18.0 certificate for the one seeded AFIP certificate', ARRAY['mod:l10n_ar_edi', 'seed:block.ar', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 1, format('certificates with serial %s in company %s: %s', pg_temp.s('ar.cert_serial'), pg_temp.s('ar.company_id'), count(*))
    FROM certificate_certificate WHERE company_id = pg_temp.si('ar.company_id') AND serial_number = pg_temp.s('ar.cert_serial')
$q$);

SELECT pg_temp.check('NL1', 'l10n_nl_reports_sbr: the company Digipoort certificate link points at the migrated certificate', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'col:res_company.l10n_nl_reports_sbr_cert_id'], $q$
    SELECT co.l10n_nl_reports_sbr_cert_id = pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_cert', co.id),
        format('company=%s certificate=%s mapped=%s', co.id, co.l10n_nl_reports_sbr_cert_id, pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_cert', co.id))
    FROM res_company co WHERE co.id = pg_temp.si('nl.company_id')
$q$);
SELECT pg_temp.check('NL2', 'l10n_nl_reports_sbr: the certificate is the PEM file with its file name and every stored compute of 18.0', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'tbl:certificate_certificate'], $q$
    SELECT r.ok AND c.name = pg_temp.s('nl.cert_filename'), r.actual || format(' name=%s', c.name)
    FROM certificate_certificate c, pg_temp.cert_check('nl', c.id, 'pem') r
    WHERE c.id = pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_cert', pg_temp.si('nl.company_id'))
$q$);
SELECT pg_temp.check('NL3', 'l10n_nl_reports_sbr: its private key is the migrated PEM key with its file name', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'tbl:certificate_key'], $q$
    SELECT r.ok AND k.name = pg_temp.s('nl.key_filename'), r.actual || format(' name=%s', k.name)
    FROM certificate_certificate c JOIN certificate_key k ON k.id = c.private_key_id, pg_temp.key_check('nl', k.id) r
    WHERE c.id = pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_cert', pg_temp.si('nl.company_id'))
$q$);
SELECT pg_temp.check('NL4', 'l10n_nl_reports_sbr: the company SBR root certificate link points at the migrated root certificate', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'col:res_company.l10n_nl_reports_sbr_server_root_cert_id'], $q$
    SELECT r.ok AND co.l10n_nl_reports_sbr_server_root_cert_id = pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_server_root_cert', co.id),
        r.actual || format(' link=%s', co.l10n_nl_reports_sbr_server_root_cert_id)
    FROM res_company co, pg_temp.cert_check('nl_root', pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_server_root_cert', co.id), 'pem') r
    WHERE co.id = pg_temp.si('nl.company_id')
$q$);
SELECT pg_temp.check('NL5', 'l10n_nl_reports_sbr: a key encrypted with a password 17.0 never stored is kept, unlinked, next to its linked certificate', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'tbl:certificate_key'], $q$
    SELECT r.ok AND c.private_key_id IS NULL AND k.id IS NOT NULL AND coalesce(k.loading_error, '') <> ''
            AND pg_temp.att_sha1('certificate.key', 'content', k.id) = pg_temp.s('nl2.key_content_sha1'),
        r.actual || format(' certificate_key=%s kept_key=%s kept_key_error=%s', c.private_key_id, k.id, k.loading_error IS NOT NULL)
    FROM res_company co JOIN certificate_certificate c ON c.id = co.l10n_nl_reports_sbr_cert_id
    LEFT JOIN certificate_key k ON k.id = pg_temp.mapped('res.company', 'l10n_nl_reports_sbr_key', co.id),
        pg_temp.cert_check('nl2', c.id, 'pem') r
    WHERE co.id = pg_temp.si('nl2.company_id')
$q$);
SELECT pg_temp.check('NL6', 'l10n_nl_reports_sbr: one 18.0 certificate per seeded certificate and company', ARRAY['mod:l10n_nl_reports_sbr', 'seed:block.nl', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 3, format('matching certificates=%s of 3', count(*))
    FROM certificate_certificate c
    WHERE (c.company_id = pg_temp.si('nl.company_id') AND c.serial_number IN (pg_temp.s('nl.cert_serial'), pg_temp.s('nl_root.cert_serial')))
       OR (c.company_id = pg_temp.si('nl2.company_id') AND c.serial_number = pg_temp.s('nl2.cert_serial'))
$q$);

SELECT pg_temp.check('BE1', 'l10n_be_hr_payroll: the company ONSS certificate link points at the migrated certificate', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.be', 'col:res_company.onss_certificate_id'], $q$
    SELECT co.onss_certificate_id = pg_temp.mapped('res.company', 'onss_pem_certificate', co.id),
        format('company=%s certificate=%s mapped=%s', co.id, co.onss_certificate_id, pg_temp.mapped('res.company', 'onss_pem_certificate', co.id))
    FROM res_company co WHERE co.id = pg_temp.si('be.company_id')
$q$);
SELECT pg_temp.check('BE2', 'l10n_be_hr_payroll: the ONSS certificate is the PEM file with every stored compute of 18.0', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.be', 'tbl:certificate_certificate'], $q$
    SELECT * FROM pg_temp.cert_check('be', pg_temp.mapped('res.company', 'onss_pem_certificate', pg_temp.si('be.company_id')), 'pem')
$q$);
SELECT pg_temp.check('BE3', 'l10n_be_hr_payroll: its private key is the 17.0 key file (unencrypted, so no password kept)', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.be', 'tbl:certificate_key'], $q$
    SELECT r.ok AND c.private_key_id = pg_temp.mapped('res.company', 'onss_key', pg_temp.si('be.company_id')) AND k.password IS NULL,
        r.actual || format(' key=%s mapped=%s', c.private_key_id, pg_temp.mapped('res.company', 'onss_key', pg_temp.si('be.company_id')))
    FROM certificate_certificate c JOIN certificate_key k ON k.id = c.private_key_id, pg_temp.key_check('be', k.id) r
    WHERE c.id = pg_temp.mapped('res.company', 'onss_pem_certificate', pg_temp.si('be.company_id'))
$q$);
SELECT pg_temp.check('BE4', 'l10n_be_hr_payroll: with an unrelated key file, the key embedded in the certificate file is used with the passphrase', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.be', 'col:res_company.onss_certificate_id'], $q$
    SELECT rc.ok AND rk.ok AND k.password = pg_temp.s('be2.cert_password'), rc.actual || ' / ' || rk.actual
    FROM res_company co JOIN certificate_certificate c ON c.id = co.onss_certificate_id
    JOIN certificate_key k ON k.id = c.private_key_id, pg_temp.cert_check('be2', c.id, 'pem') rc, pg_temp.key_check('be2', k.id) rk
    WHERE co.id = pg_temp.si('be2.company_id')
$q$);
SELECT pg_temp.check('BE5', 'l10n_be_hr_payroll: one 18.0 certificate per seeded certificate and company', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.be', 'tbl:certificate_certificate'], $q$
    SELECT count(*) = 2, format('matching certificates=%s of 2', count(*))
    FROM certificate_certificate c
    WHERE (c.company_id = pg_temp.si('be.company_id') AND c.serial_number = pg_temp.s('be.cert_serial'))
       OR (c.company_id = pg_temp.si('be2.company_id') AND c.serial_number = pg_temp.s('be2.cert_serial'))
$q$);
SELECT pg_temp.check('BE6', 'l10n_be_hr_payroll: the voluntary withholding rate of the open contract is the employee''s', ARRAY['mod:l10n_be_hr_payroll', 'seed:block.befv', 'col:hr_employee.fiscal_voluntary_rate'], $q$
    SELECT e.fiscal_voluntary_rate = pg_temp.s('befv.rate')::numeric, format('employee=%s rate=%s expected %s', e.id, e.fiscal_voluntary_rate, pg_temp.s('befv.rate'))
    FROM hr_employee e WHERE e.id = pg_temp.si('befv.employee')
$q$);

SELECT pg_temp.check('PLM1', 'mrp_plm: the ECO whose image id has no product_document row shows its own image', ARRAY['mod:mrp_plm', 'seed:block.plm', 'tbl:product_document'], $q$
    SELECT pd.ir_attachment_id = pg_temp.si('plm.att_high_id'),
        format('eco=%s displayed=%s attachment=%s expected=%s', e.id, e.displayed_image_id, pd.ir_attachment_id, pg_temp.s('plm.att_high_id'))
    FROM mrp_eco e LEFT JOIN product_document pd ON pd.id = e.displayed_image_id
    WHERE e.id = pg_temp.si('plm.eco_high_id')
$q$);
SELECT pg_temp.check('PLM2', 'mrp_plm: the ECO whose image id collided with a product_document id shows its own image', ARRAY['mod:mrp_plm', 'seed:block.plm', 'tbl:product_document'], $q$
    SELECT pd.ir_attachment_id = pg_temp.si('plm.att_low_id'),
        format('eco=%s displayed=%s attachment=%s expected=%s collision_seeded=%s', e.id, e.displayed_image_id, pd.ir_attachment_id,
            pg_temp.s('plm.att_low_id'), pg_temp.s('plm.collision'))
    FROM mrp_eco e LEFT JOIN product_document pd ON pd.id = e.displayed_image_id
    WHERE e.id = pg_temp.si('plm.eco_low_id')
$q$);
SELECT pg_temp.check('PLM3', 'mrp_plm: mrp_eco.displayed_image_id references product_document', ARRAY['mod:mrp_plm', 'seed:block.plm'], $q$
    SELECT pg_temp.fk_target('mrp_eco', 'displayed_image_id') = 'product_document',
        coalesce(pg_temp.fk_target('mrp_eco', 'displayed_image_id'), 'no foreign key')
$q$);
SELECT pg_temp.check('PLM4', 'mrp_plm: both ECO image attachments kept their content and image mimetype', ARRAY['mod:mrp_plm', 'seed:block.plm'], $q$
    SELECT count(*) = 2, format('matching attachments=%s of 2', count(*))
    FROM ir_attachment a
    WHERE (a.id = pg_temp.si('plm.att_high_id') AND a.checksum = pg_temp.s('plm.att_high_checksum')
            AND a.mimetype = pg_temp.s('plm.att_high_mimetype'))
       OR (a.id = pg_temp.si('plm.att_low_id') AND a.checksum = pg_temp.s('plm.att_low_checksum')
            AND a.mimetype = pg_temp.s('plm.att_low_mimetype'))
$q$);
SELECT pg_temp.check('PLM5', 'mrp_plm: the product document that existed on 17.0 is unchanged and shown by no ECO', ARRAY['mod:mrp_plm', 'seed:block.plm', 'tbl:product_document'], $q$
    SELECT a.res_model = 'product.template' AND NOT EXISTS (
            SELECT 1 FROM mrp_eco e WHERE e.displayed_image_id = pd.id),
        format('product_document=%s attachment=%s res_model=%s', pd.id, pd.ir_attachment_id, a.res_model)
    FROM product_document pd JOIN ir_attachment a ON a.id = pd.ir_attachment_id
    WHERE pd.id = pg_temp.si('plm.product_document_id')
$q$);

-- Company-dependent fields (17.0 ir_property, 18.0 jsonb per company), converted by the base
-- end-migration before OpenUpgrade removes ir.property.

SELECT pg_temp.check('CD1', 'account_followup: next reminder date per company, none for the empty company', ARRAY['mod:account_followup', 'seed:block.fu', 'col:res_partner.followup_next_action_date'], $q$
    SELECT pg_temp.cv(p.followup_next_action_date, pg_temp.s('cd.company_a_id')) = pg_temp.s('fu.date_a')
            AND pg_temp.cv(p.followup_next_action_date, pg_temp.s('cd.company_b_id')) = pg_temp.s('fu.date_b')
            AND pg_temp.cv(p.followup_next_action_date, pg_temp.s('cd.company_c_id')) IS NULL,
        format('partner=%s value=%s expected a=%s b=%s', p.id, p.followup_next_action_date, pg_temp.s('fu.date_a'), pg_temp.s('fu.date_b'))
    FROM res_partner p WHERE p.id = pg_temp.si('fu.partner_id')
$q$);
SELECT pg_temp.check('CD2', 'account_followup: follow-up responsible per company, none for the empty company', ARRAY['mod:account_followup', 'seed:block.fu', 'col:res_partner.followup_responsible_id'], $q$
    SELECT pg_temp.cv(p.followup_responsible_id, pg_temp.s('cd.company_a_id')) = pg_temp.s('fu.user_a')
            AND pg_temp.cv(p.followup_responsible_id, pg_temp.s('cd.company_b_id')) = pg_temp.s('fu.user_b')
            AND pg_temp.cv(p.followup_responsible_id, pg_temp.s('cd.company_c_id')) IS NULL,
        format('partner=%s value=%s expected a=%s b=%s', p.id, p.followup_responsible_id, pg_temp.s('fu.user_a'), pg_temp.s('fu.user_b'))
    FROM res_partner p WHERE p.id = pg_temp.si('fu.partner_id')
$q$);
SELECT pg_temp.check('CD3', 'hr_payroll_account: salary journal of the structure per company, none for the empty company', ARRAY['mod:hr_payroll_account', 'seed:block.pay', 'col:hr_payroll_structure.journal_id'], $q$
    SELECT pg_temp.cv(s.journal_id, pg_temp.s('cd.company_a_id')) = pg_temp.s('pay.journal_a')
            AND pg_temp.cv(s.journal_id, pg_temp.s('cd.company_b_id')) = pg_temp.s('pay.journal_b')
            AND pg_temp.cv(s.journal_id, pg_temp.s('cd.company_c_id')) IS NULL,
        format('structure=%s value=%s expected a=%s b=%s', s.id, s.journal_id, pg_temp.s('pay.journal_a'), pg_temp.s('pay.journal_b'))
    FROM hr_payroll_structure s WHERE s.id = pg_temp.si('pay.structure_id')
$q$);
SELECT pg_temp.check('CD4', 'hr_payroll_account: debit, credit and analytic account of the rule per company, none for the empty company', ARRAY['mod:hr_payroll_account', 'seed:block.pay', 'col:hr_salary_rule.account_debit'], $q$
    SELECT pg_temp.cv(r.account_debit, pg_temp.s('cd.company_a_id')) = pg_temp.s('pay.debit_a')
            AND pg_temp.cv(r.account_debit, pg_temp.s('cd.company_b_id')) = pg_temp.s('pay.debit_b')
            AND pg_temp.cv(r.account_credit, pg_temp.s('cd.company_a_id')) = pg_temp.s('pay.credit_a')
            AND pg_temp.cv(r.account_credit, pg_temp.s('cd.company_b_id')) = pg_temp.s('pay.credit_b')
            AND pg_temp.cv(r.analytic_account_id, pg_temp.s('cd.company_a_id')) = pg_temp.s('pay.analytic_a')
            AND pg_temp.cv(r.analytic_account_id, pg_temp.s('cd.company_b_id')) = pg_temp.s('pay.analytic_b')
            AND pg_temp.cv(r.account_debit, pg_temp.s('cd.company_c_id')) IS NULL
            AND pg_temp.cv(r.account_credit, pg_temp.s('cd.company_c_id')) IS NULL
            AND pg_temp.cv(r.analytic_account_id, pg_temp.s('cd.company_c_id')) IS NULL,
        format('rule=%s debit=%s credit=%s analytic=%s', r.id, r.account_debit, r.account_credit, r.analytic_account_id)
    FROM hr_salary_rule r WHERE r.id = pg_temp.si('pay.rule_id')
$q$);
SELECT pg_temp.check('CD5', 'industry_fsm_sale_report: worksheet template of the service per company, none for the empty company', ARRAY['mod:industry_fsm_sale_report', 'seed:block.fsm', 'col:product_template.worksheet_template_id'], $q$
    SELECT pg_temp.cv(t.worksheet_template_id, pg_temp.s('cd.company_a_id')) = pg_temp.s('fsm.template_a')
            AND pg_temp.cv(t.worksheet_template_id, pg_temp.s('cd.company_b_id')) = pg_temp.s('fsm.template_b')
            AND pg_temp.cv(t.worksheet_template_id, pg_temp.s('cd.company_c_id')) IS NULL,
        format('product=%s value=%s expected a=%s b=%s', t.id, t.worksheet_template_id, pg_temp.s('fsm.template_a'), pg_temp.s('fsm.template_b'))
    FROM product_template t WHERE t.id = pg_temp.si('fsm.product_id')
$q$);
SELECT pg_temp.check('CD6', 'sale_renting: extra hour and day prices per company, the company default as ir.default', ARRAY['mod:sale_renting', 'seed:block.rent', 'col:product_template.extra_hourly'], $q$
    SELECT pg_temp.cv(t.extra_hourly, pg_temp.s('cd.company_a_id'))::numeric = pg_temp.s('rent.hourly_a')::numeric
            AND pg_temp.cv(t.extra_hourly, pg_temp.s('cd.company_b_id'))::numeric = pg_temp.s('rent.hourly_b')::numeric
            AND pg_temp.cv(t.extra_daily, pg_temp.s('cd.company_a_id'))::numeric = pg_temp.s('rent.daily_a')::numeric
            AND pg_temp.cv(t.extra_daily, pg_temp.s('cd.company_b_id'))::numeric = pg_temp.s('rent.daily_b')::numeric
            AND pg_temp.cv(t.extra_hourly, pg_temp.s('cd.company_c_id')) IS NULL
            AND EXISTS (SELECT 1 FROM ir_default d JOIN ir_model_fields f ON f.id = d.field_id
                WHERE f.model = 'product.template' AND f.name = 'extra_hourly'
                    AND d.company_id = pg_temp.si('cd.company_b_id') AND d.json_value::numeric = pg_temp.s('rent.default_hourly_b')::numeric),
        format('product=%s hourly=%s daily=%s defaults b=%s', t.id, t.extra_hourly, t.extra_daily,
            (SELECT string_agg(d.json_value, ',') FROM ir_default d JOIN ir_model_fields f ON f.id = d.field_id
                WHERE f.model = 'product.template' AND f.name = 'extra_hourly' AND d.company_id = pg_temp.si('cd.company_b_id')))
    FROM product_template t WHERE t.id = pg_temp.si('rent.product_id')
$q$);
SELECT pg_temp.check('CD7', 'sale_stock_renting: preparation time per company, none for the empty company', ARRAY['mod:sale_stock_renting', 'seed:block.srent', 'col:product_template.preparation_time'], $q$
    SELECT pg_temp.cv(t.preparation_time, pg_temp.s('cd.company_a_id'))::numeric = pg_temp.s('srent.prep_a')::numeric
            AND pg_temp.cv(t.preparation_time, pg_temp.s('cd.company_b_id'))::numeric = pg_temp.s('srent.prep_b')::numeric
            AND pg_temp.cv(t.preparation_time, pg_temp.s('cd.company_c_id')) IS NULL,
        format('product=%s value=%s', t.id, t.preparation_time)
    FROM product_template t WHERE t.id = pg_temp.si('srent.product_id')
$q$);
SELECT pg_temp.check('CD8', 'every enterprise company-dependent field of an installed module is converted: marked, and every 17.0 value has its company key',
    ARRAY['mod:account_avatax|account_followup|delivery_ups|delivery_ups_rest|hr_payroll_account|industry_fsm_sale_report|l10n_be_hr_payroll_fleet|l10n_br_avatax|l10n_de_reports|l10n_ec_edi|sale_renting|sale_stock_renting',
        'tbl:openupgrade_legacy_18_0_company_dependent'], $q$
    SELECT count(*) > 0 AND count(*) FILTER (WHERE NOT coalesce(marked AND missing = 0, false)) = 0,
        format('applicable=%s %s', count(*), coalesce(string_agg(format('%s.%s=%s%s', model, field, coalesce(missing::text, 'n/a'),
            CASE WHEN marked THEN '' ELSE ' unmarked' END), ' ' ORDER BY model, field), ''))
    FROM (
        SELECT v.model, v.field, pg_temp.cd_missing(v.model, v.field) AS missing,
            EXISTS (SELECT 1 FROM openupgrade_legacy_18_0_company_dependent k WHERE k.model = v.model AND k.field = v.field) AS marked
        FROM (VALUES
            ('account_avatax', 'res.partner', 'avalara_exemption_id'),
            ('account_followup', 'res.partner', 'followup_next_action_date'),
            ('account_followup', 'res.partner', 'followup_responsible_id'),
            ('delivery_ups', 'res.partner', 'property_ups_carrier_account'),
            ('delivery_ups_rest', 'res.partner', 'property_ups_carrier_account'),
            ('hr_payroll_account', 'hr.payroll.structure', 'journal_id'),
            ('hr_payroll_account', 'hr.salary.rule', 'analytic_account_id'),
            ('hr_payroll_account', 'hr.salary.rule', 'account_debit'),
            ('hr_payroll_account', 'hr.salary.rule', 'account_credit'),
            ('industry_fsm_sale_report', 'product.template', 'worksheet_template_id'),
            ('l10n_be_hr_payroll_fleet', 'fleet.vehicle.model', 'can_be_requested'),
            ('l10n_br_avatax', 'product.template', 'l10n_br_property_service_code_origin_id'),
            ('l10n_de_reports', 'res.company', 'l10n_de_datev_consultant_number'),
            ('l10n_de_reports', 'res.company', 'l10n_de_datev_client_number'),
            ('l10n_ec_edi', 'l10n_ec.taxpayer.type', 'profit_withhold_tax_id'),
            ('l10n_ec_edi', 'l10n_ec.taxpayer.type', 'vat_goods_withhold_tax_id'),
            ('l10n_ec_edi', 'l10n_ec.taxpayer.type', 'vat_services_withhold_tax_id'),
            ('l10n_ec_edi', 'product.template', 'l10n_ec_withhold_tax_id'),
            ('sale_renting', 'product.template', 'extra_hourly'),
            ('sale_renting', 'product.template', 'extra_daily'),
            ('sale_stock_renting', 'product.template', 'preparation_time')
        ) v(module, model, field)
        WHERE pg_temp.installed(v.module)
    ) x
$q$);
SELECT pg_temp.check('CD9', 'the conversion marker holds every converted field once, with its source',
    ARRAY['mod:account_avatax|account_followup|delivery_ups|delivery_ups_rest|hr_payroll_account|industry_fsm_sale_report|l10n_be_hr_payroll_fleet|l10n_br_avatax|l10n_de_reports|l10n_ec_edi|sale_renting|sale_stock_renting',
        'tbl:openupgrade_legacy_18_0_company_dependent'], $q$
    SELECT count(*) > 0 AND count(*) = count(DISTINCT (model, field))
            AND count(*) FILTER (WHERE source NOT IN ('ir_property', 'openupgrade_legacy_18_0_l10n_de_datev_identifier',
                'openupgrade_legacy_18_0_l10n_de_datev_identifier_customer')) = 0,
        format('rows=%s %s', count(*), coalesce(string_agg(format('%s.%s<-%s:%s/%s', model, field, source, records, defaults),
            ' ' ORDER BY model, field), ''))
    FROM openupgrade_legacy_18_0_company_dependent
$q$);
SELECT pg_temp.check('RNT1', 'sale_renting: the xmlids of the 17.0 extra price defaults are gone, their ir.property rows left to the conversion', ARRAY['mod:sale_renting', 'seed:block.rent'], $q$
    SELECT * FROM pg_temp.gone('rent', NULL)
$q$);
SELECT pg_temp.check('SRN1', 'sale_stock_renting: the xmlid of the 17.0 preparation time default is gone', ARRAY['mod:sale_stock_renting', 'seed:block.srent'], $q$
    SELECT * FROM pg_temp.gone('srent', NULL)
$q$);

SELECT pg_temp.check('DE1', 'l10n_de_reports: DATEV consultant and client numbers per company, none for the empty company', ARRAY['mod:l10n_de_reports', 'seed:block.de', 'col:res_company.l10n_de_datev_consultant_number'], $q$
    SELECT pg_temp.cv(de.l10n_de_datev_consultant_number, pg_temp.s('de.company_id')) = pg_temp.s('de.consultant_de')
            AND pg_temp.cv(de.l10n_de_datev_client_number, pg_temp.s('de.company_id')) = pg_temp.s('de.client_de')
            AND pg_temp.cv(a.l10n_de_datev_consultant_number, pg_temp.s('cd.company_a_id')) = pg_temp.s('de.consultant_a')
            AND pg_temp.cv(a.l10n_de_datev_client_number, pg_temp.s('cd.company_a_id')) = pg_temp.s('de.client_a')
            AND e.l10n_de_datev_consultant_number IS NULL AND e.l10n_de_datev_client_number IS NULL,
        format('de=%s/%s main=%s/%s empty=%s/%s', de.l10n_de_datev_consultant_number, de.l10n_de_datev_client_number,
            a.l10n_de_datev_consultant_number, a.l10n_de_datev_client_number,
            e.l10n_de_datev_consultant_number, e.l10n_de_datev_client_number)
    FROM res_company de, res_company a, res_company e
    WHERE de.id = pg_temp.si('de.company_id') AND a.id = pg_temp.si('cd.company_a_id') AND e.id = pg_temp.si('de.empty_company_id')
$q$);
SELECT pg_temp.check('DE2', 'l10n_de_reports: DATEV partner identifiers in every company that sees the partner, none when empty', ARRAY['mod:l10n_de_reports', 'seed:block.de', 'col:res_partner.l10n_de_datev_identifier'], $q$
    SELECT (SELECT count(*) FROM jsonb_each_text(s.l10n_de_datev_identifier) j WHERE j.value = '70001') = (SELECT count(*) FROM res_company)
            AND (SELECT count(*) FROM jsonb_each_text(s.l10n_de_datev_identifier_customer) j WHERE j.value = '10001') = (SELECT count(*) FROM res_company)
            AND o.l10n_de_datev_identifier = jsonb_build_object(pg_temp.s('de.company_id'), 70002)
            AND o.l10n_de_datev_identifier_customer IS NULL
            AND n.l10n_de_datev_identifier IS NULL AND n.l10n_de_datev_identifier_customer IS NULL,
        format('shared=%s/%s own=%s/%s none=%s/%s companies=%s', s.l10n_de_datev_identifier, s.l10n_de_datev_identifier_customer,
            o.l10n_de_datev_identifier, o.l10n_de_datev_identifier_customer, n.l10n_de_datev_identifier,
            n.l10n_de_datev_identifier_customer, (SELECT count(*) FROM res_company))
    FROM res_partner s, res_partner o, res_partner n
    WHERE s.id = pg_temp.si('de.shared_id') AND o.id = pg_temp.si('de.own_id') AND n.id = pg_temp.si('de.empty_id')
$q$);

SELECT pg_temp.check('HS1', 'helpdesk_sale_timesheet: each company''s SLA policy of the service lists the service', ARRAY['mod:helpdesk_sale_timesheet', 'seed:block.sla', 'tbl:helpdesk_sla_product_template_rel'], $q$
    SELECT count(*) = 2, format('links of service %s: %s', pg_temp.s('sla.service_id'), string_agg(helpdesk_sla_id::text, ',' ORDER BY helpdesk_sla_id))
    FROM helpdesk_sla_product_template_rel
    WHERE product_template_id = pg_temp.si('sla.service_id') AND helpdesk_sla_id IN (pg_temp.si('sla.x_id'), pg_temp.si('sla.y_id'))
$q$);
SELECT pg_temp.check('HS2', 'helpdesk_sale_timesheet: a policy linked only to an order line is not widened to the product', ARRAY['mod:helpdesk_sale_timesheet', 'seed:block.sla', 'tbl:helpdesk_sla_product_template_rel'], $q$
    SELECT count(*) = 0, format('products of policy %s: %s', pg_temp.s('sla.z_id'), coalesce(string_agg(product_template_id::text, ','), 'none'))
    FROM helpdesk_sla_product_template_rel WHERE helpdesk_sla_id = pg_temp.si('sla.z_id')
$q$);

SELECT pg_temp.check('EC7', 'l10n_ec_edi: ec51020205, ec51030205 and ec52010405 are accounts with their template code in both EC companies', ARRAY['mod:l10n_ec_edi', 'seed:block.ec_cd', 'seed:ec2.company_id'], $q$
    SELECT count(*) = 6 AND count(*) FILTER (WHERE d.model = 'account.account'
                AND a.code_store ->> c.cid::text = substring(x.tid from 3)) = 6,
        string_agg(format('%s_%s=%s:%s:%s', c.cid, x.tid, d.model, d.res_id, a.code_store ->> c.cid::text), ' ' ORDER BY c.cid, x.tid)
    FROM (VALUES (pg_temp.si('ec.company_id')), (pg_temp.si('ec2.company_id'))) c(cid)
    CROSS JOIN (VALUES ('ec51020205'), ('ec51030205'), ('ec52010405')) x(tid)
    LEFT JOIN ir_model_data d ON d.module = 'account' AND d.name = c.cid || '_' || x.tid
    LEFT JOIN account_account a ON d.model = 'account.account' AND a.id = d.res_id
$q$);
SELECT pg_temp.check('EC8', 'l10n_ec_edi: the 17.0 chart groups of these ids still exist, under legacy xmlids', ARRAY['mod:l10n_ec_edi', 'seed:block.ec_cd', 'seed:ec2.company_id'], $q$
    SELECT count(*) = 6 AND count(*) FILTER (WHERE d.model = 'account.group' AND g.id IS NOT NULL
                AND d.res_id = pg_temp.si(format('ec_chart.%s.%s', c.prefix, x.tid))) = 6,
        string_agg(format('%s_%s=%s:%s', c.cid, x.tid, d.model, d.res_id), ' ' ORDER BY c.cid, x.tid)
    FROM (VALUES ('ec', pg_temp.si('ec.company_id')), ('ec2', pg_temp.si('ec2.company_id'))) c(prefix, cid)
    CROSS JOIN (VALUES ('ec51020205'), ('ec51030205'), ('ec52010405')) x(tid)
    LEFT JOIN ir_model_data d ON d.module = 'account' AND d.name = 'openupgrade_legacy_18_0_' || c.cid || '_' || x.tid
    LEFT JOIN account_group g ON g.id = d.res_id
$q$);
SELECT pg_temp.check('EC9', 'l10n_ec_edi: withholding taxes of the taxpayer type per EC company, none for the main company', ARRAY['mod:l10n_ec_edi', 'seed:block.ec_cd', 'col:l10n_ec_taxpayer_type.profit_withhold_tax_id'], $q$
    SELECT pg_temp.cv(t.profit_withhold_tax_id, pg_temp.s('ec.company_id')) = pg_temp.s('ec_cd.profit_ec')
            AND pg_temp.cv(t.profit_withhold_tax_id, pg_temp.s('ec2.company_id')) = pg_temp.s('ec_cd.profit_ec2')
            AND pg_temp.cv(t.vat_goods_withhold_tax_id, pg_temp.s('ec.company_id')) = pg_temp.s('ec_cd.vat_goods_ec')
            AND pg_temp.cv(t.vat_goods_withhold_tax_id, pg_temp.s('ec2.company_id')) = pg_temp.s('ec_cd.vat_goods_ec2')
            AND pg_temp.cv(t.vat_services_withhold_tax_id, pg_temp.s('ec.company_id')) = pg_temp.s('ec_cd.vat_services_ec')
            AND pg_temp.cv(t.vat_services_withhold_tax_id, pg_temp.s('ec2.company_id')) = pg_temp.s('ec_cd.vat_services_ec2')
            AND pg_temp.cv(t.profit_withhold_tax_id, m.res_id::text) IS NULL,
        format('type=%s profit=%s goods=%s services=%s', t.id, t.profit_withhold_tax_id, t.vat_goods_withhold_tax_id, t.vat_services_withhold_tax_id)
    FROM l10n_ec_taxpayer_type t, ir_model_data m
    WHERE t.id = pg_temp.si('ec_cd.taxpayer_id') AND m.module = 'base' AND m.name = 'main_company'
$q$);
SELECT pg_temp.check('EC10', 'l10n_ec_edi: profit withholding tax of the product per EC company, none for the main company', ARRAY['mod:l10n_ec_edi', 'seed:block.ec_cd', 'col:product_template.l10n_ec_withhold_tax_id'], $q$
    SELECT pg_temp.cv(t.l10n_ec_withhold_tax_id, pg_temp.s('ec.company_id')) = pg_temp.s('ec_cd.product_tax_ec')
            AND pg_temp.cv(t.l10n_ec_withhold_tax_id, pg_temp.s('ec2.company_id')) = pg_temp.s('ec_cd.product_tax_ec2')
            AND pg_temp.cv(t.l10n_ec_withhold_tax_id, m.res_id::text) IS NULL,
        format('product=%s value=%s', t.id, t.l10n_ec_withhold_tax_id)
    FROM product_template t, ir_model_data m
    WHERE t.id = pg_temp.si('ec_cd.product_id') AND m.module = 'base' AND m.name = 'main_company'
$q$);

-- Relation tables and ORM defaults: values a script must move before the 18.0 load fills
-- defaults or recomputes them.

SELECT pg_temp.check('SOC' || v.n, format('social_%s: the template and the post keep their 17.0 images and message on the %s fields', v.net, v.net),
    ARRAY['mod:social_' || v.net, 'seed:block.social'], format($q$
    SELECT pg_temp.rel_ids(%1$L, 'social_post_template_id', 'ir_attachment_id', pg_temp.si('social.template_id')) = pg_temp.s('social.template_images')
            AND pg_temp.rel_ids(%2$L, 'social_post_id', 'ir_attachment_id', pg_temp.si('social.post_id')) = pg_temp.s('social.post_images')
            AND t.%3$I = pg_temp.s('social.template_message') AND p.%3$I = pg_temp.s('social.post_message'),
        format('template images=%%s message=%%s post images=%%s message=%%s (17.0: %%s / %%s)',
            pg_temp.rel_ids(%1$L, 'social_post_template_id', 'ir_attachment_id', t.id), t.%3$I,
            pg_temp.rel_ids(%2$L, 'social_post_id', 'ir_attachment_id', p.id), p.%3$I,
            pg_temp.s('social.template_images'), pg_temp.s('social.post_images'))
    FROM social_post_template t, social_post p
    WHERE t.id = pg_temp.si('social.template_id') AND p.id = pg_temp.si('social.post_id')
$q$, 'template_' || v.net || '_image_ids_rel', v.net || '_image_ids_rel', v.net || '_message'))
FROM (VALUES (1, 'facebook'), (2, 'instagram'), (3, 'linkedin'), (4, 'twitter')) v(n, net) ORDER BY v.n;
SELECT pg_temp.check('SOC5', 'social: image_ids stay on the 17.0 relations and every per-network relation has the foreign keys of an ORM relation', ARRAY['mod:social', 'seed:block.social'], $q$
    SELECT pg_temp.rel_ids('ir_attachment_social_post_template_rel', 'social_post_template_id', 'ir_attachment_id', pg_temp.si('social.template_id')) = pg_temp.s('social.template_images')
            AND pg_temp.rel_ids('ir_attachment_social_post_rel', 'social_post_id', 'ir_attachment_id', pg_temp.si('social.post_id')) = pg_temp.s('social.post_images')
            AND count(*) FILTER (WHERE pg_temp.fk_target(r.rel, r.col) IS DISTINCT FROM r.owner
                OR pg_temp.fk_target(r.rel, 'ir_attachment_id') IS DISTINCT FROM 'ir_attachment') = 0,
        format('relations=%s missing or wrong foreign keys: %s', count(*),
            coalesce(string_agg(r.rel, ',') FILTER (WHERE pg_temp.fk_target(r.rel, r.col) IS DISTINCT FROM r.owner
                OR pg_temp.fk_target(r.rel, 'ir_attachment_id') IS DISTINCT FROM 'ir_attachment'), 'none'))
    FROM (SELECT 'template_' || n || '_image_ids_rel', 'social_post_template_id', 'social_post_template' FROM unnest(ARRAY['facebook', 'instagram', 'linkedin', 'twitter']) n
            WHERE pg_temp.installed('social_' || n)
        UNION ALL
        SELECT n || '_image_ids_rel', 'social_post_id', 'social_post' FROM unnest(ARRAY['facebook', 'instagram', 'linkedin', 'twitter']) n
            WHERE pg_temp.installed('social_' || n)) r(rel, col, owner)
$q$);
SELECT pg_temp.check('SOC6', 'social_twitter: the X media and its stream type carry their 18.0 names', ARRAY['mod:social_twitter', 'seed:block.twitter'], $q$
    SELECT pg_temp.en(m.name::text) = 'X' AND pg_temp.en(m.media_description::text) = 'Manage your X accounts and schedule posts'
            AND pg_temp.en(t.name::text) = 'Posts of',
        format('media=%s description=%s stream type=%s (17.0 name %s)', pg_temp.en(m.name::text), pg_temp.en(m.media_description::text),
            pg_temp.en(t.name::text), pg_temp.s('twitter.name17'))
    FROM social_media m, ir_model_data d, social_stream_type t
    WHERE m.id = pg_temp.si('twitter.media') AND d.module = 'social_twitter' AND d.name = 'stream_type_twitter_follow'
        AND t.id = d.res_id
$q$);
SELECT pg_temp.check('PSH1', 'social_push_notifications: the template and the post keep their message as push notification message', ARRAY['mod:social_push_notifications', 'seed:block.push', 'col:social_post.push_notification_message'], $q$
    SELECT t.push_notification_message = 'OUE18 push template' AND p.push_notification_message = 'OUE18 push post',
        format('template=%s post=%s', t.push_notification_message, p.push_notification_message)
    FROM social_post_template t, social_post p
    WHERE t.id = pg_temp.si('push.template') AND p.id = pg_temp.si('push.post')
$q$);

SELECT pg_temp.check('WKS1', 'worksheet: a template of one 17.0 company gets that company, none or several companies stay open to all', ARRAY['mod:worksheet', 'seed:block.wks', 'col:worksheet_template.company_id'], $q$
    SELECT bool_and(coalesce(t.company_id::text, '') = pg_temp.s('wks.' || x.l || '_company')) AND count(t.id) = 3,
        string_agg(format('%s=%s (expected %s)', x.l, coalesce(t.company_id::text, 'all'),
            coalesce(nullif(pg_temp.s('wks.' || x.l || '_company'), ''), 'all')), ' ')
    FROM (VALUES ('none'), ('one'), ('two')) x(l) LEFT JOIN worksheet_template t ON t.id = pg_temp.si('wks.' || x.l || '_id')
$q$);

SELECT pg_temp.check('ACC1', 'account_accountant: deferred revenue method and journal are the 17.0 deferred ones of each company', ARRAY['mod:account_accountant', 'seed:block.acct', 'col:res_company.deferred_revenue_amount_computation_method'], $q$
    SELECT bool_and(coalesce(c.deferred_revenue_amount_computation_method = pg_temp.s('acct.method_' || x.l)
            AND c.deferred_expense_amount_computation_method = pg_temp.s('acct.method_' || x.l)
            AND coalesce(c.deferred_revenue_journal_id::text, '') = pg_temp.s('acct.journal_' || x.l)
            AND coalesce(c.deferred_expense_journal_id::text, '') = pg_temp.s('acct.journal_' || x.l), FALSE)) AND count(c.id) = 3,
        string_agg(format('%s: revenue %s/%s expense %s/%s (17.0 %s/%s)', x.l,
            c.deferred_revenue_amount_computation_method, c.deferred_revenue_journal_id,
            c.deferred_expense_amount_computation_method, c.deferred_expense_journal_id,
            pg_temp.s('acct.method_' || x.l), nullif(pg_temp.s('acct.journal_' || x.l), '')), '; ')
    FROM (VALUES ('a'), ('b'), ('c')) x(l) LEFT JOIN res_company c ON c.id = pg_temp.si('acct.company_' || x.l)
$q$);

SELECT pg_temp.check('PLN1', 'planning: every shift template keeps the end hour 17.0 computed from the company calendar', ARRAY['mod:planning', 'seed:block.plan', 'col:planning_slot_template.end_time'], $q$
    SELECT bool_and(coalesce(abs(t.end_time - pg_temp.s('plan.' || x.l || '_end')::float8) < 0.01, FALSE)) AND count(t.id) = 4,
        string_agg(format('%s: %s-%s, %s day(s) (17.0 end %s, %s day(s))', x.l, t.start_time, t.end_time, t.duration_days,
            pg_temp.s('plan.' || x.l || '_end'), pg_temp.s('plan.' || x.l || '_days')), '; ')
    FROM (VALUES ('t1'), ('t2'), ('t3'), ('t4')) x(l) LEFT JOIN planning_slot_template t ON t.id = pg_temp.si('plan.' || x.l || '_id')
$q$);
SELECT pg_temp.check('PLN2', 'planning: the day span is the number of working days the 17.0 shift touches and passes the 18.0 one-day check', ARRAY['mod:planning', 'seed:block.plan', 'col:planning_slot_template.duration_days'], $q$
    SELECT bool_and(coalesce(t.duration_days = pg_temp.si('plan.' || x.l || '_span') AND (t.end_time >= t.start_time OR t.duration_days > 1), FALSE)) AND count(t.id) = 4,
        string_agg(format('%s: %s day(s), 17.0 span %s, 17.0 duration_days %s', x.l, t.duration_days,
            pg_temp.s('plan.' || x.l || '_span'), pg_temp.s('plan.' || x.l || '_days')), '; ')
    FROM (VALUES ('t1'), ('t2'), ('t3'), ('t4')) x(l) LEFT JOIN planning_slot_template t ON t.id = pg_temp.si('plan.' || x.l || '_id')
$q$);
SELECT pg_temp.check('PLN3', 'planning: a company that let employees unassign themselves keeps it, the other switches shifts', ARRAY['mod:planning', 'seed:plan.unassign_company', 'col:res_company.planning_employee_unavailabilities'], $q$
    SELECT u.planning_employee_unavailabilities = 'unassign' AND s.planning_employee_unavailabilities = 'switch',
        format('unassign company=%s switch company=%s', u.planning_employee_unavailabilities, s.planning_employee_unavailabilities)
    FROM res_company u, res_company s
    WHERE u.id = pg_temp.si('plan.unassign_company') AND s.id = pg_temp.si('plan.switch_company')
$q$);
SELECT pg_temp.check('FCS1', 'project_forecast: a shift template keeps the project 17.0 set for one of its companies', ARRAY['mod:project_forecast', 'seed:block.fcst', 'col:planning_slot_template.project_id'], $q$
    SELECT bool_and(coalesce(t.project_id = pg_temp.si('fcst.project_' || x.l), FALSE)) AND count(t.id) = 2,
        string_agg(format('%s: template %s project %s (expected %s)', x.l, t.id, t.project_id, pg_temp.s('fcst.project_' || x.l)), '; ')
    FROM (VALUES ('a'), ('b')) x(l) LEFT JOIN planning_slot_template t ON t.id = pg_temp.si('fcst.template_' || x.l)
$q$);

SELECT pg_temp.check('BUD1', 'account_budget: the line on a project-plan account keeps it as account_id', ARRAY['mod:account_budget', 'seed:block.bud', 'col:budget_line.account_id'], $q$
    SELECT l.account_id IS NOT DISTINCT FROM pg_temp.si('bud.project_account') AND l.id IS NOT NULL,
        format('line=%s account_id=%s expected %s', l.id, l.account_id, pg_temp.s('bud.project_account'))
    FROM (SELECT pg_temp.si('bud.project_line') AS id) x LEFT JOIN budget_line l ON l.id = x.id
$q$);
SELECT pg_temp.check('BUD2', 'account_budget: lines on another root plan and on its child plan keep their account in that root plan column',
    ARRAY['mod:account_budget', 'seed:block.bud', 'col:budget_line.x_plan' || coalesce(pg_temp.s('bud.other_plan'), '0') || '_id'], format($q$
    SELECT bool_and(coalesce(l.%1$I IS NOT DISTINCT FROM pg_temp.si('bud.' || x.l || '_account') AND l.account_id IS NULL, FALSE)) AND count(l.id) = 2,
        string_agg(format('%%s: line %%s %1$s=%%s account_id=%%s expected %%s', x.l, l.id, l.%1$I, l.account_id,
            pg_temp.s('bud.' || x.l || '_account')), '; ')
    FROM (VALUES ('other'), ('child')) x(l) LEFT JOIN budget_line l ON l.id = pg_temp.si('bud.' || x.l || '_line')
$q$, 'x_plan' || coalesce(pg_temp.s('bud.other_plan'), '0') || '_id'));
SELECT pg_temp.check('BUD3', 'account_budget: confirmed, validated, canceled and done budgets carry the 18.0 state names', ARRAY['mod:account_budget', 'seed:bud.state_confirm', 'tbl:budget_analytic'], $q$
    SELECT bool_and(coalesce(b.state = x.expected, FALSE)) AND count(b.id) = 4
            AND (SELECT count(*) FROM budget_analytic WHERE state IN ('confirm', 'validate', 'cancel')) = 0,
        string_agg(format('%s=%s (expected %s)', x.l, b.state, x.expected), ' ')
    FROM (VALUES ('confirm', 'confirmed'), ('validate', 'done'), ('cancel', 'canceled'), ('done', 'done')) x(l, expected)
    LEFT JOIN budget_analytic b ON b.id = pg_temp.si('bud.state_' || x.l)
$q$);
SELECT pg_temp.check('PAB1', 'project_account_budget: the old demo budget lines are deleted, the other lines of their budget stay', ARRAY['mod:project_account_budget', 'seed:block.pab', 'tbl:budget_line'], $q$
    SELECT (SELECT count(*) FROM budget_line WHERE id = ANY(string_to_array(pg_temp.s('pab.demo_lines'), ',')::integer[])) = 0
            AND (SELECT count(*) FROM ir_model_data WHERE module = 'project_account_budget' AND name LIKE 'crossovered\_budget\_line\_%') = 0
            AND EXISTS (SELECT 1 FROM budget_line WHERE id = pg_temp.si('pab.own_line')),
        format('demo lines left=%s demo xmlids left=%s own line kept=%s',
            (SELECT count(*) FROM budget_line WHERE id = ANY(string_to_array(pg_temp.s('pab.demo_lines'), ',')::integer[])),
            (SELECT count(*) FROM ir_model_data WHERE module = 'project_account_budget' AND name LIKE 'crossovered\_budget\_line\_%'),
            EXISTS (SELECT 1 FROM budget_line WHERE id = pg_temp.si('pab.own_line')))
$q$);

SELECT pg_temp.check('DOC1', 'documents: workspaces without groups become folders open to internal users, with groups closed; all owned by OdooBot', ARRAY['mod:documents', 'seed:block.doc', 'col:documents_document.access_internal'], $q$
    SELECT bool_and(coalesce(d.access_internal = x.expected AND d.owner_id = u.res_id, FALSE)) AND count(d.id) = 4,
        string_agg(format('%s: folder %s internal=%s owner=%s (expected %s)', x.l, d.id, d.access_internal, d.owner_id, x.expected), '; ')
    FROM (VALUES ('open', 'edit'), ('sub', 'edit'), ('restricted', 'none'), ('own', 'none')) x(l, expected)
    LEFT JOIN documents_document d ON d.id = pg_temp.folder_doc('doc.folder_' || x.l)
    JOIN ir_model_data u ON u.module = 'base' AND u.name = 'user_root'
$q$);
SELECT pg_temp.check('DOC2', 'documents: documents follow their 17.0 workspace for internal users', ARRAY['mod:documents', 'seed:block.doc', 'col:documents_document.access_internal'], $q$
    SELECT bool_and(coalesce(d.access_internal = x.expected AND d.folder_id = pg_temp.folder_doc('doc.folder_' || x.f), FALSE)) AND count(d.id) = 6,
        string_agg(format('%s: internal=%s folder=%s (expected %s)', x.l, d.access_internal, d.folder_id, x.expected), '; ')
    FROM (VALUES ('open', 'open', 'edit'), ('sub', 'sub', 'edit'), ('restricted', 'restricted', 'none'),
            ('own_reader', 'own', 'none'), ('own_writer', 'own', 'none'), ('own_admin', 'own', 'none')) x(l, f, expected)
    LEFT JOIN documents_document d ON d.id = pg_temp.si('doc.document_' || x.l)
$q$);
SELECT pg_temp.check('DOC3', 'documents: the 17.0 write group edits and the read group views the restricted folder and its document, nobody else is listed', ARRAY['mod:documents', 'seed:block.doc', 'tbl:documents_access'], $q$
    SELECT pg_temp.doc_access(pg_temp.folder_doc('doc.folder_restricted')) = pg_temp.doc_groups_access()
            AND pg_temp.doc_access(pg_temp.si('doc.document_restricted')) = pg_temp.doc_groups_access(),
        format('folder=%s document=%s expected %s', pg_temp.doc_access(pg_temp.folder_doc('doc.folder_restricted')),
            pg_temp.doc_access(pg_temp.si('doc.document_restricted')), pg_temp.doc_groups_access())
$q$);
SELECT pg_temp.check('DOC4', 'documents: "own documents only" keeps the groups on the folder and lists nobody on the documents (owners edit their own)', ARRAY['mod:documents', 'seed:block.doc', 'tbl:documents_access'], $q$
    SELECT pg_temp.doc_access(pg_temp.folder_doc('doc.folder_own')) = pg_temp.doc_groups_access()
            AND pg_temp.doc_access(pg_temp.si('doc.document_own_reader')) = ''
            AND pg_temp.doc_access(pg_temp.si('doc.document_own_writer')) = ''
            AND pg_temp.doc_access(pg_temp.si('doc.document_own_admin')) = ''
            AND (SELECT owner_id FROM documents_document WHERE id = pg_temp.si('doc.document_own_reader')) = pg_temp.si('doc.user_reader'),
        format('folder=%s documents=%s|%s|%s', pg_temp.doc_access(pg_temp.folder_doc('doc.folder_own')),
            pg_temp.doc_access(pg_temp.si('doc.document_own_reader')), pg_temp.doc_access(pg_temp.si('doc.document_own_writer')),
            pg_temp.doc_access(pg_temp.si('doc.document_own_admin')))
$q$);
SELECT pg_temp.check('DOC5', 'documents: open workspaces and their documents get no member list', ARRAY['mod:documents', 'seed:block.doc', 'tbl:documents_access'], $q$
    SELECT pg_temp.doc_access(pg_temp.folder_doc('doc.folder_open')) = '' AND pg_temp.doc_access(pg_temp.si('doc.document_open')) = ''
            AND pg_temp.doc_access(pg_temp.folder_doc('doc.folder_sub')) = '' AND pg_temp.doc_access(pg_temp.si('doc.document_sub')) = ''
            AND pg_temp.folder_doc('doc.folder_open') IS NOT NULL,
        format('open=%s|%s sub=%s|%s', pg_temp.doc_access(pg_temp.folder_doc('doc.folder_open')), pg_temp.doc_access(pg_temp.si('doc.document_open')),
            pg_temp.doc_access(pg_temp.folder_doc('doc.folder_sub')), pg_temp.doc_access(pg_temp.si('doc.document_sub')))
$q$);
SELECT pg_temp.check('DOC6', 'documents: 17.0 documents administrators keep full access (System Administrator), the other users do not get it', ARRAY['mod:documents', 'seed:block.doc'], $q$
    SELECT bool_and((r.uid IS NOT NULL) = (x.l = 'manager')),
        string_agg(format('%s=%s', x.l, r.uid IS NOT NULL), ' ')
    FROM (VALUES ('manager'), ('writer'), ('reader'), ('outsider')) x(l)
    JOIN ir_model_data g ON g.module = 'documents' AND g.name = 'group_documents_system'
    LEFT JOIN res_groups_users_rel r ON r.gid = g.res_id AND r.uid = pg_temp.si('doc.user_' || x.l)
$q$);
SELECT pg_temp.check('DOC7', 'documents: tags of one name in two 17.0 facets get distinct names and keep their documents', ARRAY['mod:documents', 'seed:doc.tags', 'tbl:documents_tag'], $q$
    SELECT count(t.id) = 2 AND count(DISTINCT t.name ->> 'en_US') = 2 AND bool_and(t.name ->> 'en_US' LIKE 'OUE18 contract%')
            AND EXISTS (SELECT 1 FROM document_tag_rel r WHERE r.documents_document_id = pg_temp.si('doc.request')
                AND r.documents_tag_id = (string_to_array(pg_temp.s('doc.tags'), ',')::integer[])[2]),
        string_agg(t.id || '=' || coalesce(t.name ->> 'en_US', 'missing'), ', ' ORDER BY x.id)
    FROM unnest(string_to_array(pg_temp.s('doc.tags'), ',')::integer[]) x(id) LEFT JOIN documents_tag t ON t.id = x.id
$q$);
SELECT pg_temp.check('DOC8', 'documents: a 17.0 requested document (type empty) is a file document without file', ARRAY['mod:documents', 'seed:doc.request'], $q$
    SELECT d.type = 'binary' AND d.attachment_id IS NULL AND (SELECT count(*) FROM documents_document WHERE type = 'empty') = 0,
        format('document=%s type=%s attachment=%s empty left=%s', d.id, d.type, d.attachment_id,
            (SELECT count(*) FROM documents_document WHERE type = 'empty'))
    FROM documents_document d WHERE d.id = pg_temp.si('doc.request')
$q$);

SELECT pg_temp.check('APR1', 'hr_appraisal: the company template holds the 17.0 feedback templates in every language', ARRAY['mod:hr_appraisal', 'seed:block.appr', 'col:res_company.appraisal_template_id'], $q$
    SELECT t.appraisal_employee_feedback_template = pg_temp.s('appr.company_employee')::jsonb
            AND t.appraisal_manager_feedback_template = pg_temp.s('appr.company_manager')::jsonb,
        format('company=%s template=%s employee=%s', c.id, t.id, t.appraisal_employee_feedback_template)
    FROM res_company c LEFT JOIN hr_appraisal_template t ON t.id = c.appraisal_template_id
    WHERE c.id = pg_temp.si('appr.company_id')
$q$);
SELECT pg_temp.check('APR2', 'hr_appraisal: the department with custom templates gets its own template, the other one its company template', ARRAY['mod:hr_appraisal', 'seed:block.appr', 'col:hr_department.custom_appraisal_template_id'], $q$
    SELECT t.appraisal_employee_feedback_template = pg_temp.s('appr.custom_employee')::jsonb
            AND t.appraisal_manager_feedback_template = pg_temp.s('appr.custom_manager')::jsonb
            AND t.id IS DISTINCT FROM c.appraisal_template_id
            AND p.custom_appraisal_template_id = c.appraisal_template_id,
        format('custom=%s employee=%s plain=%s company template=%s', t.id, t.appraisal_employee_feedback_template,
            p.custom_appraisal_template_id, c.appraisal_template_id)
    FROM hr_department d LEFT JOIN hr_appraisal_template t ON t.id = d.custom_appraisal_template_id,
        hr_department p, res_company c
    WHERE d.id = pg_temp.si('appr.custom_id') AND p.id = pg_temp.si('appr.plain_id') AND c.id = pg_temp.si('appr.company_id')
$q$);
SELECT pg_temp.check('APR3', 'hr_appraisal: no template body is the sanitizer error and every company with 17.0 templates has one', ARRAY['mod:hr_appraisal', 'seed:block.appr', 'tbl:hr_appraisal_template'], $q$
    SELECT (SELECT count(*) FROM hr_appraisal_template
                WHERE appraisal_employee_feedback_template::text LIKE '%Unknown error when sanitizing%'
                    OR appraisal_manager_feedback_template::text LIKE '%Unknown error when sanitizing%') = 0
            AND (SELECT count(*) FROM res_company WHERE appraisal_template_id IS NULL
                AND openupgrade_legacy_18_0_appraisal_employee_feedback_template IS NOT NULL) = 0,
        format('error bodies=%s companies without template=%s', (SELECT count(*) FROM hr_appraisal_template
                WHERE appraisal_employee_feedback_template::text LIKE '%Unknown error when sanitizing%'
                    OR appraisal_manager_feedback_template::text LIKE '%Unknown error when sanitizing%'),
            (SELECT count(*) FROM res_company WHERE appraisal_template_id IS NULL
                AND openupgrade_legacy_18_0_appraisal_employee_feedback_template IS NOT NULL))
$q$);
SELECT pg_temp.check('APS1', 'hr_appraisal_survey: the 17.0 simple manager rules are deleted, the 18.0 employee manager rules exist', ARRAY['mod:hr_appraisal_survey', 'seed:block.apsv'], $q$
    SELECT g.ok AND (SELECT count(*) FROM ir_model_data d JOIN ir_rule r ON r.id = d.res_id
                WHERE d.module = 'hr_appraisal_survey' AND d.model = 'ir.rule' AND d.name LIKE '%\_employee\_manager') >= 3,
        g.actual || format(' employee manager rules=%s', (SELECT count(*) FROM ir_model_data d JOIN ir_rule r ON r.id = d.res_id
                WHERE d.module = 'hr_appraisal_survey' AND d.model = 'ir.rule' AND d.name LIKE '%\_employee\_manager'))
    FROM pg_temp.gone('apsv', 'ir_rule') g
$q$);
SELECT pg_temp.check('APS2', 'hr_appraisal_survey: the survey manager rules 17.0 rewrote keep their ids, stay noupdate and carry the 18.0 survey domain', ARRAY['mod:hr_appraisal_survey', 'seed:block.apsv'], $q$
    SELECT count(*) = 2 AND count(*) FILTER (WHERE d.res_id IS DISTINCT FROM x.res_id OR NOT coalesce(d.noupdate, FALSE)
                OR r.domain_force IS DISTINCT FROM $d$[('survey_id.survey_type', 'in', ('assessment', 'custom', 'live_session', 'survey'))]$d$) = 0,
        string_agg(format('%s=%s noupdate=%s domain=%s', x.name, d.res_id, d.noupdate, r.domain_force), '; ')
    FROM (SELECT split_part(k, '.', 3) AS name, v::integer AS res_id FROM oue18_seed WHERE k LIKE 'apsv\_survey.survey.%') x
    LEFT JOIN ir_model_data d ON d.module = 'survey' AND d.name = x.name
    LEFT JOIN ir_rule r ON r.id = d.res_id
$q$);

SELECT pg_temp.check('PIN1', 'hr_payroll: the input type of a custom attachment type is offered in attachments with its no-end-date default, nothing duplicated', ARRAY['mod:hr_payroll', 'seed:block.payin', 'col:hr_payslip_input_type.available_in_attachments'], $q$
    SELECT count(*) = 1 AND bool_and(t.id = pg_temp.si('payin.ded_input_id') AND t.name = pg_temp.s('payin.ded_input_name')
            AND t.active AND t.available_in_attachments AND t.default_no_end_date),
        string_agg(format('type=%s name=%s active=%s attachments=%s no_end=%s', t.id, t.name, t.active,
            t.available_in_attachments, t.default_no_end_date), '; ')
    FROM hr_payslip_input_type t WHERE t.code = pg_temp.s('payin.ded_code')
$q$);
SELECT pg_temp.check('PIN2', 'hr_payroll: a custom attachment type without input type becomes an active one with its English name', ARRAY['mod:hr_payroll', 'seed:block.payin', 'col:hr_payslip_input_type.active'], $q$
    SELECT count(*) = 1 AND bool_and(t.name = pg_temp.s('payin.lone_name') AND t.active AND t.available_in_attachments
            AND NOT t.default_no_end_date AND NOT t.is_quantity),
        string_agg(format('type=%s name=%s active=%s attachments=%s no_end=%s quantity=%s', t.id, t.name, t.active,
            t.available_in_attachments, t.default_no_end_date, t.is_quantity), '; ')
    FROM hr_payslip_input_type t WHERE t.code = pg_temp.s('payin.lone_code')
$q$);
SELECT pg_temp.check('PIN3', 'hr_payroll: the salary attachment points at the input type of its 17.0 attachment type', ARRAY['mod:hr_payroll', 'seed:block.payin', 'col:hr_salary_attachment.other_input_type_id'], $q$
    SELECT a.other_input_type_id = pg_temp.si('payin.ded_input_id'),
        format('attachment=%s input type=%s expected %s', a.id, a.other_input_type_id, pg_temp.s('payin.ded_input_id'))
    FROM hr_salary_attachment a WHERE a.id = pg_temp.si('payin.attachment_id')
$q$);

SELECT pg_temp.check('DLV1', 'website_delivery_sendcloud: radiuses converted into the unit the settings select, unit set to it', ARRAY['mod:website_delivery_sendcloud', 'seed:block.dlv', 'seed:dlv.s_m_id', 'col:delivery_carrier.sendcloud_locations_radius_unit'], $q$
    SELECT bool_and(coalesce(c.sendcloud_locations_radius_value = pg_temp.si('dlv.' || x.l || '_value') AND c.sendcloud_locations_radius_unit = u.res_id, FALSE)) AND count(c.id) = 3,
        string_agg(format('%s: %s uom %s (expected %s uom %s)', x.l, c.sendcloud_locations_radius_value, c.sendcloud_locations_radius_unit,
            pg_temp.s('dlv.' || x.l || '_value'), u.res_id), '; ')
    FROM (VALUES ('s_m'), ('s_mi'), ('s_km')) x(l) LEFT JOIN delivery_carrier c ON c.id = pg_temp.si('dlv.' || x.l || '_id')
    JOIN ir_model_data u ON u.module = 'uom' AND u.name = CASE pg_temp.s('dlv.system') WHEN 'mi' THEN 'product_uom_mile' ELSE 'product_uom_km' END
$q$);
SELECT pg_temp.check('DLV2', 'website_sale_fedex: radiuses converted into the unit the settings select, unit set to it', ARRAY['mod:website_sale_fedex', 'seed:block.dlv', 'seed:dlv.f_km_id', 'col:delivery_carrier.fedex_locations_radius_unit'], $q$
    SELECT bool_and(coalesce(c.fedex_locations_radius_value = pg_temp.si('dlv.' || x.l || '_value') AND c.fedex_locations_radius_unit = u.res_id, FALSE)) AND count(c.id) = 2,
        string_agg(format('%s: %s uom %s (expected %s uom %s)', x.l, c.fedex_locations_radius_value, c.fedex_locations_radius_unit,
            pg_temp.s('dlv.' || x.l || '_value'), u.res_id), '; ')
    FROM (VALUES ('f_km'), ('f_mi')) x(l) LEFT JOIN delivery_carrier c ON c.id = pg_temp.si('dlv.' || x.l || '_id')
    JOIN ir_model_data u ON u.module = 'uom' AND u.name = CASE pg_temp.s('dlv.system') WHEN 'mi' THEN 'product_uom_mile' ELSE 'product_uom_km' END
$q$);

SELECT pg_temp.check('AU1', 'l10n_au_hr_payroll: the active rules of the regular structure have unique codes and none comes from a 17.0-only rule', ARRAY['mod:l10n_au_hr_payroll', 'seed:block.au'], $q$
    SELECT count(*) > 0 AND count(*) = count(DISTINCT r.code)
            AND count(*) FILTER (WHERE r.id = ANY(string_to_array(pg_temp.s('au.removed_rules'), ',')::integer[])
                OR r.id IN (pg_temp.si('au.rule_gone'), pg_temp.si('au.custom_rule'))) = 0,
        format('active rules=%s distinct codes=%s duplicated=%s', count(*), count(DISTINCT r.code),
            coalesce((SELECT string_agg(code || 'x' || n, ',') FROM (SELECT code, count(*) n FROM hr_salary_rule
                WHERE struct_id = pg_temp.si('au.regular_id') AND active GROUP BY code HAVING count(*) > 1) d), 'none'))
    FROM hr_salary_rule r WHERE r.struct_id = pg_temp.si('au.regular_id') AND r.active
$q$);
SELECT pg_temp.check('AU2', 'l10n_au_hr_payroll: every rule of the nine dropped structures, the custom one included, stays on its 17.0 structure, archived', ARRAY['mod:l10n_au_hr_payroll', 'seed:block.au'], $q$
    SELECT count(*) > 0 AND count(r.id) = count(*) AND bool_and(coalesce(r.struct_id = x.struct AND NOT r.active, FALSE))
            AND count(*) FILTER (WHERE x.id = pg_temp.si('au.custom_rule')) = 1,
        format('17.0 rules=%s found=%s moved=%s active=%s', count(*), count(r.id),
            count(*) FILTER (WHERE r.struct_id <> x.struct), count(*) FILTER (WHERE r.active))
    FROM (SELECT split_part(p, ':', 1)::integer AS id, split_part(p, ':', 2)::integer AS struct
          FROM unnest(string_to_array(pg_temp.s('au.rule_structures'), ',')) p) x
    LEFT JOIN hr_salary_rule r ON r.id = x.id
$q$);
SELECT pg_temp.check('AU3', 'l10n_au_hr_payroll: the nine dropped structures stay, archived, under the Australian structure type, their xmlids kept', ARRAY['mod:l10n_au_hr_payroll', 'seed:block.au'], $q$
    SELECT count(s.id) = 9 AND bool_and(coalesce(NOT s.active AND s.type_id = t.res_id AND d.noupdate, FALSE)),
        format('structures=%s active=%s other type=%s xmlids updatable=%s', count(s.id), count(*) FILTER (WHERE s.active),
            count(*) FILTER (WHERE s.type_id <> t.res_id), count(*) FILTER (WHERE NOT coalesce(d.noupdate, false)))
    FROM unnest(string_to_array(pg_temp.s('au.structures'), ',')::integer[]) x(id)
    LEFT JOIN hr_payroll_structure s ON s.id = x.id
    LEFT JOIN ir_model_data d ON d.model = 'hr.payroll.structure' AND d.res_id = s.id AND d.module = 'l10n_au_hr_payroll'
    JOIN ir_model_data t ON t.module = 'l10n_au_hr_payroll' AND t.name = 'structure_type_schedule_1'
$q$);
SELECT pg_temp.check('AU4', 'l10n_au_hr_payroll: the 17.0 payslip and its lines keep their structure and rules, the dropped regular rule they use is archived', ARRAY['mod:l10n_au_hr_payroll', 'seed:block.au'], $q$
    SELECT p.struct_id = (SELECT struct_id FROM hr_salary_rule WHERE id = pg_temp.si('au.rule_withhold'))
            AND bool_and(coalesce(l.salary_rule_id = pg_temp.si('au.rule_' || x.l), FALSE)) AND count(l.id) = 3
            AND NOT g.active AND g.struct_id = pg_temp.si('au.regular_id'),
        format('payslip struct=%s lines=%s gone rule active=%s struct=%s', p.struct_id, count(l.id), g.active, g.struct_id)
    FROM (VALUES ('withhold'), ('basic'), ('gone')) x(l)
    LEFT JOIN hr_payslip_line l ON l.id = pg_temp.si('au.line_' || x.l),
        hr_payslip p, hr_salary_rule g
    WHERE p.id = pg_temp.si('au.payslip_id') AND g.id = pg_temp.si('au.rule_gone')
    GROUP BY p.struct_id, g.active, g.struct_id
$q$);
SELECT pg_temp.check('AU5', 'l10n_au_hr_payroll: the horticulture contract uses the Australian structure type, the eight dropped types are gone', ARRAY['mod:l10n_au_hr_payroll', 'seed:block.au'], $q$
    SELECT c.structure_type_id = t.res_id
            AND (SELECT count(*) FROM ir_model_data WHERE module = 'l10n_au_hr_payroll' AND model = 'hr.payroll.structure.type'
                AND name <> 'structure_type_schedule_1') = 0,
        format('contract type=%s expected %s dropped type xmlids left=%s', c.structure_type_id, t.res_id,
            (SELECT count(*) FROM ir_model_data WHERE module = 'l10n_au_hr_payroll' AND model = 'hr.payroll.structure.type'
                AND name <> 'structure_type_schedule_1'))
    FROM hr_contract c, ir_model_data t
    WHERE c.id = pg_temp.si('au.contract_id') AND t.module = 'l10n_au_hr_payroll' AND t.name = 'structure_type_schedule_1'
$q$);
SELECT pg_temp.check('AU6', 'l10n_au_hr_payroll: casual loadings are fractions, a percentage imported into 17.0 is divided by 100', ARRAY['mod:l10n_au_hr_payroll', 'seed:au.imported_contract'], $q$
    SELECT f.l10n_au_casual_loading = 0.25 AND i.l10n_au_casual_loading = 0.25,
        format('form=%s imported=%s', f.l10n_au_casual_loading, i.l10n_au_casual_loading)
    FROM hr_contract f, hr_contract i
    WHERE f.id = pg_temp.si('au.contract_id') AND i.id = pg_temp.si('au.imported_contract')
$q$);
SELECT pg_temp.check('AU7', 'l10n_au_hr_payroll: the withholding variation, its rate and the employment basis move from the contract to the employee', ARRAY['mod:l10n_au_hr_payroll', 'seed:au.employee', 'col:hr_employee.l10n_au_withholding_variation'], $q$
    SELECT e.l10n_au_withholding_variation = 'salaries' AND e.l10n_au_withholding_variation_amount = 15.5
            AND e.l10n_au_employment_basis_code = 'P',
        format('variation=%s rate=%s basis=%s', e.l10n_au_withholding_variation, e.l10n_au_withholding_variation_amount,
            e.l10n_au_employment_basis_code)
    FROM hr_employee e WHERE e.id = pg_temp.si('au.employee')
$q$);

-- Modules 18.0 merged or renamed, and modules OpenUpgrade renames away.

SELECT pg_temp.check('MXS1', 'l10n_mx_edi_stock: every 17.0 customs regime keeps its id under l10n_mx_edi_stock, one row per code', ARRAY['mod:l10n_mx_edi_stock', 'seed:block.mxs'], $q$
    SELECT count(*) > 0 AND count(r.id) = count(*) AND bool_and(coalesce(r.code = x.code AND d.module = 'l10n_mx_edi_stock', FALSE))
            AND (SELECT count(*) FROM l10n_mx_edi_customs_regime) = (SELECT count(DISTINCT code) FROM l10n_mx_edi_customs_regime)
            AND (SELECT count(*) FROM l10n_mx_edi_customs_regime) = count(*),
        format('17.0 regimes=%s found=%s rows=%s codes=%s owners=%s', count(*), count(r.id),
            (SELECT count(*) FROM l10n_mx_edi_customs_regime), (SELECT count(DISTINCT code) FROM l10n_mx_edi_customs_regime),
            string_agg(DISTINCT coalesce(d.module, 'none'), ','))
    FROM (SELECT split_part(p, ':', 1) AS code, split_part(p, ':', 2)::integer AS id
          FROM unnest(string_to_array(pg_temp.s('mxs.regimes'), ',')) p) x
    LEFT JOIN l10n_mx_edi_customs_regime r ON r.id = x.id
    LEFT JOIN ir_model_data d ON d.model = 'l10n_mx_edi.customs.regime' AND d.res_id = r.id
$q$);
SELECT pg_temp.check('MXS2', 'l10n_mx_edi_stock: the 3.0 single regime becomes the regimes of a picking without any, 3.1 regimes stay as they were', ARRAY['mod:l10n_mx_edi_stock', 'seed:block.mxs'], $q$
    SELECT s.regimes = pg_temp.s('mxs.imd') AND b.regimes = pg_temp.s('mxs.picking_both_m2m17')
            AND p.l10n_mx_edi_customs_document_type_id = pg_temp.si('mxs.pedimento_type')
            AND p.l10n_mx_edi_pedimento_number = '15  48  3009  0001235',
        format('single=%s (expected %s) both=%s (expected %s) document type=%s pedimento=%s', s.regimes, pg_temp.s('mxs.imd'),
            b.regimes, pg_temp.s('mxs.picking_both_m2m17'), p.l10n_mx_edi_customs_document_type_id, p.l10n_mx_edi_pedimento_number)
    FROM stock_picking p,
        (SELECT string_agg(l10n_mx_edi_customs_regime_id::text, ',' ORDER BY l10n_mx_edi_customs_regime_id) AS regimes
         FROM l10n_mx_edi_customs_regime_stock_picking_rel WHERE stock_picking_id = pg_temp.si('mxs.picking_single')) s,
        (SELECT string_agg(l10n_mx_edi_customs_regime_id::text, ',' ORDER BY l10n_mx_edi_customs_regime_id) AS regimes
         FROM l10n_mx_edi_customs_regime_stock_picking_rel WHERE stock_picking_id = pg_temp.si('mxs.picking_both')) b
    WHERE p.id = pg_temp.si('mxs.picking_single')
$q$);
SELECT pg_temp.check('MXS3', 'l10n_mx_edi_stock: the typed hazardous code becomes the 18.0 catalog entry; code 0 and unknown codes stay empty', ARRAY['mod:l10n_mx_edi_stock', 'seed:block.mxs'], $q$
    SELECT h.code = '1005' AND s.l10n_mx_edi_hazardous_material_code_id IS NULL AND u.l10n_mx_edi_hazardous_material_code_id IS NULL
            AND t.l10n_mx_edi_hazard_package_type = '4H2' AND t.l10n_mx_edi_material_type = '01',
        format('hazard=%s safe=%s unknown=%s package=%s material=%s', coalesce(h.code, 'none'), s.l10n_mx_edi_hazardous_material_code_id,
            u.l10n_mx_edi_hazardous_material_code_id, t.l10n_mx_edi_hazard_package_type, t.l10n_mx_edi_material_type)
    FROM product_template t
    LEFT JOIN l10n_mx_edi_hazardous_material h ON h.id = t.l10n_mx_edi_hazardous_material_code_id,
        product_template s, product_template u
    WHERE t.id = pg_temp.si('mxs.tmpl_hazard') AND s.id = pg_temp.si('mxs.tmpl_safe') AND u.id = pg_temp.si('mxs.tmpl_unknown')
$q$);

SELECT pg_temp.check('BRS1', 'l10n_br_avatax: the 17.0 services cities are the l10n_br cities, kept with their partners, no city twice', ARRAY['mod:l10n_br_avatax', 'seed:block.brs'], $q$
    SELECT p.city_id = pg_temp.si('brs.city_sp') AND d.res_id = pg_temp.si('brs.city_sp')
            AND (SELECT count(*) FROM ir_model_data WHERE model = 'res.city' AND module IN ('l10n_br_avatax_services', 'l10n_br_avatax')) = 0
            AND (SELECT count(*) FROM ir_model_data WHERE model = 'res.city' AND module = 'l10n_br') >= pg_temp.si('brs.cities17')
            AND dup.n = 0,
        format('partner city=%s l10n_br.city_br_001=%s left elsewhere=%s l10n_br cities=%s duplicated=%s', p.city_id, d.res_id,
            (SELECT count(*) FROM ir_model_data WHERE model = 'res.city' AND module IN ('l10n_br_avatax_services', 'l10n_br_avatax')),
            (SELECT count(*) FROM ir_model_data WHERE model = 'res.city' AND module = 'l10n_br'), dup.n)
    FROM res_partner p, ir_model_data d,
        (SELECT count(*) AS n FROM (SELECT 1 FROM res_city WHERE country_id = (SELECT id FROM res_country WHERE code = 'BR')
            GROUP BY state_id, name::text HAVING count(*) > 1) x) dup
    WHERE p.id = pg_temp.si('brs.partner') AND d.module = 'l10n_br' AND d.name = 'city_br_001'
$q$);
SELECT pg_temp.check('BRS2', 'l10n_br_avatax: the service code keeps its city, company and product, the company origin of the product is kept', ARRAY['mod:l10n_br_avatax', 'seed:block.brs'], $q$
    SELECT c.city_id = pg_temp.si('brs.city_rj') AND c.company_id = pg_temp.si('brs.company_id')
            AND (SELECT count(*) FROM l10n_br_service_code_product_template_rel
                 WHERE product_template_id = pg_temp.si('brs.product') AND l10n_br_service_code_id = c.id) = 1
            AND pg_temp.cv(t.l10n_br_property_service_code_origin_id, pg_temp.s('brs.company_id')) = c.id::text,
        format('city=%s company=%s origin=%s', c.city_id, c.company_id, t.l10n_br_property_service_code_origin_id)
    FROM l10n_br_service_code c, product_template t
    WHERE c.id = pg_temp.si('brs.service_code') AND t.id = pg_temp.si('brs.product')
$q$);
SELECT pg_temp.check('BRS3', 'l10n_br_avatax: the services NCM code keeps its id under l10n_br_avatax and exists once', ARRAY['mod:l10n_br_avatax', 'seed:block.brs'], $q$
    SELECT d.res_id = pg_temp.si('brs.ncm') AND (SELECT count(*) FROM l10n_br_ncm_code WHERE code = pg_temp.s('brs.ncm_code')) = 1,
        format('l10n_br_avatax.service_1_01=%s expected %s rows with code %s=%s', d.res_id, pg_temp.s('brs.ncm'), pg_temp.s('brs.ncm_code'),
            (SELECT count(*) FROM l10n_br_ncm_code WHERE code = pg_temp.s('brs.ncm_code')))
    FROM ir_model_data d WHERE d.module = 'l10n_br_avatax' AND d.name = 'service_1_01'
$q$);

SELECT pg_temp.check('RIBA1', 'l10n_it_riba: installed on 18.0 under its name, its module xmlid and the company SIA code kept', ARRAY['mod:l10n_it_riba', 'seed:block.riba'], $q$
    SELECT m.latest_version LIKE '18.0.%' AND c.l10n_it_sia_code = pg_temp.s('riba.sia')
            AND (SELECT count(*) FROM ir_model_data WHERE module = 'base' AND name = 'module_l10n_it_riba') = 1,
        format('state=%s version=%s sia=%s', m.state, m.latest_version, c.l10n_it_sia_code)
    FROM ir_module_module m, res_company c
    WHERE m.name = 'l10n_it_riba' AND c.id = pg_temp.si('riba.company_id')
$q$);
SELECT pg_temp.check('DASH1', 'spreadsheet_dashboard_purchase_stock: its 17.0 purchase dashboard kept, the vendors dashboard of the merged module removed', ARRAY['mod:spreadsheet_dashboard_purchase_stock', 'seed:block.dash'], $q$
    SELECT d.res_id = pg_temp.si('dash.purchase')
            AND NOT EXISTS (SELECT 1 FROM spreadsheet_dashboard WHERE id = pg_temp.si('dash.vendors'))
            AND (SELECT count(*) FROM ir_model_data WHERE module LIKE 'spreadsheet_dashboard_purchase%' AND module <> 'spreadsheet_dashboard_purchase_stock') = 0,
        format('dashboard=%s (expected %s) vendors left=%s other owners=%s', d.res_id, pg_temp.s('dash.purchase'),
            EXISTS (SELECT 1 FROM spreadsheet_dashboard WHERE id = pg_temp.si('dash.vendors')),
            (SELECT count(*) FROM ir_model_data WHERE module LIKE 'spreadsheet_dashboard_purchase%' AND module <> 'spreadsheet_dashboard_purchase_stock'))
    FROM ir_model_data d WHERE d.module = 'spreadsheet_dashboard_purchase_stock' AND d.name = 'spreadsheet_dashboard_purchase'
$q$);

SELECT pg_temp.check('KP1', 'l10n_employment_hero: the company integration settings carry their 17.0 values', ARRAY['mod:l10n_employment_hero', 'seed:block.kp', 'col:res_company.employment_hero_enable'], $q$
    SELECT employment_hero_enable AND employment_hero_identifier = 'OUE18-BIZ-1'
            AND employment_hero_lock_date = pg_temp.s('kp.lock_date')::date AND employment_hero_journal_id = pg_temp.si('kp.journal_id'),
        format('enable=%s business=%s lock=%s journal=%s', employment_hero_enable, employment_hero_identifier,
            employment_hero_lock_date, employment_hero_journal_id)
    FROM res_company WHERE id = pg_temp.si('kp.company_id')
$q$);
SELECT pg_temp.check('KP2', 'l10n_employment_hero: payrun id of the move, account and tax matchings carry their 17.0 values', ARRAY['mod:l10n_employment_hero', 'seed:block.kp', 'col:account_move.employment_hero_payrun_identifier'], $q$
    SELECT m.employment_hero_payrun_identifier = 4242 AND a.employment_hero_account_identifier = 'OUE18-EH-ACC'
            AND t.employment_hero_tax_identifier = 'OUE18-EH-TAX',
        format('payrun=%s account=%s tax=%s', m.employment_hero_payrun_identifier, a.employment_hero_account_identifier,
            t.employment_hero_tax_identifier)
    FROM account_move m, account_account a, account_tax t
    WHERE m.id = pg_temp.si('kp.move_id') AND a.id = pg_temp.si('kp.account_id') AND t.id = pg_temp.si('kp.tax_id')
$q$);
SELECT pg_temp.check('KP3', 'l10n_employment_hero: the 17.0 API key and URL reach the enabled company only', ARRAY['mod:l10n_employment_hero', 'seed:block.kp', 'col:res_company.employment_hero_api_key'], $q$
    SELECT c.employment_hero_api_key = 'oue18-api-key' AND c.employment_hero_base_url = 'https://oue18.example.test/'
            AND o.employment_hero_api_key IS NULL AND o.employment_hero_base_url IS NULL,
        format('company key=%s url=%s other key=%s url=%s', c.employment_hero_api_key, c.employment_hero_base_url,
            o.employment_hero_api_key, o.employment_hero_base_url)
    FROM res_company c, res_company o
    WHERE c.id = pg_temp.si('kp.company_id') AND o.id = pg_temp.si('kp.other_company_id')
$q$);
SELECT pg_temp.check('KP4', 'l10n_employment_hero: the 17.0 payrun cron is the 18.0 cron and calls the 18.0 method, no second cron', ARRAY['mod:l10n_employment_hero', 'seed:block.kp'], $q$
    SELECT d.res_id = pg_temp.si('kp.cron_id') AND s.code = 'model._eh_payroll_cron_fetch_payrun()'
            AND (SELECT count(*) FROM ir_cron c2 JOIN ir_act_server s2 ON s2.id = c2.ir_actions_server_id
                 WHERE s2.code LIKE '%payroll_cron_fetch_payrun%') = 1,
        format('xmlid=%s (expected %s) code=%s crons=%s', d.res_id, pg_temp.s('kp.cron_id'), s.code,
            (SELECT count(*) FROM ir_cron c2 JOIN ir_act_server s2 ON s2.id = c2.ir_actions_server_id
             WHERE s2.code LIKE '%payroll_cron_fetch_payrun%'))
    FROM ir_model_data d, ir_cron c, ir_act_server s
    WHERE d.module = 'l10n_employment_hero' AND d.name = 'employment_hero_sync_cron'
        AND c.id = d.res_id AND s.id = c.ir_actions_server_id
$q$);

-- Modules whose 17.0 data 18.0 changes in place.

SELECT pg_temp.check('IOT1', 'mrp_workorder_iot: every IoT trigger action has its 18.0 key', ARRAY['mod:mrp_workorder_iot', 'seed:block.iot'], $q$
    SELECT count(t.id) = count(*) AND bool_and(coalesce(t.action = x.key, FALSE)) AND count(*) = 16,
        format('triggers=%s found=%s wrong=%s', count(*), count(t.id),
            coalesce(string_agg(t.id || ':' || t.action, ',') FILTER (WHERE t.action IS DISTINCT FROM x.key), 'none'))
    FROM (SELECT split_part(p, ':', 1)::integer AS id, split_part(p, ':', 2) AS key
          FROM unnest(string_to_array(pg_temp.s('iot.triggers'), ',')) p) x
    LEFT JOIN iot_trigger t ON t.id = x.id
$q$);
SELECT pg_temp.check('PRC1', 'pos_pricer: each tag points at the first variant of its 17.0 template, is to be linked again, and references product_product', ARRAY['mod:pos_pricer', 'seed:block.pricer'], $q$
    SELECT s.product_id = pg_temp.si('pricer.variant_single') AND d.product_id = pg_temp.si('pricer.variant_double')
            AND s.pricer_product_to_link AND d.pricer_product_to_link
            AND pg_temp.fk_target('pricer_tag', 'product_id') = 'product_product',
        format('single=%s (expected %s) double=%s (expected %s) to link=%s,%s fk=%s', s.product_id, pg_temp.s('pricer.variant_single'),
            d.product_id, pg_temp.s('pricer.variant_double'), s.pricer_product_to_link, d.pricer_product_to_link,
            pg_temp.fk_target('pricer_tag', 'product_id'))
    FROM pricer_tag s, pricer_tag d
    WHERE s.id = pg_temp.si('pricer.tag_single') AND d.id = pg_temp.si('pricer.tag_double')
$q$);
SELECT pg_temp.check('PRC2', 'pos_pricer: every variant of the two templates has the store of its template and is queued for Pricer', ARRAY['mod:pos_pricer', 'seed:block.pricer'], $q$
    SELECT count(*) = 3 AND bool_and(coalesce(pricer_store_id = pg_temp.si('pricer.store') AND pricer_product_to_create_or_update, FALSE)),
        string_agg(id || ':' || coalesce(pricer_store_id::text, '-') || ':' || coalesce(pricer_product_to_create_or_update::text, '-'), ',' ORDER BY id)
    FROM product_product
    WHERE product_tmpl_id IN (pg_temp.si('pricer.tmpl_single'), pg_temp.si('pricer.tmpl_double'))
$q$);
SELECT pg_temp.check('PAP1', 'pos_restaurant_appointment: each point of sale keeps its first active 17.0 appointment type', ARRAY['mod:pos_restaurant_appointment', 'seed:block.posappt'], $q$
    SELECT s.appointment_type_id = pg_temp.si('posappt.expected_several') AND o.appointment_type_id = pg_temp.si('posappt.expected_one'),
        format('several=%s (expected %s) one=%s (expected %s)', s.appointment_type_id, pg_temp.s('posappt.expected_several'),
            o.appointment_type_id, pg_temp.s('posappt.expected_one'))
    FROM pos_config s, pos_config o
    WHERE s.id = pg_temp.si('posappt.config_several') AND o.id = pg_temp.si('posappt.config_one')
$q$);
SELECT pg_temp.check('PRP1', 'pos_self_order_preparation_display: the take-away flag of the preparation orders is kept', ARRAY['mod:pos_self_order_preparation_display', 'seed:block.prep', 'col:pos_preparation_display_order.pos_takeaway'], $q$
    SELECT t.pos_takeaway AND NOT coalesce(e.pos_takeaway, FALSE),
        format('take-away=%s eat-in=%s', t.pos_takeaway, e.pos_takeaway)
    FROM pos_preparation_display_order t, pos_preparation_display_order e
    WHERE t.id = pg_temp.si('prep.takeaway') AND e.id = pg_temp.si('prep.eat_in')
$q$);
SELECT pg_temp.check('SGN1', 'sign: refused requests and signers are canceled, no refused state is left', ARRAY['mod:sign', 'seed:block.sign'], $q$
    SELECT r.state = 'canceled' AND i.state = 'canceled'
            AND (SELECT count(*) FROM sign_request WHERE state = 'refused') = 0
            AND (SELECT count(*) FROM sign_request_item WHERE state = 'refused') = 0,
        format('request=%s signer=%s refused left=%s/%s', r.state, i.state,
            (SELECT count(*) FROM sign_request WHERE state = 'refused'), (SELECT count(*) FROM sign_request_item WHERE state = 'refused'))
    FROM sign_request r, sign_request_item i
    WHERE r.id = pg_temp.si('sign.refused') AND i.id = pg_temp.si('sign.refused_item')
$q$);
SELECT pg_temp.check('SGN2', 'sign: canceled stays canceled, open and ignored requests stay open with their ignoring signer to sign', ARRAY['mod:sign', 'seed:block.sign'], $q$
    SELECT c.state = 'canceled' AND o.state = 'sent' AND g.state = 'sent' AND gi.state = 'sent',
        format('canceled=%s open=%s ignored=%s ignoring signer=%s', c.state, o.state, g.state, gi.state)
    FROM sign_request c, sign_request o, sign_request g, sign_request_item gi
    WHERE c.id = pg_temp.si('sign.canceled') AND o.id = pg_temp.si('sign.open') AND g.id = pg_temp.si('sign.ignored')
        AND gi.id = pg_temp.si('sign.ignored_item')
$q$);
SELECT pg_temp.check('RSG1', 'sale_renting_sign: the request of a rental order references that order, the other none', ARRAY['mod:sale_renting_sign', 'seed:block.rsign', 'col:sign_request.reference_doc'], $q$
    SELECT l.reference_doc = 'sale.order,' || pg_temp.s('rsign.order') AND u.reference_doc IS NULL,
        format('linked=%s unlinked=%s', l.reference_doc, u.reference_doc)
    FROM sign_request l, sign_request u
    WHERE l.id = pg_temp.si('rsign.linked') AND u.id = pg_temp.si('rsign.unlinked')
$q$);
SELECT pg_temp.check('UTR1', 'hr_payroll_account_iso20022: the payslip UETR is kept as iso20022_uetr', ARRAY['mod:hr_payroll_account_iso20022', 'seed:block.uetr', 'col:hr_payslip.iso20022_uetr'], $q$
    SELECT p.iso20022_uetr = pg_temp.s('uetr.value') AND u.iso20022_uetr IS NULL,
        format('paid=%s unpaid=%s', p.iso20022_uetr, u.iso20022_uetr)
    FROM hr_payslip p, hr_payslip u
    WHERE p.id = pg_temp.si('uetr.paid') AND u.id = pg_temp.si('uetr.unpaid')
$q$);
SELECT pg_temp.check('HRX1', 'hr_recruitment_extract: a candidate takes the OCR state of its latest applicant that sent a CV, the other stays unrequested', ARRAY['mod:hr_recruitment_extract', 'seed:block.hrx', 'col:hr_applicant.candidate_id'], $q$
    SELECT c.extract_state = 'waiting_extraction' AND c.extract_document_uuid = 'oue18-cv-new' AND c.extract_state_processed
            AND n.extract_state = 'no_extract_requested' AND n.extract_document_uuid IS NULL,
        format('candidate=%s state=%s uuid=%s processed=%s other=%s %s', c.id, c.extract_state, c.extract_document_uuid,
            c.extract_state_processed, n.extract_state, n.extract_document_uuid)
    FROM hr_applicant a JOIN hr_candidate c ON c.id = a.candidate_id,
        hr_applicant b JOIN hr_candidate n ON n.id = b.candidate_id
    WHERE a.id = pg_temp.si('hrx.new') AND b.id = pg_temp.si('hrx.none')
$q$);
SELECT pg_temp.check('LU1', 'l10n_lu_hr_payroll: the tax card number is the tax identification number of the employee and of both payslips', ARRAY['mod:l10n_lu_hr_payroll', 'seed:block.lu', 'col:hr_employee.l10n_lu_tax_id_number'], $q$
    SELECT e.l10n_lu_tax_id_number = '29489284' AND o.l10n_lu_tax_id_number = '29489284' AND c.l10n_lu_tax_id_number = '29489284',
        format('employee=%s open payslip=%s closed payslip=%s', e.l10n_lu_tax_id_number, o.l10n_lu_tax_id_number, c.l10n_lu_tax_id_number)
    FROM hr_employee e, hr_payslip o, hr_payslip c
    WHERE e.id = pg_temp.si('lu.employee') AND o.id = pg_temp.si('lu.open_payslip') AND c.id = pg_temp.si('lu.closed_payslip')
$q$);
SELECT pg_temp.check('LU2', 'l10n_lu_hr_payroll: the vehicle package is the VAT-included vehicle benefit, no vehicle allowance', ARRAY['mod:l10n_lu_hr_payroll', 'seed:block.lu', 'col:hr_contract.l10n_lu_bik_vehicle'], $q$
    SELECT l10n_lu_bik_vehicle = 130 AND l10n_lu_bik_vehicle_vat_included AND coalesce(l10n_lu_alw_vehicle, 0) = 0,
        format('benefit=%s vat included=%s allowance=%s', l10n_lu_bik_vehicle, l10n_lu_bik_vehicle_vat_included, l10n_lu_alw_vehicle)
    FROM hr_contract WHERE id = pg_temp.si('lu.contract')
$q$);
SELECT pg_temp.check('LU3', 'l10n_lu_hr_payroll: the monthly travel expense is the daily FD deduction (206.25 / 25)', ARRAY['mod:l10n_lu_hr_payroll', 'seed:block.lu', 'col:hr_employee.l10n_lu_deduction_fd_daily'], $q$
    SELECT l10n_lu_deduction_fd_daily = 8.25, format('daily=%s', l10n_lu_deduction_fd_daily)
    FROM hr_employee WHERE id = pg_temp.si('lu.employee')
$q$);
SELECT pg_temp.check('LU4', 'l10n_lu_hr_payroll: a 17.0 rule 18.0 dropped stays for the payslip lines that use it, archived and no longer updated', ARRAY['mod:l10n_lu_hr_payroll', 'seed:lu.trans_fees_rule'], $q$
    SELECT NOT r.active AND d.noupdate
            AND (SELECT count(*) FROM hr_payslip_line l JOIN hr_salary_rule x ON x.id = l.salary_rule_id
                WHERE l.slip_id = pg_temp.si('lu.computed_payslip')) = pg_temp.si('lu.computed_lines')
            AND EXISTS (SELECT 1 FROM hr_payslip_line WHERE slip_id = pg_temp.si('lu.computed_payslip') AND salary_rule_id = r.id),
        format('rule=%s active=%s xmlid noupdate=%s payslip lines with their rule=%s of %s', r.id, r.active, d.noupdate,
            (SELECT count(*) FROM hr_payslip_line l JOIN hr_salary_rule x ON x.id = l.salary_rule_id
                WHERE l.slip_id = pg_temp.si('lu.computed_payslip')), pg_temp.s('lu.computed_lines'))
    FROM hr_salary_rule r
    LEFT JOIN ir_model_data d ON d.model = 'hr.salary.rule' AND d.res_id = r.id AND d.module = 'l10n_lu_hr_payroll'
    WHERE r.id = pg_temp.si('lu.trans_fees_rule')
$q$);
SELECT pg_temp.check('LU5', 'l10n_lu_hr_payroll: the total allowances rule 17.0 shipped archived is active, so deductions lower the taxable amount', ARRAY['mod:l10n_lu_hr_payroll', 'seed:block.lu'], $q$
    SELECT r.active AND r.code = 'TOTAL_ALLOWANCES', format('rule=%s code=%s active=%s', r.id, r.code, r.active)
    FROM ir_model_data d JOIN hr_salary_rule r ON r.id = d.res_id
    WHERE d.module = 'l10n_lu_hr_payroll' AND d.name = 'l10n_lu_employees_total_allowance' AND d.model = 'hr.salary.rule'
$q$);
SELECT pg_temp.check('AUS1', 'l10n_au_hr_payroll_account: a line without account gets the employee account at its payee, a set account is kept', ARRAY['mod:l10n_au_hr_payroll_account', 'seed:block.ausuper'], $q$
    SELECT m.super_account_id = pg_temp.si('ausuper.account') AND s.super_account_id = pg_temp.si('ausuper.account'),
        format('member line=%s set line=%s expected %s', m.super_account_id, s.super_account_id, pg_temp.s('ausuper.account'))
    FROM l10n_au_super_stream_line m, l10n_au_super_stream_line s
    WHERE m.id = pg_temp.si('ausuper.line_member') AND s.id = pg_temp.si('ausuper.line_set')
$q$);
SELECT pg_temp.check('AUS2', 'l10n_au_hr_payroll_account: a line whose employee has no account at its payee gets one archived account there', ARRAY['mod:l10n_au_hr_payroll_account', 'seed:block.ausuper'], $q$
    SELECT a.fund_id = pg_temp.si('ausuper.other_fund') AND a.employee_id = pg_temp.si('ausuper.employee') AND NOT a.account_active
            AND a.date_from = pg_temp.s('ausuper.payslip_from')::date
            AND (SELECT count(*) FROM l10n_au_super_account WHERE employee_id = pg_temp.si('ausuper.employee')) = 2,
        format('account=%s fund=%s active=%s from=%s employee accounts=%s', a.id, a.fund_id, a.account_active, a.date_from,
            (SELECT count(*) FROM l10n_au_super_account WHERE employee_id = pg_temp.si('ausuper.employee')))
    FROM l10n_au_super_stream_line l JOIN l10n_au_super_account a ON a.id = l.super_account_id
    WHERE l.id = pg_temp.si('ausuper.line_other')
$q$);
SELECT pg_temp.check('AUS3', 'l10n_au_hr_payroll_account: no SuperStream line without account, the column is NOT NULL', ARRAY['mod:l10n_au_hr_payroll_account', 'seed:block.ausuper'], $q$
    SELECT (SELECT count(*) FROM l10n_au_super_stream_line WHERE super_account_id IS NULL) = 0 AND c.is_nullable = 'NO',
        format('lines without account=%s nullable=%s', (SELECT count(*) FROM l10n_au_super_stream_line WHERE super_account_id IS NULL),
            c.is_nullable)
    FROM information_schema.columns c
    WHERE c.table_schema = current_schema() AND c.table_name = 'l10n_au_super_stream_line' AND c.column_name = 'super_account_id'
$q$);
SELECT pg_temp.check('GST1', 'l10n_in_reports_gstr: a company in production for GST returns or e-invoicing stays in production, the other not', ARRAY['mod:l10n_in_reports_gstr', 'seed:block.gstr'], $q$
    SELECT g.l10n_in_edi_production_env AND e.l10n_in_edi_production_env AND NOT coalesce(n.l10n_in_edi_production_env, FALSE),
        format('gstr only=%s edi only=%s none=%s', g.l10n_in_edi_production_env, e.l10n_in_edi_production_env, n.l10n_in_edi_production_env)
    FROM res_company g, res_company e, res_company n
    WHERE g.id = pg_temp.si('gstr.gstr') AND e.id = pg_temp.si('gstr.edi') AND n.id = pg_temp.si('gstr.none')
$q$);

-- Accounting.

SELECT pg_temp.check('ASS1', 'account_asset: the asset model of an account is its one asset model in 18.0, an account without model has none', ARRAY['mod:account_asset', 'seed:block.asset', 'tbl:account_account_account_asset_rel'], $q$
    SELECT pg_temp.rel_ids('account_account_account_asset_rel', 'account_account_id', 'account_asset_id', pg_temp.si('asset.account_linked')) = pg_temp.s('asset.model')
            AND pg_temp.rel_ids('account_account_account_asset_rel', 'account_account_id', 'account_asset_id', pg_temp.si('asset.account_plain')) = '',
        format('linked=%s (expected %s) plain=%s',
            pg_temp.rel_ids('account_account_account_asset_rel', 'account_account_id', 'account_asset_id', pg_temp.si('asset.account_linked')),
            pg_temp.s('asset.model'),
            pg_temp.rel_ids('account_account_account_asset_rel', 'account_account_id', 'account_asset_id', pg_temp.si('asset.account_plain')))
$q$);
SELECT pg_temp.check('FLT1', 'account_asset_fleet: the asset bought for a vehicle stores that vehicle, the other asset none', ARRAY['mod:account_asset_fleet', 'seed:block.fleet', 'col:account_asset.vehicle_id'], $q$
    SELECT a.vehicle_id = pg_temp.si('fleet.vehicle') AND p.vehicle_id IS NULL,
        format('asset=%s vehicle=%s (expected %s) plain=%s', a.id, a.vehicle_id, pg_temp.s('fleet.vehicle'), p.vehicle_id)
    FROM account_asset a, account_asset p
    WHERE a.id = pg_temp.si('fleet.asset') AND p.id = pg_temp.si('fleet.plain')
$q$);
SELECT pg_temp.check('ICR1', 'account_inter_company_rules: a company that synchronized invoices generates bills and refunds, the other not', ARRAY['mod:account_inter_company_rules', 'seed:block.icr', 'col:res_company.intercompany_generate_bills_refund'], $q$
    SELECT b.intercompany_generate_bills_refund AND NOT coalesce(n.intercompany_generate_bills_refund, FALSE),
        format('synchronized=%s not=%s', b.intercompany_generate_bills_refund, n.intercompany_generate_bills_refund)
    FROM res_company b, res_company n
    WHERE b.id = pg_temp.si('icr.bills') AND n.id = pg_temp.si('icr.none')
$q$);
SELECT pg_temp.check('SPI1', 'sale_purchase_inter_company_rules: sale, purchase and both synchronizations become the matching order switches', ARRAY['mod:sale_purchase_inter_company_rules', 'seed:block.spicr', 'col:res_company.intercompany_generate_sales_orders'], $q$
    SELECT bool_and(coalesce(c.intercompany_generate_sales_orders, FALSE) = x.sales
            AND coalesce(c.intercompany_generate_purchase_orders, FALSE) = x.purchases) AND count(c.id) = 3,
        string_agg(format('%s: sales=%s purchases=%s', x.l, c.intercompany_generate_sales_orders, c.intercompany_generate_purchase_orders), '; ')
    FROM (VALUES ('sale', TRUE, FALSE), ('purchase', FALSE, TRUE), ('sale_purchase', TRUE, TRUE)) x(l, sales, purchases)
    LEFT JOIN res_company c ON c.id = pg_temp.si('spicr.' || x.l)
$q$);
SELECT pg_temp.check('SPI2', 'sale_purchase_inter_company_rules: automatic validation of generated orders becomes the posted document state, only with an order rule', ARRAY['mod:sale_purchase_inter_company_rules', 'seed:spicr.bills_auto.state', 'col:res_company.intercompany_document_state'], $q$
    SELECT bool_and(coalesce(c.intercompany_document_state = pg_temp.s('spicr.' || x.l || '.state'), FALSE)) AND count(c.id) = 4,
        string_agg(format('%s=%s (expected %s)', x.l, c.intercompany_document_state, pg_temp.s('spicr.' || x.l || '.state')), '; ')
    FROM (VALUES ('sale'), ('purchase'), ('sale_purchase'), ('bills_auto')) x(l)
    LEFT JOIN res_company c ON c.id = pg_temp.si('spicr.' || x.l)
$q$);
SELECT pg_temp.check('ISO1', 'account_iso20022: the SEPA identification of the company and the LEI of the partner carry their 17.0 values', ARRAY['mod:account_iso20022', 'seed:block.iso', 'col:res_company.iso20022_orgid_id'], $q$
    SELECT c.iso20022_orgid_id = 'OUE18ORGID' AND c.iso20022_orgid_issr = 'KBO-BCE'
            AND c.iso20022_initiating_party_name = 'OUE18 Initiator' AND p.iso20022_lei = '5493001KJTIIGC8Y1R12',
        format('orgid=%s issuer=%s party=%s lei=%s', c.iso20022_orgid_id, c.iso20022_orgid_issr, c.iso20022_initiating_party_name, p.iso20022_lei)
    FROM res_company c, res_partner p
    WHERE c.id = pg_temp.si('iso.company') AND p.id = pg_temp.si('iso.partner')
$q$);
SELECT pg_temp.check('ISO2', 'account_iso20022: the Swedish and Swiss pain versions become the generic one, ISO 20022 the 09 version, others stay', ARRAY['mod:account_iso20022', 'seed:block.iso'], $q$
    SELECT bool_and(coalesce(j.sepa_pain_version = x.expected, FALSE)) AND count(j.id) = 4,
        string_agg(format('%s=%s (expected %s)', x.v, j.sepa_pain_version, x.expected), '; ')
    FROM (VALUES ('pain.001.001.03.se', 'pain.001.001.03'), ('pain.001.001.03.ch.02', 'pain.001.001.03'),
            ('iso_20022', 'pain.001.001.09'), ('pain.001.001.03.de', 'pain.001.001.03.de')) x(v, expected)
    LEFT JOIN account_journal j ON j.id = pg_temp.si('iso.journal.' || x.v)
$q$);
SELECT pg_temp.check('ISO3', 'account_iso20022: the payment keeps its UETR as iso20022_uetr', ARRAY['mod:account_iso20022', 'seed:block.iso', 'col:account_payment.iso20022_uetr'], $q$
    SELECT p.iso20022_uetr = pg_temp.s('iso.uetr'), format('payment=%s uetr=%s', p.id, p.iso20022_uetr)
    FROM account_payment p WHERE p.id = pg_temp.si('iso.payment')
$q$);
SELECT pg_temp.check('ISO4', 'account_iso20022: the batch keeps its batch booking choice and has the charge bearer of its payment method', ARRAY['mod:account_iso20022', 'seed:block.iso', 'col:account_batch_payment.iso20022_batch_booking'], $q$
    SELECT NOT b.iso20022_batch_booking
            AND b.iso20022_charge_bearer = CASE WHEN m.code = 'sepa_ct' THEN 'SLEV' ELSE 'SHAR' END,
        format('batch=%s booking=%s method=%s bearer=%s', b.id, b.iso20022_batch_booking, m.code, b.iso20022_charge_bearer)
    FROM account_batch_payment b LEFT JOIN account_payment_method m ON m.id = b.payment_method_id
    WHERE b.id = pg_temp.si('iso.batch')
$q$);
SELECT pg_temp.check('REP1', 'account_reports: the report footnote is an annotation of the same report line with its text', ARRAY['mod:account_reports', 'seed:block.rep', 'tbl:account_report_annotation'], $q$
    SELECT a.report_id = pg_temp.si('rep.report') AND a.line_id = 'oue18-line' AND a.text = 'OUE18 footnote',
        format('annotation=%s report=%s line=%s text=%s', a.id, a.report_id, a.line_id, a.text)
    FROM account_report_annotation a WHERE a.id = pg_temp.si('rep.footnote')
$q$);
SELECT pg_temp.check('REP2', 'account_reports: a last_* opening filter is the previous_* one of 18.0, none is left', ARRAY['mod:account_reports', 'seed:block.rep'], $q$
    SELECT r.default_opening_date_filter = 'previous_quarter'
            AND (SELECT count(*) FROM account_report WHERE default_opening_date_filter LIKE 'last\_%') = 0,
        format('report=%s filter=%s last_* left=%s', r.id, r.default_opening_date_filter,
            (SELECT count(*) FROM account_report WHERE default_opening_date_filter LIKE 'last\_%'))
    FROM account_report r WHERE r.id = pg_temp.si('rep.custom')
$q$);
SELECT pg_temp.check('SDD1', 'account_sepa_direct_debit: the payment collected by direct debit carries its mandate, the other none', ARRAY['mod:account_sepa_direct_debit', 'seed:block.sdd', 'col:account_payment.sdd_mandate_id'], $q$
    SELECT p.sdd_mandate_id = pg_temp.si('sdd.mandate') AND o.sdd_mandate_id IS NULL,
        format('payment=%s mandate=%s (expected %s) other=%s', p.id, p.sdd_mandate_id, pg_temp.s('sdd.mandate'), o.sdd_mandate_id)
    FROM account_payment p, account_payment o
    WHERE p.id = pg_temp.si('sdd.payment') AND o.id = pg_temp.si('sdd.other')
$q$);

-- Services and productivity.

SELECT pg_temp.check('APT1', 'appointment: manual confirmation of resource bookings keeps its 17.0 value under the 18.0 name', ARRAY['mod:appointment', 'seed:block.appt', 'col:appointment_type.appointment_manual_confirmation'], $q$
    SELECT m.appointment_manual_confirmation AND NOT coalesce(a.appointment_manual_confirmation, FALSE),
        format('manual=%s auto=%s', m.appointment_manual_confirmation, a.appointment_manual_confirmation)
    FROM appointment_type m, appointment_type a
    WHERE m.id = pg_temp.si('appt.manual') AND a.id = pg_temp.si('appt.auto')
$q$);
SELECT pg_temp.check('APT2', 'appointment: the 17.0 onboarding steps and panel are deleted', ARRAY['mod:appointment', 'seed:block.appt'], $q$
    SELECT g.ok AND NOT EXISTS (SELECT 1 FROM onboarding_onboarding_step s
                WHERE s.id IN (SELECT v::integer FROM oue18_seed WHERE k LIKE 'appt.appointment.%step'))
            AND NOT EXISTS (SELECT 1 FROM onboarding_onboarding o
                WHERE o.id = pg_temp.si('appt.appointment.onboarding_onboarding_appointment')),
        g.actual
    FROM pg_temp.gone('appt', NULL) g
$q$);
SELECT pg_temp.check('APC1', 'appointment_crm: leads keep the Appointment tag 17.0 gave them, the tag is no longer module data', ARRAY['mod:appointment_crm', 'seed:block.apptcrm'], $q$
    SELECT EXISTS (SELECT 1 FROM crm_tag_rel r WHERE r.lead_id = pg_temp.si('apptcrm.lead') AND r.tag_id = pg_temp.si('apptcrm.tag'))
            AND t.name ->> 'en_US' = 'Appointment'
            AND NOT EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'appointment_crm' AND name = 'appointment_crm_tag'),
        format('lead tagged=%s tag=%s xmlid left=%s',
            EXISTS (SELECT 1 FROM crm_tag_rel r WHERE r.lead_id = pg_temp.si('apptcrm.lead') AND r.tag_id = pg_temp.si('apptcrm.tag')),
            coalesce(t.name ->> 'en_US', 'deleted'),
            EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'appointment_crm' AND name = 'appointment_crm_tag'))
    FROM (SELECT pg_temp.si('apptcrm.tag') AS id) x LEFT JOIN crm_tag t ON t.id = x.id
$q$);
SELECT pg_temp.check('APV1', 'approvals: the 17.0 approval request rules are deleted', ARRAY['mod:approvals', 'seed:block.approvals'], $q$
    SELECT * FROM pg_temp.gone('approvals', 'ir_rule')
$q$);
SELECT pg_temp.check('FDK1', 'frontdesk: each visitor belongs to the company of its station', ARRAY['mod:frontdesk', 'seed:block.fd', 'col:frontdesk_visitor.company_id'], $q$
    SELECT bool_and(coalesce(v.company_id = pg_temp.si('fd.company_' || x.l), FALSE)) AND count(v.id) = 2,
        string_agg(format('%s: visitor %s company %s (expected %s)', x.l, v.id, v.company_id, pg_temp.s('fd.company_' || x.l)), '; ')
    FROM (VALUES ('a'), ('b')) x(l) LEFT JOIN frontdesk_visitor v ON v.id = pg_temp.si('fd.visitor_' || x.l)
$q$);
SELECT pg_temp.check('HLP1', 'helpdesk: the list, kanban and activity views of the 7-day success action keep their records under the 18.0 xmlids', ARRAY['mod:helpdesk', 'seed:block.hd'], $q$
    SELECT bool_and(coalesce(d.res_id = pg_temp.si('hd.helpdesk.helpdesk_ticket_action_7dayssuccess_' || x.v), FALSE))
            AND NOT EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'helpdesk'
                AND name IN ('helpdesk_ticket_action_7dayssuccess_tree', 'helpdesk_ticket_action_7dayssuccess_kanban',
                    'helpdesk_ticket_action_7dayssuccess_activity')),
        string_agg(format('%s=%s (17.0 %s)', x.v, d.res_id, pg_temp.s('hd.helpdesk.helpdesk_ticket_action_7dayssuccess_' || x.v)), ' ')
    FROM (VALUES ('tree'), ('kanban'), ('activity')) x(v)
    LEFT JOIN ir_model_data d ON d.module = 'helpdesk' AND d.name = 'helpdesk_ticket_action_7days_success_' || x.v
$q$);
SELECT pg_temp.check('FSR1', 'industry_fsm, industry_fsm_report: the 17.0 task report template and report are the industry_fsm ones of 18.0, the report still attached', ARRAY['mod:industry_fsm', 'mod:industry_fsm_report', 'seed:block.fsmr'], $q$
    SELECT t.res_id = pg_temp.si('fsmr.template') AND r.res_id = pg_temp.si('fsmr.report')
            AND EXISTS (SELECT 1 FROM mail_template_ir_actions_report_rel
                WHERE mail_template_id = t.res_id AND ir_actions_report_id = r.res_id)
            AND (SELECT count(*) FROM ir_model_data WHERE module = 'industry_fsm_report'
                AND name IN ('mail_template_data_task_report', 'task_custom_report')) = 0,
        format('template=%s (17.0 %s) report=%s (17.0 %s) attached=%s', t.res_id, pg_temp.s('fsmr.template'), r.res_id,
            pg_temp.s('fsmr.report'), EXISTS (SELECT 1 FROM mail_template_ir_actions_report_rel
                WHERE mail_template_id = t.res_id AND ir_actions_report_id = r.res_id))
    FROM (SELECT 1) x
    LEFT JOIN ir_model_data t ON t.module = 'industry_fsm' AND t.name = 'mail_template_data_task_report'
    LEFT JOIN ir_model_data r ON r.module = 'industry_fsm' AND r.name = 'task_custom_report'
$q$);
SELECT pg_temp.check('IOC1', 'iot: the 17.0 channel table is dropped and the websocket channel name is kept', ARRAY['mod:iot', 'seed:block.iotch'], $q$
    SELECT to_regclass('iot_channel') IS NULL AND p.value = pg_temp.s('iotch.name'),
        format('table=%s channel=%s (17.0 %s)', coalesce(to_regclass('iot_channel')::text, 'none'), p.value, pg_temp.s('iotch.name'))
    FROM (SELECT 1) x LEFT JOIN ir_config_parameter p ON p.key = 'iot.ws_channel'
$q$);
SELECT pg_temp.check('MPS1', 'mrp_mps: the number of columns of each company''s period is kept for that period, the other periods take the defaults', ARRAY['mod:mrp_mps', 'seed:block.mps', 'col:res_company.manufacturing_period_to_display_week'], $q$
    SELECT a.manufacturing_period_to_display_week = 8 AND a.manufacturing_period_to_display_month = 12
            AND b.manufacturing_period_to_display_day = 20 AND b.manufacturing_period_to_display_week = 12
            AND c.manufacturing_period_to_display_month = 6 AND c.manufacturing_period_to_display_day = 30,
        format('week company=%s/%s day company=%s/%s month company=%s/%s',
            a.manufacturing_period_to_display_week, a.manufacturing_period_to_display_month,
            b.manufacturing_period_to_display_day, b.manufacturing_period_to_display_week,
            c.manufacturing_period_to_display_month, c.manufacturing_period_to_display_day)
    FROM res_company a, res_company b, res_company c
    WHERE a.id = pg_temp.si('mps.company_a') AND b.id = pg_temp.si('mps.company_b') AND c.id = pg_temp.si('mps.company_c')
$q$);
SELECT pg_temp.check('SHT1', 'spreadsheet_edition: revisions keep their uuid and point at their parent revision, the first one at none', ARRAY['mod:spreadsheet_edition', 'seed:block.sheet', 'col:spreadsheet_revision.revision_uuid'], $q$
    SELECT r1.revision_uuid = 'oue18-rev-1' AND r1.parent_revision_id IS NULL
            AND r2.revision_uuid = 'oue18-rev-2' AND r2.parent_revision_id = r1.id
            AND r3.revision_uuid = 'oue18-rev-3' AND r3.parent_revision_id = r2.id,
        format('1=%s/%s 2=%s/%s 3=%s/%s', r1.revision_uuid, r1.parent_revision_id, r2.revision_uuid, r2.parent_revision_id,
            r3.revision_uuid, r3.parent_revision_id)
    FROM spreadsheet_revision r1, spreadsheet_revision r2, spreadsheet_revision r3
    WHERE r1.id = pg_temp.si('sheet.rev_1') AND r2.id = pg_temp.si('sheet.rev_2') AND r3.id = pg_temp.si('sheet.rev_3')
$q$);
SELECT pg_temp.check('VOP1', 'voip: the default provider carries the 17.0 PBX settings', ARRAY['mod:voip', 'seed:block.voip', 'tbl:voip_provider'], $q$
    SELECT p.ws_server = 'wss://oue18.example.test:7443' AND p.pbx_ip = 'pbx.oue18.example.test' AND p.mode = 'prod',
        format('provider=%s ws=%s pbx=%s mode=%s', p.id, p.ws_server, p.pbx_ip, p.mode)
    FROM ir_model_data d JOIN voip_provider p ON p.id = d.res_id
    WHERE d.module = 'voip' AND d.name = 'default_voip_provider'
$q$);
SELECT pg_temp.check('VOP2', 'voip: the settings of a 17.0 user point at the default provider', ARRAY['mod:voip', 'seed:block.voip', 'col:res_users_settings.voip_provider_id'], $q$
    SELECT s.voip_provider_id = d.res_id, format('settings=%s provider=%s default=%s', s.id, s.voip_provider_id, d.res_id)
    FROM res_users_settings s, ir_model_data d
    WHERE s.id = pg_temp.si('voip.settings') AND d.module = 'voip' AND d.name = 'default_voip_provider'
$q$);
SELECT pg_temp.check('STU1', 'web_studio: the approval rule keeps its group as approval group', ARRAY['mod:web_studio', 'seed:block.studio', 'col:studio_approval_rule.approval_group_id'], $q$
    SELECT r.approval_group_id = pg_temp.si('studio.group'), format('rule=%s group=%s (expected %s)', r.id, r.approval_group_id, pg_temp.s('studio.group'))
    FROM studio_approval_rule r WHERE r.id = pg_temp.si('studio.rule')
$q$);
SELECT pg_temp.check('STU2', 'web_studio: the approval rule keeps its 17.0 users to notify in the 18.0 relation', ARRAY['mod:web_studio', 'seed:studio.notified', 'tbl:approval_rule_users_to_notify_rel'], $q$
    SELECT coalesce(string_agg(n.res_users_id::text, ',' ORDER BY n.res_users_id), '') = pg_temp.s('studio.notified'),
        format('rule=%s users=%s (expected %s)', pg_temp.s('studio.rule'),
            coalesce(string_agg(n.res_users_id::text, ',' ORDER BY n.res_users_id), 'none'), pg_temp.s('studio.notified'))
    FROM (SELECT pg_temp.si('studio.rule') AS id) x
    LEFT JOIN approval_rule_users_to_notify_rel n ON n.studio_approval_rule_id = x.id
$q$);
SELECT pg_temp.check('WAP1', 'whatsapp: a conversation''s last customer message is its last message from the WhatsApp partner, not the record message it came from', ARRAY['mod:whatsapp', 'seed:block.wa', 'col:discuss_channel.last_wa_mail_message_id'], $q$
    SELECT c.last_wa_mail_message_id = pg_temp.si('wa.last_customer'),
        format('channel=%s last customer message=%s (expected %s, record message %s)', c.id, c.last_wa_mail_message_id,
            pg_temp.s('wa.last_customer'), pg_temp.s('wa.origin'))
    FROM discuss_channel c WHERE c.id = pg_temp.si('wa.channel')
$q$);

-- HR and payroll.

SELECT pg_temp.check('SAL1', 'hr_contract_salary: a benefit whose description was hidden when not taken is no longer always shown, the other is', ARRAY['mod:hr_contract_salary', 'seed:block.salary', 'col:hr_contract_salary_benefit.always_show_description'], $q$
    SELECT NOT h.always_show_description AND s.always_show_description,
        format('hidden=%s shown=%s', h.always_show_description, s.always_show_description)
    FROM hr_contract_salary_benefit h, hr_contract_salary_benefit s
    WHERE h.id = pg_temp.si('salary.benefit_hidden') AND s.id = pg_temp.si('salary.benefit_shown')
$q$);
SELECT pg_temp.check('SAL2', 'hr_contract_salary: benefit values keep their description choice and a red color as red highlight', ARRAY['mod:hr_contract_salary', 'seed:block.salary', 'col:hr_contract_salary_benefit_value.selector_highlight'], $q$
    SELECT r.selector_highlight = 'red' AND NOT r.always_show_description
            AND g.selector_highlight = 'none' AND g.always_show_description,
        format('red=%s/%s green=%s/%s', r.selector_highlight, r.always_show_description, g.selector_highlight, g.always_show_description)
    FROM hr_contract_salary_benefit_value r, hr_contract_salary_benefit_value g
    WHERE r.id = pg_temp.si('salary.value_red') AND g.id = pg_temp.si('salary.value_green')
$q$);
SELECT pg_temp.check('REF1', 'hr_referral: the 17.0 points manager rule is deleted', ARRAY['mod:hr_referral', 'seed:block.ref'], $q$
    SELECT * FROM pg_temp.gone('ref', 'ir_rule')
$q$);
SELECT pg_temp.check('KE1', 'l10n_ke_hr_payroll: the Kenyan disability exemption is the employee''s disabled flag', ARRAY['mod:l10n_ke_hr_payroll', 'seed:block.ke', 'col:hr_employee.disabled'], $q$
    SELECT d.disabled AND NOT coalesce(a.disabled, FALSE), format('disabled=%s able=%s', d.disabled, a.disabled)
    FROM hr_employee d, hr_employee a
    WHERE d.id = pg_temp.si('ke.disabled') AND a.id = pg_temp.si('ke.able')
$q$);
SELECT pg_temp.check('CH1', 'l10n_ch_hr_payroll: every insurance keeps its Swissdec institution, the code as code and the name as company', ARRAY['mod:l10n_ch_hr_payroll', 'seed:block.ch'], $q$
    SELECT bool_and(coalesce(x.code = pg_temp.s('ch.' || x.l || '_code') AND x.company = pg_temp.s('ch.' || x.l || '_name'), FALSE))
            AND count(x.code) = 5,
        string_agg(format('%s: code=%s company=%s (17.0 %s %s)', x.l, x.code, x.company,
            pg_temp.s('ch.' || x.l || '_code'), pg_temp.s('ch.' || x.l || '_name')), '; ')
    FROM (SELECT 'social' AS l, insurance_code AS code, insurance_company AS company FROM l10n_ch_social_insurance WHERE id = pg_temp.si('ch.social')
        UNION ALL SELECT 'accident', insurance_code, insurance_company FROM l10n_ch_accident_insurance WHERE id = pg_temp.si('ch.accident')
        UNION ALL SELECT 'additional', insurance_code, insurance_company FROM l10n_ch_additional_accident_insurance WHERE id = pg_temp.si('ch.additional')
        UNION ALL SELECT 'fund', insurance_code, insurance_company FROM l10n_ch_compensation_fund WHERE id = pg_temp.si('ch.fund')
        UNION ALL SELECT 'sickness', insurance_code, insurance_company FROM l10n_ch_sickness_insurance WHERE id = pg_temp.si('ch.sickness')) x
$q$);
SELECT pg_temp.check('CBX1', 'l10n_be_codabox: a company marked connected without token is disconnected, one with a token stays connected', ARRAY['mod:l10n_be_codabox', 'seed:block.cbx'], $q$
    SELECT NOT s.l10n_be_codabox_is_connected AND t.l10n_be_codabox_is_connected,
        format('without token=%s with token=%s', s.l10n_be_codabox_is_connected, t.l10n_be_codabox_is_connected)
    FROM res_company s, res_company t
    WHERE s.id = pg_temp.si('cbx.stale') AND t.id = pg_temp.si('cbx.token')
$q$);

-- Sales.

SELECT pg_temp.check('SUB1', 'sale_subscription: the 17.0 payment success template is deleted', ARRAY['mod:sale_subscription', 'seed:block.sub'], $q$
    SELECT * FROM pg_temp.gone('sub', 'mail_template')
$q$);
SELECT pg_temp.check('STE1', 'sale_timesheet_enterprise: every company shows the rates and the leaderboard 17.0 enabled, the 17.0 groups are gone', ARRAY['mod:sale_timesheet_enterprise', 'seed:block.ste', 'col:res_company.timesheet_show_leaderboard'], $q$
    SELECT count(c.id) > 0 AND count(c.id) = count(*) AND bool_and(coalesce(c.timesheet_show_rates AND c.timesheet_show_leaderboard, FALSE))
            AND NOT EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'sale_timesheet_enterprise'
                AND name IN ('group_timesheet_leaderboard_show_rates', 'group_use_timesheet_leaderboard')),
        format('companies=%s showing rates=%s leaderboard=%s groups left=%s', count(*),
            count(*) FILTER (WHERE c.timesheet_show_rates), count(*) FILTER (WHERE c.timesheet_show_leaderboard),
            EXISTS (SELECT 1 FROM ir_model_data WHERE module = 'sale_timesheet_enterprise'
                AND name IN ('group_timesheet_leaderboard_show_rates', 'group_use_timesheet_leaderboard')))
    FROM unnest(string_to_array(pg_temp.s('ste.companies'), ',')::integer[]) x(id) LEFT JOIN res_company c ON c.id = x.id
$q$);
SELECT pg_temp.check('WSD1', 'website_sale_dashboard: the 17.0 onboarding step and panel are deleted', ARRAY['mod:website_sale_dashboard', 'seed:block.wsd'], $q$
    SELECT g.ok AND NOT EXISTS (SELECT 1 FROM onboarding_onboarding_step
                WHERE id = pg_temp.si('wsd.website_sale_dashboard.onboarding_onboarding_step_payment_provider'))
            AND NOT EXISTS (SELECT 1 FROM onboarding_onboarding
                WHERE id = pg_temp.si('wsd.website_sale_dashboard.onboarding_onboarding_website_sale_dashboard')),
        g.actual
    FROM pg_temp.gone('wsd', NULL) g
$q$);
SELECT pg_temp.check('WSR1', 'website_sale_renting: every 17.0 website has a timezone', ARRAY['mod:website_sale_renting', 'seed:block.wsr', 'col:website.tz'], $q$
    SELECT count(w.id) > 0 AND count(w.id) = count(*) AND bool_and(coalesce(w.tz = 'UTC', FALSE)),
        string_agg(format('%s=%s', x.id, coalesce(w.tz, 'none')), ' ')
    FROM unnest(string_to_array(pg_temp.s('wsr.websites'), ',')::integer[]) x(id) LEFT JOIN website w ON w.id = x.id
$q$);

\o
SELECT format('%s %s %s %s | %s', lpad(seq::text, 3), result, code, name, actual) FROM oue_result ORDER BY seq;
SELECT format('SUMMARY passed=%s | failed=%s | skipped=%s',
    count(*) FILTER (WHERE result = 'PASS'), count(*) FILTER (WHERE result = 'FAIL'), count(*) FILTER (WHERE result = 'SKIP'))
FROM oue_result;

DO $$
DECLARE
    failed integer;
    total integer;
BEGIN
    SELECT count(*) FILTER (WHERE result = 'FAIL'), count(*) INTO failed, total FROM oue_result;
    IF failed > 0 THEN
        RAISE EXCEPTION 'verify_v18: % of % checks failed', failed, total;
    END IF;
END $$;
