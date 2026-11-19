-- ============================================================
-- NUR BEIM NEUAUFSETZEN DER DATENBANK AUSFÜHREN
-- In der aktuellen Supabase-DB (Cloud) ist das bereits angelegt.
-- Reihenfolge: Dateien nach Nummer ausführen (001, 002, ...).
-- Mehrfaches Ausführen schadet nicht (if not exists).
-- Ausführen: im Supabase SQL-Editor oder Statement für Statement
-- über config.db_connection.db.execute(...).
-- ============================================================

-- Endgültige Aktion nach menschlicher Prüfung getrennt speichern.
-- chosen_action bleibt der Vorschlag des Agenten (Basis für die Kalibrierung).

alter table public.decision_log add column if not exists final_action jsonb;
