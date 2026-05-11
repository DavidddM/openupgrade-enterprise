-- =============================================================================
-- OpenUpgrade Enterprise E2E: country companies on the 17.0 source database.
-- =============================================================================
-- Run by scripts/run_e2e_test.sh as BASE_SQL, after base is installed and
-- before the batch modules, so module installation sees the companies. Creates
-- one child company of company 1 per country code that scripts/seed_test_data.sql
-- looks up by partner country (AR CL EC MX PE NL DE BE CH AU KE). Idempotent.
-- =============================================================================

DO $$ DECLARE
    v_country_id INTEGER;
    v_partner_id INTEGER;
    v_company_id INTEGER;
    v_currency_id INTEGER;
    v_countries TEXT[] := ARRAY['AR','CL','EC','MX','PE','NL','DE','BE','CH','AU','KE'];
    v_code TEXT;
BEGIN
    SELECT currency_id INTO v_currency_id FROM res_company WHERE id = 1;
    FOREACH v_code IN ARRAY v_countries LOOP
        SELECT id INTO v_country_id FROM res_country WHERE code = v_code;
        IF v_country_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM res_company WHERE name = 'Company ' || v_code) THEN
            INSERT INTO res_partner (name, is_company, country_id, company_id,
                                     create_uid, create_date, write_uid, write_date)
            VALUES ('Company ' || v_code, true, v_country_id, NULL,
                    1, NOW(), 1, NOW())
            RETURNING id INTO v_partner_id;
            INSERT INTO res_company (name, partner_id, parent_id, currency_id,
                                     layout_background,
                                     create_uid, create_date, write_uid, write_date)
            VALUES ('Company ' || v_code, v_partner_id, 1, v_currency_id,
                    'Blank',
                    1, NOW(), 1, NOW())
            RETURNING id INTO v_company_id;
            UPDATE res_partner
            SET company_id = v_company_id,
                country_id = v_country_id
            WHERE id = v_partner_id;
            RAISE NOTICE 'Created company for %: id=%', v_code, v_company_id;
        END IF;
    END LOOP;
END $$;
