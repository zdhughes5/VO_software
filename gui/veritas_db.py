"""Workers that talk to the VERITAS MySQL database.

``database_worker`` polls telescope pointing in a background thread and
turns it into the star field the camera panels draw.
``VeritasSQLPingWorker`` is a one-shot connectivity check.
"""

from astropy.coordinates import Angle, SkyCoord, EarthLocation
from multiprocessing import Process, Queue
from queue import Empty
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from astropy.time import Time
import astroplan as apl
import logging
import os
import pymysql
import signal
import time
from astropy import units as u

from star_display import DEFAULT_STAR_DISPLAY, PROCESS_JOIN_TIMEOUT_S
from star_display import MAX_POINTING_AGE_S
from qt_logging import logger
from db_worker_process import query_last_pointing, parse_vdb_timestamp
import star_field

class database_worker(QtCore.QObject):
    VPM_fetched_signal = QtCore.pyqtSignal(dict)
    star_field_signal = QtCore.pyqtSignal(dict)
    start_querying_VPM_signal = QtCore.pyqtSignal()
    stop_querying_VPM_signal = QtCore.pyqtSignal()
    query_run_number_signal = QtCore.pyqtSignal(int)
    query_timeout_signal = QtCore.pyqtSignal()
    query_ok_signal = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.vpm_timer = QtCore.QTimer()
        self.vpm_timer.timeout.connect(self.get_stars_in_fov)
        self.running = False
        self.basecamp = EarthLocation(lat=31.6716989799*u.deg, lon=-110.951291195*u.deg, height=1268*u.m)
        self.observer = apl.Observer(location=self.basecamp, name="VERITAS")
        self.catalog = star_field.load_star_catalog()
        self.star_display = dict(DEFAULT_STAR_DISPLAY)
        self.queue_check_counter = 0
        self.queue_check_interval = 2.5
        self.maximum_queue_checks = 5

        # A pointing row older than this is treated as "positioner parked":
        # keep its alt/az, but draw the stars that are there now.
        self.max_pointing_age_s = MAX_POINTING_AGE_S
        self.log_throttle_interval = 300.0
        self.log_throttle_state = {}

        # Database configuration
        self.db_config = {
            'host': 'romulus.ucsc.edu',
            'db': 'VERITAS',
            'user': 'readonly',
            'cursorclass': pymysql.cursors.DictCursor,
            'charset': 'utf8'
        }

        self.queue = Queue(maxsize=1)
        self.command_queue = Queue()
        # (level, message) from the worker process, which cannot log itself.
        self.status_queue = Queue()
        self.process = None

        self.start_querying_VPM_signal.connect(self.start_querying)
        self.stop_querying_VPM_signal.connect(self.stop_querying)

    def start_querying(self):
        if self.process is not None:
            self.stop_querying()
        self.process = Process(target=query_last_pointing, args=(self.queue, self.db_config, self.command_queue, self.status_queue))
        self.process.start()
        self.queue_check_counter = 0
        self.vpm_timer.start(int(self.queue_check_interval*1000))  # Check the queue every 2.5 seconds

    def stop_querying(self):
        #print("stop_querying called") 
        if self.process is not None:
            try:
                self.command_queue.put(False)
                #print('Put command')
                self.process.terminate()
                self.process.join(timeout=3)  # Wait for 5 seconds for the process to terminate
                if self.process.is_alive():
                    #print('bop')
                    os.kill(self.process.pid, signal.SIGKILL)
                    # Bounded: SIGKILL cannot be caught so this returns at once
                    # in practice, but an unbounded join here is the one call in
                    # the shutdown path that could still wedge the GUI.
                    self.process.join(timeout=PROCESS_JOIN_TIMEOUT_S)
                    if self.process.is_alive():
                        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
                        logger.log(logging.ERROR, f"Pointing subprocess {self.process.pid} survived SIGKILL; abandoning it.", extra=extra)
            except Exception as e:
                extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
                logger.log(logging.ERROR, f"Error terminating the pointing subprocess: {e}", extra=extra)
            finally:
                self.process = None
        self.vpm_timer.stop()
        self.log_worker_messages()

    def log_worker_messages(self):
        """Log whatever the pointing subprocess has reported (errors, recoveries)."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        while True:
            try:
                level, message = self.status_queue.get_nowait()
            except Empty:
                return
            except Exception as e:
                logger.log(logging.ERROR, f"Could not read the pointing subprocess's messages: {e}", extra=extra)
                return
            logger.log(level, message, extra=extra)


    def get_stars_in_fov(self):
        self.log_worker_messages()
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if not self.queue.empty():
            vpm = self.queue.get()
            if self.queue_check_counter >= self.maximum_queue_checks:
                logger.log(logging.INFO, "Pointing from the VERITAS MySQL DB worker resumed after %d seconds."
                           % (self.queue_check_counter*self.queue_check_interval), extra=extra)
            self.VPM_fetched_signal.emit(vpm)
            self.calculate_star_offsets(vpm)
            self.query_ok_signal.emit(True)
            self.queue_check_counter = 0
        else:
            self.queue_check_counter += 1
            if self.queue_check_counter >= self.maximum_queue_checks:
                self.query_ok_signal.emit(False)
                # Once per outage; the resume is logged above.
                if self.queue_check_counter == self.maximum_queue_checks:
                    logger.log(logging.WARNING, "Haven't got pointing from the VERITAS MySQL DB worker in %d seconds. "
                               "Not repeated; logged again when pointing resumes."
                               % (self.queue_check_counter*self.queue_check_interval), extra=extra)


    def log_throttled(self, key, level, message):
        """Log a recurring condition at most once every throttle_interval.

        The pointing poll runs every 2.5 s for four telescopes, so an
        unthrottled complaint about a stale row is ~96 log lines a minute --
        enough to bury everything else in the GUI log.
        """
        now = time.time()
        if now - self.log_throttle_state.get(key, 0.0) < self.log_throttle_interval:
            return

        self.log_throttle_state[key] = now
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName()}
        logger.log(level, message, extra=extra)

    def pointing_obstime(self, telescope, row):
        """Time to place stars at for one telescope's pointing row.

        The row's own timestamp is preferred over the wall clock, which lags it
        by up to the poll interval.

        A row far from the present is not trusted. While the positioner is
        parked its last status row can be hours old, and the telescope has not
        moved since -- so the stars to draw are the ones at that pointing
        *now*, not the ones that were there when the row was written. Falling
        back to the current time is the right answer for a stale row, and it
        also contains the damage if the stored timezone is ever not UTC.
        """
        stamp = row.get('timestamp')
        if stamp is None:
            return Time.now()

        try:
            obstime = Time(parse_vdb_timestamp(stamp), scale='utc')
        except Exception as e:
            self.log_throttled(
                (telescope, 'unparseable'), logging.ERROR,
                f"Could not read {telescope} pointing timestamp {stamp!r} ({e}); using current time.",
            )
            return Time.now()

        skew = (Time.now() - obstime).to_value(u.s)
        if abs(skew) > self.max_pointing_age_s:
            self.log_throttled(
                (telescope, 'stale'), logging.WARNING,
                f"{telescope} pointing row is {skew/60.0:+.1f} min from now (positioner parked, or "
                f"the timestamp is not UTC); drawing stars for the current time instead.",
            )
            return Time.now()

        return obstime

    def calculate_star_offsets(self, vpm):
        star_field_data = {}
        star_offsets = []
        star_offsets_labels = []
        star_sizes = []
        star_descriptions = []

        for telescope in ['t1', 't2', 't3', 't4']:
            row = vpm[telescope]
            obstime = self.pointing_obstime(telescope, row)
            current_pointing = SkyCoord(
                alt=row['elevation_raw']*u.rad, az=row['azimuth_raw']*u.rad,
                location=self.basecamp, obstime=obstime, frame='altaz',
            )
            # Camera coordinates, not raw alt/az offsets: the elevation axis is
            # flipped in the VERITAS camera frame. See star_field.py.
            s = self.star_display
            labels, xs, ys, vmag, descriptions = star_field.stars_in_fov(
                self.catalog, current_pointing,
                mag_min=s['mag_min'], mag_max=s['mag_max'],
                label_mag_max=s['label_mag_max'], label_scheme=s['label_scheme'],
            )
            star_offsets.append(list(zip(xs, ys)))
            star_offsets_labels.append(labels)
            star_sizes.append(star_field.marker_sizes(vmag))
            star_descriptions.append(descriptions)
        star_field_data['offsets'] = star_offsets
        star_field_data['labels'] = star_offsets_labels
        star_field_data['sizes'] = star_sizes
        star_field_data['descriptions'] = star_descriptions

        self.star_field_signal.emit(star_field_data)

    @QtCore.pyqtSlot(dict)
    def apply_star_display(self, settings):
        """Take new display settings from the options window.

        Invoked across the thread boundary, so Qt queues it onto this worker's
        thread; the dict is copied rather than shared.
        """
        self.star_display.update(settings)

    @QtCore.pyqtSlot(dict)
    def recompute_star_field(self, vpm):
        """Redraw the overlay from a pointing we already have.

        Lets a threshold drag take effect at once instead of at the next poll.
        """
        try:
            self.calculate_star_offsets(vpm)
        except Exception as e:
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName()}
            logger.log(logging.ERROR, f"Could not recompute the star field: {e}", extra=extra)

    def stop(self):
        self.stop_querying()

    def query_last_run_number(self):
        start_time = time.time()
        query = 'SELECT run_id FROM tblRun_Info ORDER BY db_start_time DESC LIMIT 1'
        self.fetch_data(query)
        elapsed_time = time.time() - start_time
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        logger.log(logging.DEBUG, f"query_last_run_number took {elapsed_time:.4f} seconds", extra=extra)

    def fetch_data(self, query):
        start_time = time.time()
        try:
            self.crs.execute(query)
            res = self.crs.fetchone()
            if res:
                return res
        except Exception as e:
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
            logger.log(logging.ERROR, f"Error querying the VERITAS database: {e}", extra=extra)
        elapsed_time = time.time() - start_time
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        logger.log(logging.DEBUG, f"fetch_data took {elapsed_time:.4f} seconds", extra=extra)


class VeritasSQLPingWorker(QtCore.QThread):
    result_signal = QtCore.pyqtSignal(bool)
    runid_signal = QtCore.pyqtSignal(int)
    error_signal = QtCore.pyqtSignal(str)

    def run(self):
        db_config = {
            'host': 'romulus.ucsc.edu',
            'db': 'VERITAS',
            'user': 'readonly',
            'cursorclass': pymysql.cursors.DictCursor,
            'charset': 'utf8'
        }
        try:
            dbcnx = pymysql.connect(**db_config)
            crs = dbcnx.cursor()
            query = 'SELECT run_id FROM tblRun_Info ORDER BY run_id DESC LIMIT 1'
            
            crs.execute(query)
            result = crs.fetchone()
            #print(result)
            crs.close()
            dbcnx.close()
            self.result_signal.emit(bool(result))
            self.runid_signal.emit(result['run_id'])

        except Exception as e:
            self.error_signal.emit(str(e))
