-- ============================================================
-- Bay Log seed data — Automotive blend zone.
-- Applied by app/db.py only when the tickets table is empty, so it
-- never overwrites real data on restart or upgrade.
-- ============================================================

INSERT INTO people (name, role, email) VALUES
('Lead Instructor', 'instructor', 'instructor@example.edu'),
('Auto Lead Instr', 'instructor', NULL),
('Shop Staff',      'staff',      NULL),
('Student A',       'student',    NULL),
('Student B',       'student',    NULL);

INSERT INTO resources (name, category, identifier, notes) VALUES
('Engine oil, 5W-30 (qt)',   'Fluids',     'OIL-5W30',    'Bulk dispense at station 3'),
('Oil filter, spin-on',      'Filters',    'FLT-OIL-STD', 'Check application chart'),
('Cabin air filter',         'Filters',    'FLT-CABIN',   NULL),
('Front brake pad set',      'Brakes',     'BRK-PAD-F',   NULL),
('Brake rotor, front',       'Brakes',     'BRK-ROT-F',   NULL),
('Spark plug, iridium',      'Ignition',   'IGN-PLUG-IR', 'Torque to spec'),
('Ignition coil',            'Ignition',   'IGN-COIL',    NULL),
('12V battery, Group 35',    'Electrical', 'BAT-G35',     'Load test before replacing'),
('Shop rag bundle',          'Supplies',   'SUP-RAG',     NULL),
('Nitrile gloves (box)',     'Supplies',   'SUP-GLOVE',   NULL);

INSERT INTO knowledge_base
    (category, trigger_or_symptom, likely_causes, diagnostic_steps, common_resolution, notes)
VALUES
('Ignition',
 'Engine misfire, rough idle, P0300-series code',
 'Worn spark plugs; failed ignition coil; vacuum leak; clogged injector',
 '1. Pull codes and note which cylinder. 2. Swap the suspect coil to another cylinder and see if the misfire follows. 3. Inspect plug condition and gap. 4. Smoke-test for vacuum leaks.',
 'Replace the failed coil and/or plugs on the affected cylinder, then clear codes and road test.',
 'If the misfire follows the swapped coil, the coil is the fault — good teaching moment for substitution testing.'),

('Brakes',
 'Squealing or grinding on brake application',
 'Worn pad friction material; glazed rotors; missing anti-rattle hardware',
 '1. Measure pad thickness against spec. 2. Measure rotor thickness and check for scoring. 3. Inspect hardware and slide pins.',
 'Replace pads (and rotors if below discard thickness), lubricate slide pins, torque to spec.',
 'Always record measured thickness in the diagnosis notes — that is the number QC checks.'),

('Electrical',
 'No-crank / slow crank, clicking at starter',
 'Discharged or failed battery; corroded terminals; failed starter; bad ground',
 '1. Measure resting battery voltage. 2. Load test the battery. 3. Voltage-drop test the cables. 4. Check starter current draw.',
 'Clean and torque terminals; replace the battery if it fails a load test; otherwise chase the voltage drop.',
 'Load test before selling a battery — resting voltage alone is not evidence.'),

('Cooling',
 'Overheating, coolant loss, sweet smell',
 'External leak at hose or radiator; failed water pump; failed head gasket; stuck thermostat',
 '1. Pressure-test the cooling system. 2. Inspect for external leaks. 3. Check for combustion gases in coolant. 4. Verify thermostat opening temperature.',
 'Repair the located leak; replace thermostat or pump as indicated by the test.',
 NULL),

('Maintenance',
 'Routine service interval due',
 'Scheduled maintenance, not a fault',
 '1. Confirm interval against manufacturer schedule and current mileage. 2. Inspect fluids, filters, tires, brakes. 3. Note anything found for a separate ticket.',
 'Perform the scheduled service and document all measurements.',
 'Anything found outside the service scope becomes its own repair order rather than scope creep on this one.');

