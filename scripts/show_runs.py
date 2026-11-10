#!/usr/bin/env python3
"""Print the VO run table (tblrun_info) from the local run DB.

    python3 show_runs.py          every run
    python3 show_runs.py 20       the last 20 runs
    python3 show_runs.py --notes  the full notes of every run that has any
                                  (combine with N for the last N runs)

In the table, notes are shortened to one line; --notes shows them in full.

Runs are listed oldest first, so the newest is at the bottom, next to the
prompt. A footer gives the total number of runs and the run ID the GUI will
hand out next.

Standard library only: it runs the psql client (installed alongside the
database) with the GUI's connection settings, so it works from any directory
and without the conda env.
"""

import argparse
import os
import shutil
import subprocess
import sys

# The GUI's run-DB connection, hardwired in gui/ui_run_metadata.py (connect_to_vo_db).
RUN_DB = {'host': 'localhost', 'port': '5432', 'dbname': 'telescope_db', 'user': 'vo_admin', 'password': 'lsttkc#$!'}

# The same rule as read_last_run_id in gui/ui_run_metadata.py.
SUMMARY_QUERY = (
    "SELECT (SELECT count(*) FROM tblrun_info), "
    "GREATEST(CASE WHEN is_called THEN last_value + 1 ELSE last_value END, "
    "(SELECT COALESCE(MAX(run_id), 0) + 1 FROM tblrun_info)) "
    "FROM tblrun_info_run_id_seq"
)


# Every column but notes, which is folded onto one line and cut short so a long
# or multi-line note does not break the aligned table.
TABLE_COLUMNS = (
    "run_id, veritas_run_id, run_type, run_status, run_window, db_start_time, db_end_time, "
    "data_start_time, data_end_time, duration, telescope_mask, harvester_mask, source_id, "
    "CASE WHEN length(notes) > 60 THEN left(replace(notes, E'\\n', ' | '), 57) || '...' "
    "ELSE replace(notes, E'\\n', ' | ') END AS notes"
)


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"N must be at least 1, got {value}")
    return value


def run_psql(psql, query, *flags):
    """Run one query; exit with psql's own error message if it fails."""
    cmd = [psql, '-X', '-w', '-P', 'pager=off', *flags,
           '-h', RUN_DB['host'], '-p', RUN_DB['port'], '-U', RUN_DB['user'], '-d', RUN_DB['dbname'],
           '-c', query]
    env = dict(os.environ, PGPASSWORD=RUN_DB['password'], PGCONNECT_TIMEOUT='3')
    out = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if out.returncode != 0:
        sys.exit(f"Could not read {RUN_DB['dbname']} on {RUN_DB['host']}:{RUN_DB['port']} as {RUN_DB['user']}:\n"
                 f"{out.stderr.strip()}\n(Set the DB up with: sudo deploy/setup_postgres.sh)")
    return out.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('n', nargs='?', type=positive_int, help="show only the last N runs (default: all)")
    parser.add_argument('--notes', action='store_true', help="show the full notes of runs that have any")
    args = parser.parse_args()

    psql = shutil.which('psql')
    if psql is None:
        sys.exit("psql not found. It comes with PostgreSQL; this script needs it to read the run DB.")

    if args.n is None:
        runs = "tblrun_info"
    else:
        # Take the newest N, then list them oldest first.
        runs = f"(SELECT * FROM tblrun_info ORDER BY run_id DESC LIMIT {args.n}) AS last"

    if args.notes:
        query = f"SELECT run_id, notes FROM {runs} WHERE notes IS NOT NULL ORDER BY run_id"
        print(run_psql(psql, query, '-x') or "(no notes)\n", end='')
    else:
        query = f"SELECT {TABLE_COLUMNS} FROM {runs} ORDER BY run_id"
        print(run_psql(psql, query), end='')
    total, next_run = run_psql(psql, SUMMARY_QUERY, '-At').strip().split('|')
    shown = f"last {min(args.n, int(total))} of " if args.n is not None else ""
    print(f"Showing {shown}{total} runs. Next run ID: {next_run}")


if __name__ == '__main__':
    main()
