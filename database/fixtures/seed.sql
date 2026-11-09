-- statement
INSERT INTO users(id, keycloak_sub, display_name) VALUES
('cafe0000-0000-4000-8000-000000000101', 'cafe0000-0000-4000-8000-000000000001', 'Alex Sales'),
('cafe0000-0000-4000-8000-000000000102', 'cafe0000-0000-4000-8000-000000000002', 'Jordan Support'),
('cafe0000-0000-4000-8000-000000000103', 'cafe0000-0000-4000-8000-000000000003', 'Morgan Admin')
ON CONFLICT (id) DO NOTHING;
-- statement
INSERT INTO customers(id,name,account_owner_sub,status) VALUES
('ac000000-0000-4000-8000-000000000001','Acme Retail','cafe0000-0000-4000-8000-000000000001','active'),
('ac000000-0000-4000-8000-000000000002','Meridian Logistics','cafe0000-0000-4000-8000-000000000002','active'),
('ac000000-0000-4000-8000-000000000003','Northstar Finance','cafe0000-0000-4000-8000-000000000003','active')
ON CONFLICT (id) DO NOTHING;
-- statement
INSERT INTO user_customer_access(keycloak_sub,customer_id) VALUES
('cafe0000-0000-4000-8000-000000000001','ac000000-0000-4000-8000-000000000001')
ON CONFLICT DO NOTHING;
-- statement
INSERT INTO issues(id,customer_id,title,description,priority,status,sla_due_at,created_at,updated_at) VALUES
('ab000000-0000-4000-8000-000000000001','ac000000-0000-4000-8000-000000000001','Payment reconciliation discrepancy','Settlement file does not match payment ledger','critical','investigating','2026-11-07 16:00+00','2026-11-01 09:00+00','2026-11-08 11:00+00'),
('ab000000-0000-4000-8000-000000000002','ac000000-0000-4000-8000-000000000001','Returns queue elevated','Support tickets waiting for resolution','high','open','2026-11-10 17:00+00','2026-11-02 08:00+00','2026-11-07 11:00+00'),
('ab000000-0000-4000-8000-000000000003','ac000000-0000-4000-8000-000000000001','Receipt template typo','Minor formatting issue','low','resolved',NULL,'2026-10-20 08:00+00','2026-11-01 12:00+00'),
('ab000000-0000-4000-8000-000000000004','ac000000-0000-4000-8000-000000000002','Delayed dispatch','Warehouse scans lag by four hours','medium','open','2026-11-11 18:00+00','2026-11-04 08:00+00','2026-11-05 11:00+00'),
('ab000000-0000-4000-8000-000000000005','ac000000-0000-4000-8000-000000000002','API error spike','Frequent 5xx on shipment webhook','high','investigating','2026-11-08 12:00+00','2026-11-04 08:00+00','2026-11-08 09:00+00'),
('ab000000-0000-4000-8000-000000000006','ac000000-0000-4000-8000-000000000002','Duplicate alerts','Resolved paging duplication','low','closed',NULL,'2026-10-28 08:00+00','2026-11-02 09:00+00'),
('ab000000-0000-4000-8000-000000000007','ac000000-0000-4000-8000-000000000003','Statement export delayed','Month-end statements taking longer','high','open','2026-11-10 10:00+00','2026-11-05 08:00+00','2026-11-08 10:00+00'),
('ab000000-0000-4000-8000-000000000008','ac000000-0000-4000-8000-000000000003','User access request','Request awaiting manager approval','medium','open',NULL,'2026-11-01 08:00+00','2026-11-02 10:00+00'),
('ab000000-0000-4000-8000-000000000009','ac000000-0000-4000-8000-000000000003','Daily report intermittent','No recent issue updates available','low','open',NULL,'2026-11-04 08:00+00','2026-11-04 08:00+00')
ON CONFLICT (id) DO NOTHING;
-- statement
INSERT INTO issue_updates(id,issue_id,author_sub,content,created_at) VALUES
('ad000000-0000-4000-8000-000000000001','ab000000-0000-4000-8000-000000000001','cafe0000-0000-4000-8000-000000000002','Investigation started; impact being validated','2026-11-05 09:30+00'),
('ad000000-0000-4000-8000-000000000002','ab000000-0000-4000-8000-000000000001','cafe0000-0000-4000-8000-000000000002','Provisional fix deployed, not confirmed by business','2026-11-07 12:00+00'),
('ad000000-0000-4000-8000-000000000003','ab000000-0000-4000-8000-000000000001','cafe0000-0000-4000-8000-000000000002','Customer reports discrepancy still present: conflicting update','2026-11-08 11:00+00'),
('ad000000-0000-4000-8000-000000000004','ab000000-0000-4000-8000-000000000002','cafe0000-0000-4000-8000-000000000002','Backlog triaged; no confirmed ETA','2026-11-07 11:00+00'),
('ad000000-0000-4000-8000-000000000005','ab000000-0000-4000-8000-000000000004','cafe0000-0000-4000-8000-000000000002','Initial telemetry received','2026-11-05 11:00+00'),
('ad000000-0000-4000-8000-000000000006','ab000000-0000-4000-8000-000000000005','cafe0000-0000-4000-8000-000000000002','High error rate persists at peak traffic','2026-11-08 09:00+00'),
('ad000000-0000-4000-8000-000000000007','ab000000-0000-4000-8000-000000000007','cafe0000-0000-4000-8000-000000000002','Customer deadline remains at risk','2026-11-08 10:00+00'),
('ad000000-0000-4000-8000-000000000008','ab000000-0000-4000-8000-000000000008','cafe0000-0000-4000-8000-000000000003','Waiting for manager consent','2026-11-02 10:00+00')
ON CONFLICT (id) DO NOTHING;