-- ------------------------------------------------------------
-- Three example vehicles / repair orders spread across the workflow,
-- so the board is not empty on first launch.
-- ------------------------------------------------------------

INSERT INTO subjects (owner_id, label, attributes) VALUES
(4, '2014 Honda Civic LX',       '{"vin":"2HGFB2F58EH000111","plate":"BKN-4412","mileage":142870}'),
(5, '2011 Ford F-150 XLT',       '{"vin":"1FTFW1ET1BFA00222","plate":"WA-88231","mileage":198450}'),
(4, '2017 Subaru Outback 2.5i',  '{"vin":"4S4BSANC7H3000333","plate":"SHOP-0007","mileage":96310}');

INSERT INTO tickets
    (ticket_id, subject_id, assigned_person_id, stage_key, title, intake_notes, priority, done)
VALUES
('T-1001', 1, 4, 'diagnosis',     'Rough idle and check engine light',   'Customer reports shaking at stoplights for two weeks.', 'normal', 0),
('T-1002', 2, 5, 'qc_inspection', 'Front brake noise',                   'Grinding on stops, worse when cold.',                   'rush',   0),
('T-1003', 3, 4, 'intake',        'Due for scheduled maintenance',       'Customer requesting 96k service.',                      'low',    0);

-- T-1001: intake complete, now sitting in diagnosis
INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by, entered_at, exited_at) VALUES
('T-1001', 'intake',
 '{"complaint":"Shaking at idle, check engine light on steady.","mileage_in":142870,"notes":"No recent service history on file."}',
 4, datetime('now','-3 days'), datetime('now','-3 days','+2 hours')),
('T-1001', 'diagnosis',
 '{"codes":"P0303"}',
 4, datetime('now','-3 days','+2 hours'), NULL);

-- T-1002: through intake, diagnosis, approval and bay work; now at QC
INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by, entered_at, exited_at) VALUES
('T-1002', 'intake',
 '{"complaint":"Grinding noise from front when braking.","mileage_in":198450,"notes":"Customer waiting."}',
 5, datetime('now','-2 days'), datetime('now','-2 days','+1 hours')),
('T-1002', 'diagnosis',
 '{"findings":"Front pads at 2mm, below 3mm discard spec. Rotors scored, measured 27.1mm against 28.0mm minimum.","codes":"none"}',
 5, datetime('now','-2 days','+1 hours'), datetime('now','-2 days','+3 hours')),
('T-1002', 'estimate_approval',
 '{"estimate_hours":2,"estimate_parts":186,"notes":"Pads and rotors both required."}',
 3, datetime('now','-2 days','+3 hours'), datetime('now','-1 days')),
('T-1002', 'in_bay',
 '{"work_performed":"Replaced front pads and rotors, cleaned and lubricated slide pins, torqued to 80 ft-lb.","actual_hours":2.25}',
 5, datetime('now','-1 days'), datetime('now','-4 hours')),
('T-1002', 'qc_inspection',
 '{"road_tested":true}',
 2, datetime('now','-4 hours'), NULL);

INSERT INTO stage_signoffs (ticket_id, stage_key, signed_off_by, signed_off_name, signed_off_at) VALUES
('T-1002', 'estimate_approval', 3, 'Shop Staff', datetime('now','-1 days'));

-- T-1003: freshly checked in
INSERT INTO ticket_stage_log (ticket_id, stage_key, notes, entered_by, entered_at, exited_at) VALUES
('T-1003', 'intake',
 '{"complaint":"96k scheduled maintenance requested.","mileage_in":96310}',
 4, datetime('now','-5 hours'), NULL);

INSERT INTO ticket_knowledge_links (ticket_id, entry_id) VALUES
('T-1001', 1),
('T-1002', 2),
('T-1003', 5);

INSERT INTO ticket_resources (ticket_id, resource_id, quantity) VALUES
('T-1002', 4, 1),
('T-1002', 5, 2);
