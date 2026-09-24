"""The star overlay and the VERITAS SQL thread that feeds it.

The thread lifecycle lives here rather than with the other database code
because ``database_worker`` exists only to produce this overlay: it polls
pointing, computes the star field, and this module draws it.
"""

from astropy.coordinates import Angle, SkyCoord, EarthLocation
from PyQt6.QtNetwork import QHostAddress, QUdpSocket, QNetworkDatagram
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from astropy.time import Time
import logging
import pyqtgraph as pg
import signal
from astropy import units as u

from star_display import DB_THREAD_WAIT_MS, DEFAULT_STAR_DISPLAY
from star_display import MAX_POINTING_AGE_S
from veritas_db import VeritasSQLPingWorker
from veritas_db import database_worker
from star_display import format_sexagesimal
from star_display import load_star_display_settings
from qt_logging import logger
from db_worker_process import query_last_pointing, parse_vdb_timestamp
from star_display import save_star_display_settings
import star_field
import star_options

class StarOverlayMixin:
    """Star overlay drawing and its data source.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_db_thread_state(self):
        """Extracted verbatim from Window.__init__ (lines 549-558 of the pre-split file)."""


        #self.listenSocket = QUdpSocket()
        #self.listenSocket.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        #self.listenSocket.readyRead.connect(self.getDatagramAndQueue)


        self.db_thread = None
        self.db_worker = None
        self.db_worker_active = False

    def _setup_data_display_buttons(self):
        """Extracted verbatim from Window.__init__ (lines 569-595 of the pre-split file)."""



        # Connect signals to mark widgets as modified
        self.star_field_request = False
        self.data_display_star_field_button.clicked.connect(self.requestStarField)

        # Most recent pointing rows, kept so the pointing can be printed on
        # demand rather than only when a fresh row happens to arrive.
        self.last_vpm = None
        self.data_display_pointing_button.clicked.connect(self.printPointing)

        # Star overlay display settings. Held here rather than on the worker so
        # they survive the SQL thread being stopped and restarted.
        self.star_display = load_star_display_settings()
        self.star_options_dialog = None
        self.data_display_star_options_button.clicked.connect(self.openStarOptions)

        self.data_display_clear_ts_button.clicked.connect(self.clear_time_series_data)
        self.veritas_sql_ping_button.clicked.connect(self.ping_veritas_sql)

        self.veritas_sql_status_start_button.clicked.connect(self.start_db_thread)
        self.veritas_sql_status_stop_button.clicked.connect(self.stop_db_thread)

        self.VO_server_start_button.clicked.connect(self.start_server)
        self.VO_server_stop_button.clicked.connect(self.stop_server)
        self.server_process = None  # Initialize the server process variable

    def start_db_thread(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if not self.db_worker_active:
            # Create the worker and thread
            self.db_worker = database_worker()
            self.db_thread = QtCore.QThread()

            # Move the worker to the thread
            self.db_worker.moveToThread(self.db_thread)

            # Connect signals and slots
            self.startWorkerSignal.connect(self.db_worker.start_querying_VPM_signal)
            self.stopWorkerSignal.connect(self.db_worker.stop_querying_VPM_signal)
            self.db_worker.VPM_fetched_signal.connect(self.handle_VPM_data)
            self.db_worker.star_field_signal.connect(self.draw_star_field)
            self.db_worker.query_ok_signal.connect(self.veritas_sql_status)

            # The worker starts on its defaults; hand it the persisted overlay
            # settings before it computes its first field.
            self.db_worker.apply_star_display(dict(self.star_display))

            # Start the thread
            self.db_thread.start()
            self.startWorkerSignal.emit()
            self.db_worker_active = True
            logger.log(logging.INFO, "Started VERITAS SQL database thread.", extra=extra)
            logger.log(logging.INFO, f"Star catalog: {len(self.db_worker.catalog):,} stars.", extra=extra)

    def veritas_sql_status(self, ok):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if ok:
            self.veritas_sql_status_line.setStyleSheet("background-color: green; color: white;")
            self.veritas_sql_status_line.setText("Running")
        else:
            self.veritas_sql_status_line.setStyleSheet("background-color: red; color: white;")
            self.veritas_sql_status_line.setText("Timeout")
            #logger.log(logging.WARNING, "VERITAS SQL database timeout.", extra=extra)

    def stop_db_thread(self):
        #print('What')
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.db_worker_active:
            self.stopWorkerSignal.emit()
            self.db_thread.quit()
            # Bounded, unlike stopWorker's, this one must not fall through on a
            # timeout: the teardown below calls deleteLater() on the thread, and
            # destroying a QThread that is still running crashes Qt. Leave the
            # worker marked active and let the operator try again.
            if not self.db_thread.wait(DB_THREAD_WAIT_MS):
                logger.log(logging.ERROR, f"VERITAS SQL thread did not stop within {DB_THREAD_WAIT_MS/1000:.0f} s; leaving it running rather than destroying a live thread. Try Stop again.", extra=extra)
                self.veritas_sql_status_line.setStyleSheet("background-color: red; color: white;")
                self.veritas_sql_status_line.setText("Stop failed")
                return

            # Disconnect signals to avoid any pending signal-slot connections
            self.stopWorkerSignal.disconnect(self.db_worker.stop_querying_VPM_signal)
            self.startWorkerSignal.disconnect(self.db_worker.start_querying_VPM_signal)
            self.db_worker.VPM_fetched_signal.disconnect(self.handle_VPM_data)
            self.db_worker.star_field_signal.disconnect(self.draw_star_field)
            self.db_worker.query_ok_signal.disconnect(self.veritas_sql_status)

            # Clean up the worker and thread
            self.db_worker.deleteLater()
            self.db_thread.deleteLater()
            self.db_worker_active = False

            self.veritas_sql_status_line.setStyleSheet("background-color: yellow; color: black;")
            self.veritas_sql_status_line.setText("Stopped") 
            logger.log(logging.INFO, "Stopped VERITAS SQL database thread.", extra=extra) 

    def ping_veritas_sql(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.worker = VeritasSQLPingWorker()
        self.worker.result_signal.connect(self.handle_ping_result)
        self.worker.error_signal.connect(self.handle_ping_error)
        logger.log(logging.INFO, "Pinging VERITAS SQL database...", extra=extra)
        self.worker.start()

    def query_veritas_sql(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.worker = VeritasSQLPingWorker()
        self.worker.runid_signal.connect(self.update_veritas_runid)
        self.worker.error_signal.connect(self.handle_ping_error)
        logger.log(logging.INFO, "Querying VERITAS SQL database...", extra=extra)
        self.worker.start()

    def update_veritas_runid(self, runid):
        self.obs_params_veritas_runid_spin.setValue(runid)

    def handle_ping_result(self, success):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if success:
            self.veritas_sql_ping_line.setStyleSheet("background-color: green; color: white;")
            self.veritas_sql_ping_line.setText("Success!")
            logger.log(logging.INFO, "VERITAS SQL database ping successful.", extra=extra)
        else:
            self.veritas_sql_ping_line.setStyleSheet("background-color: red; color: white;")
            self.veritas_sql_ping_line.setText("Failed!")
            logger.log(logging.INFO, "VERITAS SQL database ping failed.", extra=extra)

    def handle_ping_error(self, error_message):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.veritas_sql_ping_line.setStyleSheet("background-color: red; color: white;")
        self.veritas_sql_ping_line.setText("Failed!")
        QtWidgets.QMessageBox.critical(None, "Database Error", error_message)
        logger.log(logging.ERROR, f"Error pinging VERITAS SQL database: {error_message}", extra=extra)

    def requestStarField(self):
        self.star_field_request = True

    def openStarOptions(self):
        """Show the non-modal Star Field Options window.

        The catalog is only loaded inside database_worker, so the dialog needs
        the SQL thread running -- that is also the only state in which changing
        the settings would show anything.
        """
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName()}

        if self.star_options_dialog is not None:
            self.star_options_dialog.show()
            self.star_options_dialog.raise_()
            self.star_options_dialog.activateWindow()
            return

        if not self.db_worker_active or self.db_worker is None:
            logger.log(logging.WARNING, "Star options need the star catalog -- start the VERITAS SQL database thread first.", extra=extra)
            return

        self.star_options_dialog = star_options.StarOptionsDialog(
            self.db_worker.catalog, self.star_display, DEFAULT_STAR_DISPLAY, parent=self)
        self.star_options_dialog.settings_changed.connect(self.applyStarDisplay)
        self.star_options_dialog.show()

    def applyStarDisplay(self, settings):
        """Push new overlay settings to the worker and redraw immediately."""
        self.star_display.update(settings)
        save_star_display_settings(self.star_display)

        if self.db_worker is None:
            return

        # Queued across the thread boundary by Qt, so the worker mutates its
        # own copy on its own thread.
        QtCore.QMetaObject.invokeMethod(
            self.db_worker, 'apply_star_display', QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(dict, dict(self.star_display)))

        # Redraw from the last pointing rather than waiting out the 2.5 s poll,
        # so dragging a threshold changes the camera panels as you drag.
        if self.last_vpm:
            QtCore.QMetaObject.invokeMethod(
                self.db_worker, 'recompute_star_field', QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(dict, dict(self.last_vpm)))

    def stopWorker(self):
        if self.db_worker_active:
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
            self.stopWorkerSignal.emit()
            self.db_thread.quit()
            # Bounded so a wedged worker can never freeze application shutdown.
            # Nothing follows this call, so carrying on after a timeout is safe;
            # the thread is left running and the process exit reaps it.
            if not self.db_thread.wait(DB_THREAD_WAIT_MS):
                logger.log(logging.WARNING, f"VERITAS SQL thread did not stop within {DB_THREAD_WAIT_MS/1000:.0f} s; continuing without it.", extra=extra)

    def handle_VPM_data(self, vpm):

        # Handle the new data fetched from the database
        self.last_vpm = vpm
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = '\n'
        for key, value in vpm.items():
            print_string += f"Telescope {key} - Elevation: {value['elevation_raw']}, Azimuth: {value['azimuth_raw']}\n"
        #logger.log(logging.INFO, print_string, extra=extra)

    def printPointing(self):
        """Dump the latest telescope pointings to the log as Az/Alt sexagesimal.

        Formatted for pasting straight into Stellarium's search window, which
        is why azimuth comes first and each pair sits on one line.
        """
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }

        if not self.last_vpm:
            logger.log(logging.WARNING, "No telescope pointing yet -- start the VERITAS SQL database thread first.", extra=extra)
            return

        print_string = '\nTelescope pointing (Azimuth, Altitude)\n'
        print_string += '______________________________________\n'

        for telescope in ['t1', 't2', 't3', 't4']:
            row = self.last_vpm.get(telescope)
            if row is None:
                print_string += f"{telescope.upper()}: no data\n"
                continue

            az = Angle(row['azimuth_raw']*u.rad).wrap_at(360*u.deg)
            alt = Angle(row['elevation_raw']*u.rad)
            print_string += f"{telescope.upper()}: {format_sexagesimal(az)}  {format_sexagesimal(alt)}\n"

            # The positioner only writes status while it is moving, so a parked
            # telescope's last row can be hours old. Say so -- pasting a stale
            # pointing into Stellarium silently gives the wrong field.
            age = self.pointing_age_minutes(row)
            if age is None:
                print_string += "    (row timestamp unreadable)\n"
            elif abs(age) * 60.0 > MAX_POINTING_AGE_S:
                print_string += f"    (STALE: row is {age:+.1f} min old)\n"

        logger.log(logging.INFO, print_string, extra=extra)

    def pointing_age_minutes(self, row):
        """Age of a pointing row in minutes, or None if it cannot be read."""
        stamp = row.get('timestamp')
        if stamp is None:
            return None

        try:
            obstime = Time(parse_vdb_timestamp(stamp), scale='utc')
        except Exception:
            return None

        return (Time.now() - obstime).to_value(u.min)

    def draw_star_field(self, star_field_data):
        #print("self.star_field", self.star_field)
        #print("star_positions", array_star_positions)
        array_star_positions = star_field_data['offsets']
        array_star_labels = star_field_data['labels']
        array_star_sizes = star_field_data.get('sizes')
        array_star_descriptions = star_field_data.get('descriptions')
        #print(self.star_field_labels)
        for i in range(4):
            if self.star_field[i] is not None:
                # The name labels are child items of the scatter plot, so
                # removing it takes them with it.
                self.ws[i].removeItem(self.star_field[i])
        self.star_field = [None, None, None, None]
        self.star_field_labels = [None, None, None, None]
        border_pen = pg.mkPen(color='k', width=1)  # Black border with width 1
        for i, star_positions in enumerate(array_star_positions):
            if len(star_positions) > 0:
                # star_field.stars_in_fov emits camera (x, y) pairs.
                xs, ys = list(zip(*star_positions))
                # Brighter stars draw larger; hovering shows every identifier
                # the star has, so the compact on-camera label can stay short.
                sizes = array_star_sizes[i] if array_star_sizes is not None else 20
                hover_data = (array_star_descriptions[i]
                              if array_star_descriptions is not None
                              else array_star_labels[i])
                scatter_plot = pg.ScatterPlotItem(
                    x=xs,
                    y=ys,
                    brush=pg.mkColor('r'),
                    size=sizes,
                    pen=border_pen,
                    symbol='star',
                    pxMode=True,  # Set pxMode=False to allow spots to transform with the view
                    hoverable=True,
                    useCache=True,
                    antialias=False,
                    data=hover_data
                )
                self.star_field[i] = scatter_plot
                self.ws[i].addItem(scatter_plot)
                font = QtGui.QFont()
                font.setPointSize(8)  # Set the font size to 12
                font.setBold(True)
                text_items = []
                for j, point in enumerate(scatter_plot.points()):
                    # Stars fainter than the label threshold get an empty
                    # label; skip them rather than parenting an empty item.
                    text = str(array_star_labels[i][j])
                    if not text:
                        continue
                    x, y = point.pos()
                    text_item = pg.TextItem(text=text, anchor=(0, 0.75))
                    text_item.setParentItem(scatter_plot)
                    text_item.setPos(x, y)
                    text_item.setFont(font)
                    text_items.append(text_item)
                self.star_field_labels[i] = text_items
            else:
                self.star_field[i] = None
                self.star_field_labels[i] = None
        if self.star_field_request:
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
            print_string = '\n'
            for i in range(4):
                print_string += f"\nTelescope {i+1} - Stars in FOV: {len(array_star_labels[i])}\n"
                print_string += f"___________________________________\n"
                for j, star in enumerate(array_star_labels[i]):
                    x, y = array_star_positions[i][j]
                    # The dump carries every identifier, not just the compact
                    # on-camera label -- that is what gets cross-referenced.
                    full = (array_star_descriptions[i][j]
                            if array_star_descriptions is not None else star)
                    print_string += f"Star {j+1}: {full}\n"
                    print_string += f"Camera x, y (deg): {x:+.3f}, {y:+.3f}\n"
                    print_string += f"-----------------------------------\n"
            logger.log(logging.INFO, print_string, extra=extra)
            self.star_field_request = False
        return
