# gui/db_worker_process.py
import pymysql
import time
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


def query_last_pointing(queue: Queue, db_config: dict, command_queue: Queue):
    n = 0
    while True:
        start_time = time.time()
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
                query_start_time = time.time()
                crs.execute(query)
                res = crs.fetchone()
                query_elapsed_time = time.time() - query_start_time
                #print(f"Query for {telescope} took {query_elapsed_time:.4f} seconds")
                vpm[telescope] = {'timestamp': res['timestamp'], 'elevation_raw': res['elevation_raw'], 'azimuth_raw': res['azimuth_raw']}
            total_elapsed_time = time.time() - start_time
            #print(f"Total query_last_pointing took {total_elapsed_time:.4f} seconds")
            
            if not queue.full():
                queue.put(vpm)
            else:
                queue.get()
                queue.put(vpm)

            # Can I not close the cursor and connection here?
            crs.close()
            dbcnx.close()
        except Exception as e:
            print(f"Error in query_last_pointing: {e}")
            continue
        n += 1
        #print('Beep ', n)
        # Assuming command_queue is an instance of queue.Queue
        try:
            item = command_queue.get(timeout=2.5)  # Wait for up to 5 seconds
            print(f"VPM querying subprocess exiting...")
            exit(0)
            break
            # Process the item
        except Empty:
            # Handle the case where the queue is empty after the timeout
            #print("No command received")
            pass
