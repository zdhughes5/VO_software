# gui/db_worker_process.py
import pymysql
import time
from multiprocessing import Queue

def query_last_pointing(queue: Queue, db_config: dict):
    while True:
        start_time = time.time()
        dbcnx = pymysql.connect(**db_config)
        crs = dbcnx.cursor(pymysql.cursors.DictCursor)
        vpm = {}
        queries = {
            't1': 'SELECT elevation_raw, azimuth_raw FROM tblPositioner_Telescope0_Status ORDER BY timestamp DESC LIMIT 1',
            't2': 'SELECT elevation_raw, azimuth_raw FROM tblPositioner_Telescope1_Status ORDER BY timestamp DESC LIMIT 1',
            't3': 'SELECT elevation_raw, azimuth_raw FROM tblPositioner_Telescope2_Status ORDER BY timestamp DESC LIMIT 1',
            't4': 'SELECT elevation_raw, azimuth_raw FROM tblPositioner_Telescope3_Status ORDER BY timestamp DESC LIMIT 1'
        }
        for telescope, query in queries.items():
            query_start_time = time.time()
            crs.execute(query)
            res = crs.fetchone()
            query_elapsed_time = time.time() - query_start_time
            #print(f"Query for {telescope} took {query_elapsed_time:.4f} seconds")
            vpm[telescope] = {'elevation_raw': res['elevation_raw'], 'azimuth_raw': res['azimuth_raw']}
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
        
        time.sleep(2.5)  # Query every 1 second