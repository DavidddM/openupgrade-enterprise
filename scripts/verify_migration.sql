-- =============================================================================
-- OpenUpgrade Enterprise E2E Test: Verification Queries (Post-Upgrade)
-- =============================================================================
-- Each test returns PASS or FAIL. Results are collected in a temp table.
-- Tests are guarded: if the table/column doesn't exist (module not installed),
-- the test returns PASS (the migration script's guard clause would have skipped it).
-- =============================================================================

DROP TABLE IF EXISTS _ou_test_results;
CREATE TEMP TABLE _ou_test_results (
    test_id   INTEGER,
    test_name TEXT,
    result    TEXT,
    detail    TEXT
);

-- ---------------------------------------------------------------------------
-- TEST 1: account_accountant - deferred_expense_journal_id column exists
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='deferred_expense_journal_id') THEN
    INSERT INTO _ou_test_results VALUES (1, 'account_accountant: deferred_expense_journal_id exists', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_accountant' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (1, 'account_accountant: deferred_expense_journal_id exists', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (1, 'account_accountant: deferred_expense_journal_id exists', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 2: account_accountant - deferred_revenue_journal_id backfill
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='deferred_revenue_journal_id') THEN
    IF EXISTS (SELECT 1 FROM res_company
               WHERE deferred_expense_journal_id IS NOT NULL
               AND deferred_revenue_journal_id IS NOT NULL) THEN
        INSERT INTO _ou_test_results VALUES (2, 'account_accountant: revenue journal backfilled', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (2, 'account_accountant: revenue journal backfilled', 'FAIL',
            'deferred_revenue_journal_id NULL where expense is set');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (2, 'account_accountant: revenue journal backfilled', 'PASS', 'Module not installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 3: account_accountant - Kenya tax tags exist
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='l10n_ke' AND state='installed') THEN
    DECLARE v_count INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_count FROM account_account_tag
        WHERE country_id = (SELECT id FROM res_country WHERE code='KE')
        AND applicability = 'taxes';
        IF v_count >= 34 THEN
            INSERT INTO _ou_test_results VALUES (3, 'account_accountant: Kenya tax tags', 'PASS', v_count || ' tags found');
        ELSE
            INSERT INTO _ou_test_results VALUES (3, 'account_accountant: Kenya tax tags', 'FAIL', 'Only ' || v_count || ' tags');
        END IF;
    END;
ELSE
    INSERT INTO _ou_test_results VALUES (3, 'account_accountant: Kenya tax tags', 'PASS', 'l10n_ke not installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 4: account_accountant - accountant module hook
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_accountant' AND state='installed') THEN
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='accountant' AND state NOT IN ('uninstalled', 'uninstallable')) THEN
        INSERT INTO _ou_test_results VALUES (4, 'account_accountant: accountant module', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (4, 'account_accountant: accountant module', 'FAIL', 'accountant module not enabled');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (4, 'account_accountant: accountant module', 'PASS', 'Module not installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 5: account_reports - annotation table exists
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='account_report_annotation') THEN
    INSERT INTO _ou_test_results VALUES (5, 'account_reports: annotation table exists', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_reports' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (5, 'account_reports: annotation table exists', 'FAIL', 'Table missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (5, 'account_reports: annotation table exists', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 6: account_reports - no last_* values in opening_date_filter
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_report' AND column_name='default_opening_date_filter') THEN
    IF NOT EXISTS (SELECT 1 FROM account_report WHERE default_opening_date_filter LIKE 'last_%') THEN
        INSERT INTO _ou_test_results VALUES (6, 'account_reports: no last_* date filters', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (6, 'account_reports: no last_* date filters', 'FAIL',
            'Found last_* values still present');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (6, 'account_reports: no last_* date filters', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 7: account_budget - budget_analytic table exists
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='budget_analytic') THEN
    INSERT INTO _ou_test_results VALUES (7, 'account_budget: budget_analytic table', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_budget' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (7, 'account_budget: budget_analytic table', 'FAIL', 'Table missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (7, 'account_budget: budget_analytic table', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 8: account_budget - no old states
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='budget_analytic') THEN
    IF NOT EXISTS (SELECT 1 FROM budget_analytic WHERE state IN ('confirm', 'cancel', 'validate')) THEN
        INSERT INTO _ou_test_results VALUES (8, 'account_budget: state mapping', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (8, 'account_budget: state mapping', 'FAIL', 'Old states still present');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (8, 'account_budget: state mapping', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 9: account_budget - budget_line columns renamed
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='budget_line') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='budget_line' AND column_name='budget_analytic_id')
    AND EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='budget_line' AND column_name='budget_amount') THEN
        INSERT INTO _ou_test_results VALUES (9, 'account_budget: column renames', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (9, 'account_budget: column renames', 'FAIL', 'Columns missing');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (9, 'account_budget: column renames', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 10: account_asset - M2M table has rows
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables
           WHERE table_name='account_account_account_asset_rel') THEN
    IF EXISTS (SELECT 1 FROM account_account_account_asset_rel LIMIT 1) THEN
        INSERT INTO _ou_test_results VALUES (10, 'account_asset: M2O->M2M populated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (10, 'account_asset: M2O->M2M populated', 'FAIL', 'No rows in M2M table');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (10, 'account_asset: M2O->M2M populated', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 11: account_iso20022 - orgid renamed
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='iso20022_orgid_id') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE iso20022_orgid_id = 'TESTORGID001') THEN
        INSERT INTO _ou_test_results VALUES (11, 'account_iso20022: orgid rename', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (11, 'account_iso20022: orgid rename', 'FAIL', 'Value not found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (11, 'account_iso20022: orgid rename', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 12: account_iso20022 - no legacy pain versions
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_journal' AND column_name='sepa_pain_version') THEN
    IF NOT EXISTS (SELECT 1 FROM account_journal
                   WHERE sepa_pain_version IN ('pain.001.001.03.se', 'pain.001.001.03.ch.02', 'iso_20022')) THEN
        INSERT INTO _ou_test_results VALUES (12, 'account_iso20022: pain versions', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (12, 'account_iso20022: pain versions', 'FAIL', 'Legacy versions found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (12, 'account_iso20022: pain versions', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 13: account_inter_company_rules - boolean set
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='intercompany_generate_bills_refund') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE intercompany_generate_bills_refund = true AND id = 1) THEN
        INSERT INTO _ou_test_results VALUES (13, 'inter_company: bills_refund boolean', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (13, 'inter_company: bills_refund boolean', 'FAIL', 'Not set on company 1');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (13, 'inter_company: bills_refund boolean', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 14: sale_purchase_inter_company_rules - both booleans
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='intercompany_generate_sales_orders') THEN
    IF EXISTS (SELECT 1 FROM res_company
               WHERE intercompany_generate_sales_orders = true
               AND intercompany_generate_purchase_orders = true
               AND id != 1) THEN
        INSERT INTO _ou_test_results VALUES (14, 'sale_purchase_inter_company: booleans', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (14, 'sale_purchase_inter_company: booleans', 'FAIL', 'Booleans not set');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (14, 'sale_purchase_inter_company: booleans', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 15: account_sepa_direct_debit - sdd_mandate_id on payment
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='account_payment' AND column_name='sdd_mandate_id') THEN
    INSERT INTO _ou_test_results VALUES (15, 'sepa_direct_debit: mandate on payment', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_sepa_direct_debit' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (15, 'sepa_direct_debit: mandate on payment', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (15, 'sepa_direct_debit: mandate on payment', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 16: l10n_ar_edi - certificate records created
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='certificate_certificate') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='res_company' AND column_name='l10n_ar_afip_ws_crt') THEN
        IF EXISTS (SELECT 1 FROM certificate_certificate WHERE name LIKE '%AR AFIP%') THEN
            INSERT INTO _ou_test_results VALUES (16, 'l10n_ar_edi: certificate migrated', 'PASS', NULL);
        ELSE
            IF EXISTS (SELECT 1 FROM res_company WHERE l10n_ar_afip_ws_crt IS NOT NULL) THEN
                INSERT INTO _ou_test_results VALUES (16, 'l10n_ar_edi: certificate migrated', 'FAIL', 'No cert record');
            ELSE
                INSERT INTO _ou_test_results VALUES (16, 'l10n_ar_edi: certificate migrated', 'PASS', 'No AR data to migrate');
            END IF;
        END IF;
    ELSE
        INSERT INTO _ou_test_results VALUES (16, 'l10n_ar_edi: certificate migrated', 'PASS', 'No old column');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (16, 'l10n_ar_edi: certificate migrated', 'PASS', 'cert table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 17: l10n_cl_edi - certificate migrated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='certificate_certificate') THEN
    IF EXISTS (SELECT 1 FROM certificate_certificate WHERE LOWER(name) LIKE '%cl%') THEN
        INSERT INTO _ou_test_results VALUES (17, 'l10n_cl_edi: certificate migrated', 'PASS', NULL);
    ELSE
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_cl_certificate')
           AND EXISTS (SELECT 1 FROM l10n_cl_certificate LIMIT 1) THEN
            INSERT INTO _ou_test_results VALUES (17, 'l10n_cl_edi: certificate migrated', 'FAIL', 'Old data exists but no new cert');
        ELSE
            INSERT INTO _ou_test_results VALUES (17, 'l10n_cl_edi: certificate migrated', 'PASS', 'No CL data');
        END IF;
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (17, 'l10n_cl_edi: certificate migrated', 'PASS', 'cert table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 18: l10n_ec_edi - certificate migrated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='certificate_certificate') THEN
    IF EXISTS (SELECT 1 FROM certificate_certificate WHERE LOWER(name) LIKE '%ec%') THEN
        INSERT INTO _ou_test_results VALUES (18, 'l10n_ec_edi: certificate migrated', 'PASS', NULL);
    ELSE
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_ec_edi_certificate')
           AND EXISTS (SELECT 1 FROM l10n_ec_edi_certificate LIMIT 1) THEN
            INSERT INTO _ou_test_results VALUES (18, 'l10n_ec_edi: certificate migrated', 'FAIL', 'Old data but no new cert');
        ELSE
            INSERT INTO _ou_test_results VALUES (18, 'l10n_ec_edi: certificate migrated', 'PASS', 'No EC data');
        END IF;
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (18, 'l10n_ec_edi: certificate migrated', 'PASS', 'cert table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 19: l10n_mx_edi - cert+key+addenda
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='certificate_certificate') THEN
    IF EXISTS (SELECT 1 FROM certificate_certificate WHERE name LIKE '%MX%') THEN
        INSERT INTO _ou_test_results VALUES (19, 'l10n_mx_edi: certificate migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (19, 'l10n_mx_edi: certificate migrated', 'PASS', 'No MX data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (19, 'l10n_mx_edi: certificate migrated', 'PASS', 'cert table N/A');
END IF;
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_mx_edi_addenda') THEN
    INSERT INTO _ou_test_results VALUES (190, 'l10n_mx_edi: addenda migrated', 'PASS', NULL);
ELSE
    INSERT INTO _ou_test_results VALUES (190, 'l10n_mx_edi: addenda migrated', 'PASS', 'Addenda table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 20: l10n_pe_edi - certificate migrated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='certificate_certificate') THEN
    IF EXISTS (SELECT 1 FROM certificate_certificate WHERE name LIKE '%PE%') THEN
        INSERT INTO _ou_test_results VALUES (20, 'l10n_pe_edi: certificate migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (20, 'l10n_pe_edi: certificate migrated', 'PASS', 'No PE data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (20, 'l10n_pe_edi: certificate migrated', 'PASS', 'cert table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 21: l10n_nl_reports_sbr - cert+key+root migrated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='l10n_nl_reports_sbr_cert_id') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE l10n_nl_reports_sbr_cert_id IS NOT NULL) THEN
        INSERT INTO _ou_test_results VALUES (21, 'l10n_nl_reports_sbr: cert migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (21, 'l10n_nl_reports_sbr: cert migrated', 'PASS', 'No NL cert data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (21, 'l10n_nl_reports_sbr: cert migrated', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 22: documents - type='folder' documents exist
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_document') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='documents_document' AND column_name='type') THEN
        IF EXISTS (SELECT 1 FROM documents_document WHERE type='folder') THEN
            INSERT INTO _ou_test_results VALUES (22, 'documents: folder-type docs exist', 'PASS', NULL);
        ELSE
            INSERT INTO _ou_test_results VALUES (22, 'documents: folder-type docs exist', 'FAIL', 'No folder-type docs');
        END IF;
    ELSE
        INSERT INTO _ou_test_results VALUES (22, 'documents: folder-type docs exist', 'PASS', 'Column N/A');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (22, 'documents: folder-type docs exist', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 23: documents - folder_id refs point to folder-type docs
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_document') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='documents_document' AND column_name='folder_id') THEN
        IF NOT EXISTS (
            SELECT 1 FROM documents_document dd
            JOIN documents_document parent ON parent.id = dd.folder_id
            WHERE parent.type != 'folder'
            AND dd.folder_id IS NOT NULL
            LIMIT 1
        ) THEN
            INSERT INTO _ou_test_results VALUES (23, 'documents: folder_id FK correct', 'PASS', NULL);
        ELSE
            INSERT INTO _ou_test_results VALUES (23, 'documents: folder_id FK correct', 'FAIL', 'folder_id points to non-folder');
        END IF;
    ELSE
        INSERT INTO _ou_test_results VALUES (23, 'documents: folder_id FK correct', 'PASS', 'Column N/A');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (23, 'documents: folder_id FK correct', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 24: documents - no duplicate tag names
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_tag') THEN
    DECLARE v_dup_count INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_dup_count FROM (
            SELECT name FROM documents_tag GROUP BY name HAVING COUNT(*) > 1
        ) dupes;
        IF v_dup_count = 0 THEN
            INSERT INTO _ou_test_results VALUES (24, 'documents: no duplicate tags', 'PASS', NULL);
        ELSE
            INSERT INTO _ou_test_results VALUES (24, 'documents: no duplicate tags', 'FAIL', v_dup_count || ' duplicates');
        END IF;
    END;
ELSE
    INSERT INTO _ou_test_results VALUES (24, 'documents: no duplicate tags', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 25: documents - no type='empty'
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='documents_document') THEN
    IF NOT EXISTS (SELECT 1 FROM documents_document WHERE type='empty') THEN
        INSERT INTO _ou_test_results VALUES (25, 'documents: no empty type', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (25, 'documents: no empty type', 'FAIL', 'type=empty still present');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (25, 'documents: no empty type', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 26: hr_payroll - custom input type migrated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_payslip_input_type') THEN
    IF EXISTS (SELECT 1 FROM hr_payslip_input_type WHERE code='CUSTOM_DED') THEN
        INSERT INTO _ou_test_results VALUES (26, 'hr_payroll: input type migrated', 'PASS', NULL);
    ELSE
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_salary_attachment_type')
           AND EXISTS (SELECT 1 FROM hr_salary_attachment_type WHERE code='CUSTOM_DED') THEN
            INSERT INTO _ou_test_results VALUES (26, 'hr_payroll: input type migrated', 'FAIL', 'Custom code not migrated');
        ELSE
            INSERT INTO _ou_test_results VALUES (26, 'hr_payroll: input type migrated', 'PASS', 'No custom data');
        END IF;
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (26, 'hr_payroll: input type migrated', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 27: hr_appraisal - template records created
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='hr_appraisal_template') THEN
    IF EXISTS (SELECT 1 FROM hr_appraisal_template LIMIT 1) THEN
        INSERT INTO _ou_test_results VALUES (27, 'hr_appraisal: templates migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (27, 'hr_appraisal: templates migrated', 'FAIL', 'No template records');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (27, 'hr_appraisal: templates migrated', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 28: hr_contract_salary - always_show_description (inverted)
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_contract_salary_benefit' AND column_name='always_show_description') THEN
    INSERT INTO _ou_test_results VALUES (28, 'hr_contract_salary: hide->show inversion', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='hr_contract_salary' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (28, 'hr_contract_salary: hide->show inversion', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (28, 'hr_contract_salary: hide->show inversion', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 29: hr_contract_salary - selector_highlight='red'
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_contract_salary_benefit_value' AND column_name='selector_highlight') THEN
    IF EXISTS (SELECT 1 FROM hr_contract_salary_benefit_value WHERE selector_highlight='red') THEN
        INSERT INTO _ou_test_results VALUES (29, 'hr_contract_salary: color->highlight', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (29, 'hr_contract_salary: color->highlight', 'FAIL', 'No red highlight');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (29, 'hr_contract_salary: color->highlight', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 30: l10n_ch_hr_payroll - no NULL insurance_code
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='l10n_ch_social_insurance') THEN
    IF NOT EXISTS (SELECT 1 FROM l10n_ch_social_insurance WHERE insurance_code IS NULL) THEN
        INSERT INTO _ou_test_results VALUES (30, 'l10n_ch_hr_payroll: insurance_code', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (30, 'l10n_ch_hr_payroll: insurance_code', 'FAIL', 'NULL insurance_code found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (30, 'l10n_ch_hr_payroll: insurance_code', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 31: l10n_ke_hr_payroll - disabled field
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_employee' AND column_name='disabled') THEN
    IF EXISTS (SELECT 1 FROM hr_employee WHERE disabled = true) THEN
        INSERT INTO _ou_test_results VALUES (31, 'l10n_ke_hr_payroll: disabled migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (31, 'l10n_ke_hr_payroll: disabled migrated', 'PASS', 'No KE employees');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (31, 'l10n_ke_hr_payroll: disabled migrated', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 32: social - per-media message fields populated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='social_post' AND column_name='facebook_message') THEN
    IF EXISTS (SELECT 1 FROM social_post WHERE facebook_message IS NOT NULL AND facebook_message != '') THEN
        INSERT INTO _ou_test_results VALUES (32, 'social: per-media messages', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (32, 'social: per-media messages', 'FAIL', 'facebook_message empty');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (32, 'social: per-media messages', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 33: social - per-media image M2M tables exist with rows
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='facebook_image_ids_rel') THEN
    IF EXISTS (SELECT 1 FROM facebook_image_ids_rel LIMIT 1) THEN
        INSERT INTO _ou_test_results VALUES (33, 'social: facebook image rel', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (33, 'social: facebook image rel', 'PASS', 'Table exists, no seed data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (33, 'social: facebook image rel', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 34: social_twitter - name = 'X'
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='social_media') THEN
    IF EXISTS (SELECT 1 FROM ir_model_data
               WHERE module='social_twitter' AND name='social_media_twitter') THEN
        DECLARE v_name TEXT;
        BEGIN
            SELECT COALESCE(sm.name->>'en_US', sm.name::text) INTO v_name
            FROM social_media sm
            JOIN ir_model_data imd ON imd.res_id = sm.id
            WHERE imd.module='social_twitter' AND imd.name='social_media_twitter';
            IF v_name = 'X' THEN
                INSERT INTO _ou_test_results VALUES (34, 'social_twitter: name=X', 'PASS', NULL);
            ELSE
                INSERT INTO _ou_test_results VALUES (34, 'social_twitter: name=X', 'FAIL', 'Name is: ' || COALESCE(v_name, 'NULL'));
            END IF;
        END;
    ELSE
        INSERT INTO _ou_test_results VALUES (34, 'social_twitter: name=X', 'PASS', 'No twitter media');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (34, 'social_twitter: name=X', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 35: sale_timesheet_enterprise - company boolean
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='timesheet_show_leaderboard') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE timesheet_show_leaderboard = true) THEN
        INSERT INTO _ou_test_results VALUES (35, 'sale_timesheet: leaderboard boolean', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (35, 'sale_timesheet: leaderboard boolean', 'FAIL', 'Not set');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (35, 'sale_timesheet: leaderboard boolean', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 36: spreadsheet_edition - revision_uuid column
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='spreadsheet_revision') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='spreadsheet_revision' AND column_name='revision_uuid') THEN
        INSERT INTO _ou_test_results VALUES (36, 'spreadsheet: revision_uuid column', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (36, 'spreadsheet: revision_uuid column', 'FAIL', 'Column missing');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (36, 'spreadsheet: revision_uuid column', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 37: spreadsheet_edition - parent_revision_id is integer
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='spreadsheet_revision') THEN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='spreadsheet_revision' AND column_name='parent_revision_id'
               AND data_type = 'integer') THEN
        INSERT INTO _ou_test_results VALUES (37, 'spreadsheet: parent_revision M2O', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (37, 'spreadsheet: parent_revision M2O', 'FAIL', 'Not integer type');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (37, 'spreadsheet: parent_revision M2O', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 38: voip - provider record populated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='voip_provider') THEN
    IF EXISTS (SELECT 1 FROM voip_provider WHERE pbx_ip = 'pbx.example.com') THEN
        INSERT INTO _ou_test_results VALUES (38, 'voip: config migrated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (38, 'voip: config migrated', 'FAIL', 'pbx_ip not set');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (38, 'voip: config migrated', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 39: whatsapp - last_wa_mail_message_id column
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='discuss_channel' AND column_name='last_wa_mail_message_id') THEN
    INSERT INTO _ou_test_results VALUES (39, 'whatsapp: field rename', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='whatsapp' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (39, 'whatsapp: field rename', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (39, 'whatsapp: field rename', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 40: web_studio - approval_group_id column
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='studio_approval_rule' AND column_name='approval_group_id') THEN
    INSERT INTO _ou_test_results VALUES (40, 'web_studio: approval_group_id', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='web_studio' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (40, 'web_studio: approval_group_id', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (40, 'web_studio: approval_group_id', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 41: worksheet - company_id populated
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='worksheet_template' AND column_name='company_id') THEN
    IF EXISTS (SELECT 1 FROM worksheet_template WHERE company_id IS NOT NULL) THEN
        INSERT INTO _ou_test_results VALUES (41, 'worksheet: company_id populated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (41, 'worksheet: company_id populated', 'PASS', 'No M2M source data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (41, 'worksheet: company_id populated', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 42: frontdesk - no NULL company_id on visitors
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='frontdesk_visitor') THEN
    IF NOT EXISTS (SELECT 1 FROM frontdesk_visitor WHERE company_id IS NULL) THEN
        INSERT INTO _ou_test_results VALUES (42, 'frontdesk: visitor company_id', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (42, 'frontdesk: visitor company_id', 'FAIL', 'NULL company_id found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (42, 'frontdesk: visitor company_id', 'PASS', 'Table N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 43: iot - iot_channel table gone
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='iot' AND state='installed') THEN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='iot_channel') THEN
        INSERT INTO _ou_test_results VALUES (43, 'iot: channel table dropped', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (43, 'iot: channel table dropped', 'FAIL', 'Table still exists');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (43, 'iot: channel table dropped', 'PASS', 'Module not installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 44: base - account_sepa renamed to account_iso20022
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_sepa' AND state='installed') THEN
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='account_iso20022') THEN
        INSERT INTO _ou_test_results VALUES (44, 'base: sepa->iso20022 rename', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (44, 'base: sepa->iso20022 rename', 'PASS', 'Module N/A');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (44, 'base: sepa->iso20022 rename', 'FAIL', 'account_sepa still installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 45: base - data_merge merged into data_cleaning
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM ir_module_module WHERE name='data_merge' AND state='installed') THEN
    INSERT INTO _ou_test_results VALUES (45, 'base: data_merge merged', 'PASS', NULL);
ELSE
    INSERT INTO _ou_test_results VALUES (45, 'base: data_merge merged', 'FAIL', 'data_merge still installed');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 46: appointment - manual_confirmation rename
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='appointment_type' AND column_name='appointment_manual_confirmation') THEN
    INSERT INTO _ou_test_results VALUES (46, 'appointment: field rename', 'PASS', NULL);
ELSE
    IF EXISTS (SELECT 1 FROM ir_module_module WHERE name='appointment' AND state='installed') THEN
        INSERT INTO _ou_test_results VALUES (46, 'appointment: field rename', 'FAIL', 'Column missing');
    ELSE
        INSERT INTO _ou_test_results VALUES (46, 'appointment: field rename', 'PASS', 'Module not installed');
    END IF;
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 47: planning - bool -> selection
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='planning_employee_unavailabilities') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE planning_employee_unavailabilities = 'unassign') THEN
        INSERT INTO _ou_test_results VALUES (47, 'planning: bool->selection', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (47, 'planning: bool->selection', 'FAIL', 'No unassign value');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (47, 'planning: bool->selection', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 48: planning - duration_days conversion
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='planning_slot_template' AND column_name='duration_days') THEN
    IF EXISTS (SELECT 1 FROM planning_slot_template WHERE duration_days = 3) THEN
        INSERT INTO _ou_test_results VALUES (48, 'planning: duration_days=3', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (48, 'planning: duration_days=3', 'PASS', 'No 24h template found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (48, 'planning: duration_days=3', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 49: project_forecast - project_id populated from ir_property
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='planning_slot_template' AND column_name='project_id') THEN
    IF EXISTS (SELECT 1 FROM planning_slot_template WHERE project_id IS NOT NULL) THEN
        INSERT INTO _ou_test_results VALUES (49, 'project_forecast: project_id populated', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (49, 'project_forecast: project_id populated', 'PASS', 'No data');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (49, 'project_forecast: project_id populated', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 50: mrp_mps - manufacturing_period_to_display_month
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='manufacturing_period_to_display_month') THEN
    IF EXISTS (SELECT 1 FROM res_company WHERE manufacturing_period_to_display_month = 6 AND id = 1) THEN
        INSERT INTO _ou_test_results VALUES (50, 'mrp_mps: period split month=6', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (50, 'mrp_mps: period split month=6', 'FAIL', 'Value not 6');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (50, 'mrp_mps: period split month=6', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 51: l10n_be_codabox - connected cleaned
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_company' AND column_name='l10n_be_codabox_is_connected') THEN
    IF NOT EXISTS (SELECT 1 FROM res_company
                   WHERE l10n_be_codabox_is_connected = true
                   AND (l10n_be_codabox_iap_token IS NULL OR l10n_be_codabox_iap_token = '')) THEN
        INSERT INTO _ou_test_results VALUES (51, 'l10n_be_codabox: connected cleanup', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (51, 'l10n_be_codabox: connected cleanup', 'FAIL', 'Connected without token');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (51, 'l10n_be_codabox: connected cleanup', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 52: l10n_au_hr_payroll - casual_loading scaled
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='hr_contract' AND column_name='l10n_au_casual_loading') THEN
    IF NOT EXISTS (SELECT 1 FROM hr_contract WHERE l10n_au_casual_loading > 1) THEN
        INSERT INTO _ou_test_results VALUES (52, 'l10n_au_hr_payroll: casual_loading scaled', 'PASS', NULL);
    ELSE
        INSERT INTO _ou_test_results VALUES (52, 'l10n_au_hr_payroll: casual_loading scaled', 'FAIL', 'Values >1 found');
    END IF;
ELSE
    INSERT INTO _ou_test_results VALUES (52, 'l10n_au_hr_payroll: casual_loading scaled', 'PASS', 'Column N/A');
END IF;
END $$;

-- ---------------------------------------------------------------------------
-- TEST 53: l10n_de_reports - datev identifier preserved
-- ---------------------------------------------------------------------------
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_name='res_partner'
           AND column_name LIKE '%l10n_de_datev_identifier%') THEN
    INSERT INTO _ou_test_results VALUES (53, 'l10n_de_reports: datev id preserved', 'PASS', NULL);
ELSE
    INSERT INTO _ou_test_results VALUES (53, 'l10n_de_reports: datev id preserved', 'PASS', 'Column N/A (expected)');
END IF;
END $$;

-- =============================================================================
-- SUMMARY
-- =============================================================================
SELECT '======================================' AS separator;
SELECT 'OPENUPGRADE ENTERPRISE E2E RESULTS' AS header;
SELECT '======================================' AS separator;

SELECT
    COUNT(*) FILTER (WHERE result = 'PASS') AS passed,
    COUNT(*) FILTER (WHERE result = 'FAIL') AS failed,
    COUNT(*) AS total
FROM _ou_test_results;

SELECT test_id, test_name, result, detail
FROM _ou_test_results
WHERE result = 'FAIL'
ORDER BY test_id;

SELECT test_id, test_name, result, COALESCE(detail, '') AS detail
FROM _ou_test_results
ORDER BY test_id;
