# gui/db_worker_process.py
import logging
import pymysql
from datetime import datetime
from multiprocessing import Queue
from queue import Empty
from sys import exit

# Digits in a packed VERITAS DB timestamp: YYYYMMDDHHMMSSmmm.
_VDB_TIMESTAMP_DIGITS = 17


def parse_vdb_timestamp(stamp):
    """Parse a VERITAS DB timestamp into a naive UTC datetime.

    The positioner tables store these as a packed decimal rather than a SQL
    DATETIME, so pymysql hands back an int (or Decimal): 20260922022408512 is
    2026-09-22 02:24:08.512 UTC. A real datetime is passed through unchanged,
    in case some deployment does return one.

    Raises ValueError on anything else, so a format change surfaces instead of
    quietly becoming the wrong time.
    """
    if isinstance(stamp, datetime):
        return stamp

    text = str(stamp).strip()
    if not text.isdigit() or len(text) != _VDB_TIMESTAMP_DIGITS:
        raise ValueError(
            f"expected {_VDB_TIMESTAMP_DIGITS} digits (YYYYMMDDHHMMSSmmm), got {stamp!r}"
        )

    return datetime(
        year=int(text[0:4]), month=int(text[4:6]), day=int(text[6:8]),
        hour=int(text[8:10]), minute=int(text[10:12]), second=int(text[12:14]),
        microsecond=int(text[14:17]) * 1000,
    )


def query_last_pointing(queue: Queue, db_config: dict, command_queue: Queue, status_queue: Queue = None):
    """Poll the VERITAS DB for each telescope's latest pointing, every 2.5 s.

    Runs in its own process, which has no log handlers (it is started with
    forkserver), so log messages go back to the GUI as (level, message) pairs
    on status_queue, and database_worker logs them. A failure is reported once,
    and again only if the error changes; recovery is reported once. Polling
    keeps retrying every 2.5 s, so an unreachable DB cannot flood the log.
    """
    def report(level, message):
        if status_queue is not None:
            status_queue.put((level, message))
        else:
            print(message)

    last_error = None
    while True:
        dbcnx = None
        try:
            dbcnx = pymysql.connect(**db_config)
            crs = dbcnx.cursor(pymysql.cursors.DictCursor)
            vpm = {}
            # timestamp comes along so the star overlay can place stars at the
            # time the pointing was actually measured rather than at the time
            # the row was consumed, which lags by up to the poll interval.
            queries = {
                't1': 'SELECT timestamp, elevation_raw, azimuth_raw FROM tblPositioner_Telescope0_Status ORDER BY timestamp DESC LIMIT 1',
                't2': 'SELECT timestamp, elevation_raw, azimuth_raw FROM tblPositioner_Telescope1_Status ORDER BY timestamp DESC LIMIT 1',
                't3': 'SELECT timestamp, elevation_raw, azimuth_raw FROM tblPositioner_Telescope2_Status ORDER BY timestamp DESC LIMIT 1',
                't4': 'SELECT timestamp, elevation_raw, azimuth_raw FROM tblPositioner_Telescope3_Status ORDER BY timestamp DESC LIMIT 1'
            }
            for telescope, query in queries.items():
                crs.execute(query)
                res = crs.fetchone()
                vpm[telescope] = {'timestamp': res['timestamp'], 'elevation_raw': res['elevation_raw'], 'azimuth_raw': res['azimuth_raw']}
            crs.close()

            if not queue.full():
                queue.put(vpm)
            else:
                queue.get()
                queue.put(vpm)

            if last_error is not None:
                report(logging.INFO, "VERITAS pointing DB queries are working again.")
                last_error = None
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            if error != last_error:
                report(logging.ERROR, f"VERITAS pointing DB query failed: {error}. "
                                      "Retrying every 2.5 s; logged again only if the error changes, and when it clears.")
                last_error = error
        finally:
            if dbcnx is not None:
                try:
                    dbcnx.close()
                except Exception:
                    pass

        # Wait here after a failure too: retrying at once spun in a tight loop
        # against an unreachable DB and never saw the stop command.
        try:
            command_queue.get(timeout=2.5)
            exit(0)
        except Empty:
            pass
