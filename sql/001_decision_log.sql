-- ============================================================
-- NUR BEIM NEUAUFSETZEN DER DATENBANK AUSFÜHREN
-- In der aktuellen Supabase-DB (Cloud) ist das bereits angelegt.
-- Reihenfolge: Dateien nach Nummer ausführen (001, 002, ...).
-- Mehrfaches Ausführen schadet nicht (if not exists).
-- Ausführen: im Supabase SQL-Editor oder Statement für Statement
-- über config.db_connection.db.execute(...).
-- ============================================================

-- Decision-Log für den Governance-Layer (eine Zeile pro Gate-Entscheidung)

create table if not exists public.decision_log (
    id               uuid primary key default gen_random_uuid(),
    created_at       timestamptz not null default now(),

    -- Kontext
    process_id       uuid references public.process_list(id) on delete set null,
    thread_id        text,          -- LangGraph-Thread, für resume nach interrupt
    scenario_id      text,          -- Testszenario, für die Ground Truth
    step_id          text,
    tool             text,
    risk             text,          -- read | draft | submit | payment
    autonomy_level   text,          -- L1 | L2 | L3
    trigger          text,          -- chat | auto

    -- Konfidenz
    n_samples        int,
    distribution     jsonb,         -- [{key, count}, ...]
    conf_consistency real,
    conf_verbal      real,
    threshold        real,
    rule_hits        jsonb,

    -- Entscheidung
    decision         text,          -- auto | escalate | needs_human
    reason           text,
    chosen_action    jsonb,

    -- nach dem Menschen bzw. der Auswertung
    human_action     text,          -- approve | select | edit | reject
    corrected        boolean,
    correct          boolean        -- wird gegen den Gold-Fingerprint gelabelt
);

create index if not exists decision_log_process_idx  on public.decision_log (process_id);
create index if not exists decision_log_scenario_idx on public.decision_log (scenario_id, autonomy_level);
