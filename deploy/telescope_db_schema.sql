-- Schema of the VO run-metadata database (telescope_db), as the GUI expects it.
--
-- Applied by deploy/setup_postgres.sh, as a superuser, connected to telescope_db.
-- Safe to re-run: every statement is IF NOT EXISTS or an idempotent GRANT.
-- The role vo_admin must already exist.
--
-- Reproduces the hand-built database on hypatia (pg_dump --schema-only,
-- 2026-11-06). The constraint, sequence and table names match it, so a data-only
-- dump from an old machine loads into a fresh one unchanged.
--
-- Used by gui/ui_run_metadata.py:
--   * reserve_run_id     SELECT nextval('tblrun_info_run_id_seq')  -- needs USAGE
--   * read_last_run_id   SELECT last_value, is_called FROM the sequence -- needs SELECT
--   * write_VO_db_params_to_db  INSERT with an explicit run_id
-- vo_admin deliberately has no UPDATE on the sequence, so it cannot setval.

CREATE SEQUENCE IF NOT EXISTS public.tblrun_info_run_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

CREATE TABLE IF NOT EXISTS public.tblrun_info (
    run_id integer NOT NULL DEFAULT nextval('public.tblrun_info_run_id_seq'::regclass),
    veritas_run_id integer,
    run_type character varying(20),
    run_status character varying(20),
    run_window integer,
    db_start_time timestamp without time zone,
    db_end_time timestamp without time zone,
    data_start_time timestamp without time zone,
    data_end_time timestamp without time zone,
    duration interval,
    telescope_mask integer,
    harvester_mask bigint,
    source_id character varying(255),
    CONSTRAINT tblrun_info_pkey PRIMARY KEY (run_id),
    -- Written as IN (...): that is what the original was created with, and it makes
    -- PostgreSQL store (and pg_dump print) exactly the same expressions as on hypatia.
    CONSTRAINT tblrun_info_run_status_check CHECK (run_status IN ('started', 'aborted', 'ended', 'ended_manually')),
    CONSTRAINT tblrun_info_run_type_check CHECK (run_type IN ('observing', 'calibration', 'engineering', 'other')),
    CONSTRAINT tblrun_info_run_window_check CHECK (run_window IN (1, 2, 4, 8, 16))
);

-- Dropping the table drops the sequence too, as with a serial column.
ALTER SEQUENCE public.tblrun_info_run_id_seq OWNED BY public.tblrun_info.run_id;

GRANT ALL ON TABLE public.tblrun_info TO vo_admin;
GRANT SELECT, USAGE ON SEQUENCE public.tblrun_info_run_id_seq TO vo_admin;
