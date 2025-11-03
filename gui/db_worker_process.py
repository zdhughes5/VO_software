# gui/db_worker_process.py
import pymysql
import time
from multiprocessing import Queue
from queue import Empty
from sys import exit

def query_last_pointing(queue: Queue, db_config: dict, command_queue: Queue, observing_info_queue: Queue):
    n = 0
    dbcnx = pymysql.connect(**db_config)
    crs = dbcnx.cursor(pymysql.cursors.DictCursor)
    while True:
        start_time = time.time()
        try:

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


        except Exception as e:
            print(f"Error in query_last_pointing: {e}")
            continue

        obs_info = {}
        obs_query = 'SELECT run_id, run_status, run_type, source_id FROM tblRun_Info ORDER BY run_id DESC LIMIT 1'
        try:
            crs.execute(obs_query)
            res = crs.fetchone()
            if res:
                obs_info['run_id'] = res['run_id']
                obs_info['run_status'] = res['run_status']
                obs_info['run_type'] = res['run_type']
                obs_info['source_id'] = res['source_id']

                # if n % 5 == 0:
                #     obs_info['run_id'] = str(n)
                #     obs_info['run_status'] = 'started'
                #     obs_info['run_type'] = 'observing'
                #     obs_info['source_id'] = 'Crab'
                # if n % 10 == 0:
                #     obs_info['run_id'] = str(n)
                #     obs_info['run_status'] = 'ended'
                #     obs_info['run_type'] = 'observing' 
                #     obs_info['source_id'] = 'Crab'
                if obs_info:            
                    if not observing_info_queue.full():
                        observing_info_queue.put(obs_info)
                    else:
                        observing_info_queue.get()
                        observing_info_queue.put(obs_info)
        except Exception as e:
            print(f"Error fetching observing info: {e}")
            continue

        n += 1
        #print('Beep ', n)
        # Assuming command_queue is an instance of queue.Queue
        try:
            item = command_queue.get(timeout=0.1)  # Wait for up to 5 seconds
            print(f"VPM querying subprocess exiting...")
            exit(0)
            break
            # Process the item
        except Empty:
            # Handle the case where the queue is empty after the timeout
            #print("No command received")
            pass
        # Can I not close the cursor and connection here?
    else:
        print("Exiting query_last_pointing loop")
        # Clean up resources
        if crs:
            crs.close()
        dbcnx.close()