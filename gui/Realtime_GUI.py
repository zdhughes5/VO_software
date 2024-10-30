#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Oct 11 20:54:47 2022

@author: zdhughes
"""

#TODO: Finishing porting traceAnalysis into the program.
#scp zdhughes@herc3:~/c_ether/server_FADC.c ./
#gcc server_FADC.c -lfadc -lvme -lm -o server

# Janurary - updated GUI to show simulated stars, catalog points and field rotations
# Zero order simulated stars, gaussian smeared out over some spatial spread.
# Do a ratio of integral fluxes for TXS in soft and medium.

from GUI import Ui_MainWindow
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from time import perf_counter
from pyqtgraph.Qt.QtGui import QBrush, QColor
from ast import literal_eval as  le
from PyQt6.QtNetwork import QHostAddress, QUdpSocket
import sys
from time import sleep
import logging
from string import ascii_lowercase as alc
from string import ascii_uppercase as auc
import pymysql
from astropy.coordinates import AltAz, SkyCoord, EarthLocation
from astropy.time import Time
from astropy import units as u
import astroplan as apl
import time
from multiprocessing import Process, Queue
from db_worker_process import query_last_pointing
import json
import resources_rc
import os
import signal
import subprocess
import psycopg
from datetime import datetime
import struct





fs = '[%(asctime)s %(levelname)s] %(message)s'
formatter = logging.Formatter(fs)
#ogging.basicConfig(format='[%(asctime)s line %(lineno)d %(qThreadName)s %(levelname)s] %(message)s', handlers=[logging.FileHandler("debug.log", mode="w")])
logging.basicConfig(format='[%(asctime)s line %(lineno)d %(qThreadName)s %(levelname)s] %(message)s', handlers=[logging.FileHandler("debug.log", mode="w")])
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class LogSignalEmitter(QtCore.QObject):
    logSignal = QtCore.pyqtSignal(str, logging.LogRecord)


class QLogHandler(logging.Handler):
    def __init__(self, emitter, slotFunc, *args, **kwargs):
        super(QLogHandler, self).__init__(*args, **kwargs)
        self._emitter = emitter
        self._emitter.logSignal.connect(slotFunc)

    @property
    def emitter(self):
        return self._emitter

    def emit(self, record):
        msg = self.format(record)
        self.emitter.logSignal.emit(msg, record)

class NamedSkyCoord(SkyCoord):
    def __init__(self, *args, star_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.star_name = star_name

    def __repr__(self):
        base_repr = super().__repr__()
        return f"{base_repr}, star_name={self.star_name}"

    def __str__(self):
        base_str = super().__str__()
        return f"{base_str}, star_name={self.star_name}"

    def __getitem__(self, item):
        sliced_obj = super().__getitem__(item)
        if isinstance(sliced_obj, SkyCoord):
            return NamedSkyCoord(sliced_obj, star_name=self.star_name[item])
        return sliced_obj

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
        with open('catalogs/asu2.dat', 'r') as f:
            lines = [x for x in f]
        self.star_names = np.array([x.split()[0] for x in lines])
        star_RA_deg = np.array([float(x.split()[1]) for x in lines])
        star_DEC_deg = np.array([float(x.split()[2]) for x in lines])
        self.stars = SkyCoord(ra=star_RA_deg*u.deg, dec=star_DEC_deg*u.deg)
        self.queue_check_counter = 0
        self.queue_check_interval = 2.5
        self.maximum_queue_checks = 5

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
        self.process = None

        self.start_querying_VPM_signal.connect(self.start_querying)
        self.stop_querying_VPM_signal.connect(self.stop_querying)

    def start_querying(self):
        if self.process is not None:
            self.stop_querying()
        self.process = Process(target=query_last_pointing, args=(self.queue, self.db_config, self.command_queue))
        self.process.start()
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
                    self.process.join()
            except Exception as e:
                print(f"Error terminating process: {e}")
            finally:
                self.process = None
        self.vpm_timer.stop()


    def get_stars_in_fov(self):
        if not self.queue.empty():
            vpm = self.queue.get()
            self.VPM_fetched_signal.emit(vpm)
            self.calculate_star_offsets(vpm)
            self.query_ok_signal.emit(True)
            self.queue_check_counter = 0
        else:
            self.queue_check_counter += 1
            if self.queue_check_counter >= self.maximum_queue_checks:
                extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
                self.query_ok_signal.emit(False)
                if self.queue_check_counter % self.maximum_queue_checks == 0:
                    logger.log(logging.WARNING, "Haven't got pointing from VERITAS MySQL DB worker in %d seconds" % (self.queue_check_counter*self.queue_check_interval), extra=extra)


    def calculate_star_offsets(self, vpm):
        current_time = Time.now()
        stars_altaz = self.stars.transform_to(AltAz(obstime=current_time, location=self.basecamp))
        star_field_data = {}
        star_offsets = []
        star_offsets_labels = []

        for telescope in ['t1', 't2', 't3', 't4']:
            current_pointing = SkyCoord(alt=vpm[telescope]['elevation_raw']*u.rad, az=vpm[telescope]['azimuth_raw']*u.rad, location=self.basecamp, obstime=current_time, frame='altaz')
            separation = current_pointing.separation(stars_altaz)
            stars_in_fov = stars_altaz[separation < 2*u.deg]
            dazs, dalts = current_pointing.spherical_offsets_to(stars_in_fov)
            dazs_deg = dazs.degree
            dalts_deg = dalts.degree
            stars_offsets_in_fov = list(zip(dalts_deg, dazs_deg))
            star_offsets_labels_in_fov = self.star_names[separation < 2*u.deg]
            star_offsets.append(stars_offsets_in_fov)
            star_offsets_labels.append(star_offsets_labels_in_fov)
        star_field_data['offsets'] = star_offsets
        star_field_data['labels'] = star_offsets_labels

        self.star_field_signal.emit(star_field_data)

    def stop(self):
        self.stop_querying()

    def query_last_run_number(self):
        start_time = time.time()
        query = 'SELECT run_id FROM tblRun_Info ORDER BY db_start_time DESC LIMIT 1'
        self.fetch_data(query)
        elapsed_time = time.time() - start_time
        print(f"query_last_run_number took {elapsed_time:.4f} seconds")

    def fetch_data(self, query):
        start_time = time.time()
        try:
            self.crs.execute(query)
            res = self.crs.fetchone()
            if res:
                return res
        except Exception as e:
            print(f"Error querying database: {e}")
        elapsed_time = time.time() - start_time
        print(f"fetch_data took {elapsed_time:.4f} seconds")

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



class Window(QtWidgets.QMainWindow, Ui_MainWindow):

    startWorkerSignal = QtCore.pyqtSignal()
    stopWorkerSignal = QtCore.pyqtSignal()
    printStarFieldSignal = QtCore.pyqtSignal()
    
    '''This is the main application window.'''
    COLORS = {
        logging.DEBUG: 'blue',
        logging.INFO: 'white',
        logging.WARNING: 'yellow',
        logging.ERROR: 'red',
        logging.CRITICAL: 'purple',
    }
    LOG_LEVELS = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    def __init__(self):
        #Execute the QMainWindow __init__. 
        #QMainWindow is a QWidget; a widget without a parent is a window.
        super().__init__()
        #Draw all the stuff from the UI file.
        self.setupUi(self)
        #self.log_box.setStyleSheet("color: white; background-color: #1b1b1b; font-weight: bold;")

        self.logEmitter = LogSignalEmitter()
        self.logHandler = QLogHandler(self.logEmitter, self.updateLog)
        self.logHandler.setFormatter(formatter)
        logger.addHandler(self.logHandler)
        self.logHandler.setLevel('INFO')

        self.actionExit.triggered.connect(self.close)

        self.config_data = None

        self.starPos = [(0,0)]
        self.star_field = [None, None, None, None]
        self.star_field_labels = [None, None, None, None]

        self.weights = np.zeros(499)
        self.hexSize = 13
        self.cameraView.ci.setBorder((50, 50, 100))
        self.w1 = self.cameraView.addViewBox(enableMouse=False)
        self.w2 = self.cameraView.addViewBox(enableMouse=False)
        self.cameraView.nextRow()
        self.w3 = self.cameraView.addViewBox(enableMouse=False)
        self.w4 = self.cameraView.addViewBox(enableMouse=False)
        self.cameraView.nextRow()
        self.w5 = self.cameraView.addPlot(colspan=2)
        self.ws = [self.w1, self.w2, self.w3, self.w4, self.w5]

        # Example values for zooming in
        xmin, xmax = -1.85, 1.85
        ymin, ymax = -1.865, 1.865

        # Set the range for each ViewBox
        self.w1.setRange(xRange=[xmin, xmax], yRange=[ymin, ymax])
        self.w2.setRange(xRange=[xmin, xmax], yRange=[ymin, ymax])
        self.w3.setRange(xRange=[xmin, xmax], yRange=[ymin, ymax])
        self.w4.setRange(xRange=[xmin, xmax], yRange=[ymin, ymax])

        self.w1.setAspectLocked()
        self.w2.setAspectLocked()
        self.w3.setAspectLocked()
        self.w4.setAspectLocked()

        self.w1, self.s1, self.spots1, self.xs, self.ys, self.labels = self.createCameraPixelArray(self.w1)
        self.w2, self.s2, self.spots1, self.xs, self.ys, self.labels = self.createCameraPixelArray(self.w2)
        self.w3, self.s3, self.spots1, self.xs, self.ys, self.labels = self.createCameraPixelArray(self.w3)
        self.w4, self.s4, self.spots1, self.xs, self.ys, self.labels = self.createCameraPixelArray(self.w4)
        self.points = list(zip(self.xs, self.ys))

        #self.nPts = 255
        self.nPts = 255
        self.ptr1 = -1000
        self.colormap = pg.colormap.get('CET-CBL2')
        self.valueRange = np.linspace(0, 66000, num=self.nPts)
        #self.valueRange = np.linspace(0, 255, num=self.nPts)
        self.colors = self.colormap.getLookupTable(0, 1, nPts=self.nPts+1)
        self.colors2 = np.array([QBrush(QColor(*i)) for i in self.colors])
        
        self.pixelTimeSeriesData1 = np.zeros(1000)
        self.pixelTimeSeriesData2 = np.zeros(1000)
        self.pixelTimeSeriesData3 = np.zeros(1000)
        self.pixelTimeSeriesData4 = np.zeros(1000)
        self.pixelTimeSeriesDataCurve1 = pg.PlotCurveItem(self.pixelTimeSeriesData1, pen=(255,0,0), antialias=False, skipFiniteCheck=True)
        self.pixelTimeSeriesDataCurve2 = pg.PlotCurveItem(self.pixelTimeSeriesData2, antialias=False, skipFiniteCheck=True)
        self.pixelTimeSeriesDataCurve3 = pg.PlotCurveItem(self.pixelTimeSeriesData3, pen=(0,255,0), antialias=False, skipFiniteCheck=True)
        self.pixelTimeSeriesDataCurve4 = pg.PlotCurveItem(self.pixelTimeSeriesData4, pen=(0,0,255), antialias=False, skipFiniteCheck=True)
        self.w5.addItem(self.pixelTimeSeriesDataCurve1)
        self.w5.addItem(self.pixelTimeSeriesDataCurve2)
        self.w5.addItem(self.pixelTimeSeriesDataCurve3)
        self.w5.addItem(self.pixelTimeSeriesDataCurve4)

        thick_pen = pg.mkPen((255, 0, 0), width=3)
        self.roi1 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=thick_pen, handlePen=thick_pen)
        self.roi2 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=thick_pen, movable=False, resizable=False)
        self.roi3 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=thick_pen, movable=False, resizable=False)
        self.roi4 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=thick_pen, movable=False, resizable=False)
        self.rois = [self.roi1, self.roi2, self.roi3, self.roi4]
        self.w1.addItem(self.roi1)
        self.w2.addItem(self.roi2)
        self.w3.addItem(self.roi3)
        self.w4.addItem(self.roi4)
        self.roi2.removeHandle(0)
        self.roi3.removeHandle(0)
        self.roi4.removeHandle(0)
        self.selected = np.zeros(1, dtype=int)

        self.pixelData = np.zeros(2000) # Initialize the pixel data array.
        
        # This is really slow!
        self.fps = None
        self.lastTime = perf_counter()
        
        #self.update()
        self.w1.disableAutoRange()
        self.w2.disableAutoRange()
        self.w3.disableAutoRange()
        self.w4.disableAutoRange()
        #w5.disableAutoRange(axis=0)
        self.firstFlip = False


        self.roi1.sigRegionChanged.connect(self.updateROI)
        
        self.updateROI(self.roi1)
        
        self.StartButton.clicked.connect(self.startRun)
        self.StopButton.clicked.connect(self.send_stop_message)
        self.s1.scene().sigMouseMoved.connect(self.onMouseMoved)


        self.config_file = '../server/internal/server.json'
        self.load_config_file()
        self.establish_connections()



        #self.listenSocket = QUdpSocket()
        #self.listenSocket.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        #self.listenSocket.readyRead.connect(self.getDatagramAndQueue)


        self.db_thread = None
        self.db_worker = None
        self.db_worker_active = False



        self.actionLoad_state_file.triggered.connect(self.load_state_file)
        #self.actionLoad_config_file.triggered.connect(self.load_config_file)
        self.state_edit_check.toggled.connect(self.toggle_state_edit)  # Connect the checkbox to the function
        self.state_edit_check_was_checked = self.state_edit_check.isChecked()  # Store the initial state of the checkbox
        self.state_edit_set_button.clicked.connect(self.set_changes)
        self.state_edit_undo_button.clicked.connect(self.undo_changes)




        # Connect signals to mark widgets as modified
        self.star_field_request = False
        self.data_display_star_field_button.clicked.connect(self.requestStarField)

        self.data_display_clear_ts_button.clicked.connect(self.clear_time_series_data)
        self.veritas_sql_ping_button.clicked.connect(self.ping_veritas_sql)

        self.veritas_sql_status_start_button.clicked.connect(self.start_db_thread)
        self.veritas_sql_status_stop_button.clicked.connect(self.stop_db_thread)

        self.VO_server_start_button.clicked.connect(self.start_server)
        self.VO_server_stop_button.clicked.connect(self.stop_server)
        self.server_process = None  # Initialize the server process variable

        self.obs_params = {
            'SavePath': self.obs_params_save_path_line.text(),
            'SourceID': self.obs_params_sourceid_line.text(),
            'VERITASRunNumber': self.obs_params_veritas_runid_spin.value(),
            'RunType': self.obs_params_run_type_combo.currentText(),
            'RunDuration': self.obs_params_duration_spin.value(),
        }
        self.VO_db_params_sourceid_line.setText(self.obs_params['SourceID'])
        self.VO_db_params_vrunid_line.setText(str(self.obs_params['VERITASRunNumber']))
        self.VO_db_params_run_type_line.setText(self.obs_params['RunType'])
        self.VO_db_params_duration_line.setText(str(self.obs_params['RunDuration']))
        self.obs_connect_signals_to_mark_modified()
        self.obs_params_set_button.clicked.connect(self.obs_set_changes)
        self.obs_params_undo_button.clicked.connect(self.obs_undo_changes)
        self.obs_params_veritas_runid_query_button.clicked.connect(self.query_veritas_sql)

        self.VO_db_params = {
            'run_id': '',
            'veritas_run_id': '',
            'run_type': '',
            'run_status': '',
            'run_window': '',
            'db_start_time': '',
            'db_end_time': '',
            'data_start_time': '',
            'data_end_time': '',
            'duration': '',
            'telescope_mask': '',
            'harvester_mask': '',
            'source_id': ''
        }
        self.VO_db_params_filled = {
            'run_id': False,
            'veritas_run_id': False,
            'run_type': False,
            'run_status': False,
            'run_window': False,
            'db_start_time': False,
            'db_end_time': False,
            'data_start_time': False,
            'data_end_time': False,
            'duration': False,
            'telescope_mask': False,
            'harvester_mask': False,
            'source_id': False
        }


        self.read_last_run_id()

        self.test_button.clicked.connect(self.dump_VO_db_params)


        self.VO_db_params_runid_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_vrunid_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_run_type_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_run_status_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_run_window_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_db_start_time_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_db_end_time_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_data_start_time_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_data_end_time_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_duration_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_telescope_mask_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_harvester_mask_line.textChanged.connect(self.update_VO_db_params)
        self.VO_db_params_sourceid_line.textChanged.connect(self.update_VO_db_params)

        self.update_VO_db_params()

        self.populate_dt.clicked.connect(self.set_current_datetime)
        self.wrtie_db.clicked.connect(self.write_VO_db_params_to_db)

        self.fadc_gate_array_window_set_button.clicked.connect(self.set_fadc_gate_array_window)

        self.send_stop_button.clicked.connect(self.send_stop_message)
        self.StartButton.clicked.connect(self.request_listen)

        self.harvester_command_c001_button.clicked.connect(lambda: self.send_harvester_packet('c001', log=True))
        self.harvester_command_c002_button.clicked.connect(lambda: self.send_harvester_packet('c002', log=True))
        self.harvester_command_c003_button.clicked.connect(lambda: self.send_harvester_packet('c003', log=True))
        self.harvester_command_c004_button.clicked.connect(lambda: self.send_harvester_packet('c004', log=True))
        
        # Initialize the timer
        self.harvester_timer = QtCore.QTimer(self)
        self.harvester_timer.timeout.connect(lambda: self.send_harvester_packet('c004'))
        
        self.harvester_command_start_time_pulse_button.clicked.connect(self.start_harvester_timer)
        self.harvester_command_stop_time_pulse_button.clicked.connect(self.stop_harvester_timer)
    

    def start_harvester_timer(self):
        self.harvester_timer.start(1000)  # Start the timer with a 1-second interval
        self.harvester_command_time_status_label.setStyleSheet("background-color: green; color: white;")
        self.harvester_command_time_status_label.setText("Active")
    
    def stop_harvester_timer(self):
        self.harvester_timer.stop()  # Stop the timer
        self.harvester_command_time_status_label.setStyleSheet("background-color: yellow; color: black;")
        self.harvester_command_time_status_label.setText("Inactive")


    def send_harvester_packet(self, command, log=False):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        try:
            # Define the host and port from the configuration
            host = QHostAddress(self.config_data['harvesterControlConnIP'].split(':')[0])
            port = int(self.config_data['harvesterControlConnIP'].split(':')[1])
            
            # Prepare the data to be sent
            if command == 'c004':
                hex_timestamp = self.get_hex_timestamp()
                big_send = True
            else:
                big_send = False
            
            if big_send:
                hex_timestamp = int(hex_timestamp, 16)
                datum = struct.pack('>HI', int(command, 16), hex_timestamp)
            else:
                datum = struct.pack('>HI', int(command, 16), 0)
            
            # Send the datagram using self.heartbeatSocket
            self.heartbeatSocket.writeDatagram(datum, host, port)
            if log:
                logger.log(logging.INFO, f'Sent datagram: {datum}', extra=extra)
        except Exception as e:
            logger.log(logging.ERROR, f'Failed to send UDP packet: {e}', extra=extra)
    
    def get_hex_timestamp(self):
        timestamp = int(time.time())
        return hex(timestamp)[2:]

    def get_VO_db_params_filled_short(self):
        return {key: self.VO_db_params_filled[key] for key in ['run_id', 'veritas_run_id', 'run_type', 'run_window', 'duration', 'telescope_mask', 'harvester_mask', 'source_id']}

    def request_listen(self):
        # Create data_map with parameters from VO_db_params and self.config_data
        data_map = {
            "command": int(self.config_data['commands']['startRunCmd']),
            "runNumber": int(self.VO_db_params['run_id']),
            "duration": int(self.VO_db_params['duration']),
            "sendInterval": int(self.config_data['sendInterval']),
            "dataSaveDir": self.config_data['dataSavePath'],
            "state": json.dumps(self.state_data)  # Use self.state_data instead of reading the state.json file
        }

        # Convert map to JSON



        try:
            json_data = json.dumps(data_map)
        except json.JSONEncodeError as err:
            print(f"Error marshaling JSON: {err}")
            return

        #print(f"command is type {type(data_map['command'])}")

        server_control_ip, server_control_port = self.config_data['serverControlConnIP'].split(':')
        server_control_port = int(server_control_port)

        datagram = json_data.encode()

        try:
            self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port)
        except Exception as err:
            print(f"Error sending JSON over UDP: {err}")



    def execute_binary_over_ssh(self, hostname, username, binary_path, argument):
        """
        Executes a binary on a remote server over SSH.

        :param hostname: The hostname or IP address of the remote server.
        :param username: The username for the SSH connection.
        :param binary_path: The path to the binary on the remote server.
        :param argument: The command line argument to pass to the binary.
        """
        try:
            # Construct the SSH command
            ssh_command = f"ssh {username}@{hostname} '{binary_path} {argument}'"
            
            # Execute the command
            process = subprocess.Popen(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Read the output and error streams
            output, error = process.communicate()
            
            # Decode the output and error
            output = output.decode()
            error = error.decode()
            
            # Log the output and errors
            if output:
                logger.info(f"Output: {output}")
            if error:
                logger.error(f"Error: {error}")
            
        except Exception as e:
            logger.error(f"Failed to execute binary over SSH: {str(e)}")

    def set_fadc_gate_array_window(self):
        self.VO_db_params_run_window_line.setText(self.fadc_gate_array_window_combo.currentText().split(' ')[0])
        #self.execute_binary_over_ssh('10.0.7.20', 'observer', '/home/zdhughes/c_ether/server_FADC', f'{self.fadc_gate_array_window_combo.currentText().split(' ')[0]}')

    def set_current_datetime(self):
        self.VO_db_params_run_status_line.setText('ended')
        self.VO_db_params_db_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.VO_db_params_data_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


    def write_VO_db_params_to_db(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if not self.check_VO_db_params_filled(self.VO_db_params):
            logger.log(logging.WARNING, "Not all VO DB parameters are filled.", extra=extra)
            return

        connection, cursor = None, None
        try:
            # Connect to the database
            connection = psycopg.connect(
                dbname="telescope_db",
                user="vo_admin",
                password="lsttkc#$!",
                host="localhost",
                port="5432"
            )
            cursor = connection.cursor()

            # Insert the data into the database
            insert_query = """
            INSERT INTO tblrun_info (veritas_run_id, run_type, run_status, run_window, db_start_time, db_end_time, data_start_time, data_end_time, duration, telescope_mask, harvester_mask, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            run_data = (
                self.VO_db_params['veritas_run_id'],  # integer
                self.VO_db_params['run_type'],  # character varying(20)
                self.VO_db_params['run_status'],  # character varying(20)
                self.VO_db_params['run_window'],  # integer
                datetime.strptime(self.VO_db_params['db_start_time'], '%Y-%m-%d %H:%M:%S'),  # timestamp without time zone
                datetime.strptime(self.VO_db_params['db_end_time'], '%Y-%m-%d %H:%M:%S'),  # timestamp without time zone
                datetime.strptime(self.VO_db_params['data_start_time'], '%Y-%m-%d %H:%M:%S'),  # timestamp without time zone
                datetime.strptime(self.VO_db_params['data_end_time'], '%Y-%m-%d %H:%M:%S'),  # timestamp without time zone
                self.VO_db_params['duration'],  # interval
                self.VO_db_params['telescope_mask'],  # integer
                self.VO_db_params['harvester_mask'],  # integer
                self.VO_db_params['source_id']  # character varying(255)
            )
            cursor.execute(insert_query, run_data)
            connection.commit()
            logger.log(logging.INFO, "VO DB parameters inserted successfully", extra=extra)
            self.read_last_run_id()
        except Exception as e:
            logger.log(logging.ERROR, f"Error inserting VO DB parameters: {e}", extra=extra)
            if connection:
                connection.rollback()
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
                logger.log(logging.INFO, "Database connection closed", extra=extra)

    def check_VO_db_params_filled(self, dictionary):
        for key, value in dictionary.items():
            if not value:
                return False
        return True

    def flag_VO_db_params_filled(self):
        for key in self.VO_db_params_filled:
            if self.VO_db_params[key] and self.VO_db_params[key] != 'null':
                self.VO_db_params_filled[key] = True


    def update_VO_db_params(self):
        self.VO_db_params['run_id'] = self.VO_db_params_runid_line.text()
        self.VO_db_params['veritas_run_id'] = self.VO_db_params_vrunid_line.text()
        self.VO_db_params['run_type'] = self.VO_db_params_run_type_line.text()
        self.VO_db_params['run_status'] = self.VO_db_params_run_status_line.text()
        self.VO_db_params['run_window'] = self.VO_db_params_run_window_line.text()
        self.VO_db_params['db_start_time'] = self.VO_db_params_db_start_time_line.text()
        self.VO_db_params['db_end_time'] = self.VO_db_params_db_end_time_line.text()
        self.VO_db_params['data_start_time'] = self.VO_db_params_data_start_time_line.text()
        self.VO_db_params['data_end_time'] = self.VO_db_params_data_end_time_line.text()
        self.VO_db_params['duration'] = self.VO_db_params_duration_line.text()
        self.VO_db_params['telescope_mask'] = self.VO_db_params_telescope_mask_line.text()
        self.VO_db_params['harvester_mask'] = self.VO_db_params_harvester_mask_line.text()
        self.VO_db_params['source_id'] = self.VO_db_params_sourceid_line.text()
        self.flag_VO_db_params_filled()
        if not self.firstFlip and self.check_VO_db_params_filled(self.get_VO_db_params_filled_short()):
            self.firstFlip = True
            self.StartButton.setEnabled(True)




    def dump_VO_db_params(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = "Current VO DB parameters:\n"
        for key, value in self.VO_db_params.items():
            print_string += f"{key}: {value} {self.VO_db_params_filled[key]}\n"
        logger.log(logging.INFO, print_string, extra=extra)

    def read_last_run_id(self):
        connection = None  # Initialize connection to None
        try:
            connection = psycopg.connect(
                dbname="telescope_db",
                user="vo_admin",
                password="lsttkc#$!",
                host="localhost",
                port="5432"
            )
            cursor = connection.cursor()
            cursor.execute("SELECT MAX(run_id) FROM tblrun_info;")
            last_run_id = cursor.fetchone()[0]
            if last_run_id is None:
                last_run_id = 0
            self.VO_db_params_runid_line.setText(str(last_run_id + 1))
        except Exception as e:
            print(f"Error reading last run ID: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()





    def start_server(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if not self.server_process:
            try:
                server_path = os.path.abspath("../server/bin/server")
                server_dir = os.path.dirname(server_path)
                self.server_process = subprocess.Popen([server_path], cwd=server_dir)

                self.heartbeatSendTimer = QtCore.QTimer()
                self.heartbeatSendTimer.timeout.connect(self.send_heartbeat)
                self.heartbeatSendTimer.start(1000)  # Send a heartbeat every 1 seconds

                self.heartbeatRecvTimer = QtCore.QTimer()
                self.heartbeatRecvTimer.timeout.connect(self.handle_heartbeat_timeout)
                self.heartbeatRecvTimer.start(3000)  # Check for a heartbeat every 5 seconds

                logger.log(logging.INFO, f"Server started successfully with PID: {self.server_process.pid}", extra=extra)
            except Exception as e:
                logger.log(logging.ERROR, f"Failed to start server: {e}", extra=extra)
        else:
            print_string = f"Server is already running at PID: {self.server_process.pid}"
            logger.log(logging.WARNING, print_string, extra=extra)

    def check_server_is_stopped(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.server_process:
            try:
                os.kill(self.server_process.pid, 0)
            except OSError or ProcessLookupError:
                logger.log(logging.INFO, f"Server process with PID {self.server_process.pid} has been terminated (OSError).", extra=extra)
                self.server_process = None
                self.VO_server_status_line.setStyleSheet("background-color: yellow; color: black;")
                self.VO_server_status_line.setText("Stopped")
            except Exception as e:
                logger.log(logging.ERROR, f"Failed to check server status: {e}", extra=extra)
                os.kill(self.server_process.pid, signal.SIGTERM)
            else:
                logger.log(logging.WARNING, f"Server process with PID {self.server_process.pid} is still running.", extra=extra)
                os.kill(self.server_process.pid, signal.SIGTERM)

    def stop_server(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.server_process:
            try:
                server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
                server_control_port = int(server_control_port)

                # Create the JSON object
                stop_message = json.dumps({"command": 3})
                datagram = stop_message.encode()

                self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port)

                self.heartbeatSendTimer.stop()
                self.heartbeatRecvTimer.stop()
                self.heartbeatSendTimer.timeout.disconnect(self.send_heartbeat)
                self.heartbeatRecvTimer.timeout.disconnect(self.handle_heartbeat_timeout)

                QtCore.QTimer.singleShot(1000, self.check_server_is_stopped)
                self.server_process.wait()

            except Exception as e:
                logger.log(logging.ERROR, f"Failed to stop server: {e}", extra=extra)
                QtWidgets.QMessageBox.critical(None, "Error", f"Failed to stop server: {e}")
        else:
            logger.log(logging.INFO, "Server is not running.", extra=extra)

    def establish_connections(self):

        gui_data_ip, gui_data_port = self.config_data["guiDataConnIP"].split(':')
        gui_heartbeat_ip, gui_heartbeat_port = self.config_data["guiHeartbeatConnIP"].split(':')
        gui_status_ip, gui_status_port = self.config_data["guiStatusConnIP"].split(':')

        self.listenSocket = QUdpSocket()
        self.listenSocket.bind(QHostAddress(gui_data_ip), int(gui_data_port))
        self.listenSocket.readyRead.connect(self.getDatagramAndQueue)

        self.VO_server_ip_line.setText(self.config_data["serverControlConnIP"])

        self.heartbeatSocket = QUdpSocket()
        self.heartbeatSocket.bind(QHostAddress(gui_heartbeat_ip), int(gui_heartbeat_port))
        self.heartbeatSocket.readyRead.connect(self.got_heartbeat)

        self.statusSocket = QUdpSocket()
        self.statusSocket.bind(QHostAddress(gui_status_ip), int(gui_status_port))
        self.statusSocket.readyRead.connect(self.got_status)

    def invert_dict(self, d):
        return {v: k for k, v in d.items()}

    def get_key_from_value(self, inverted_dictionary, value):
        return inverted_dictionary.get(value, None)

    def got_status(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        datagram = self.statusSocket.receiveDatagram(8000)
        status_code = struct.unpack('>I', datagram.data())[0]  # '>I' for big-endian unsigned int
        #print(self.config_data["status"])
        statuses = self.invert_dict(self.config_data["status"])
        status_key = self.get_key_from_value(statuses, status_code)

        logger.log(logging.INFO, f"Received status: {status_code}, corresponding to {status_key}", extra=extra)
        
        # Now you can compare status_code with the value in the JSON file

        #for key, value in self.config_data["status"].items():
        #    print(f"key: {key}, value: {value}, type: {type(value)}")
            
        #print('status_key:', status_key, type(status_key))
        #print('self.config_data["status"]["started"]:', self.config_data["status"]["started"])
        if status_code == self.config_data["status"]["started"]:
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_db_end_time_line.setText('null')
            self.VO_db_params_data_end_time_line.setText('null')
            self.VO_db_params_filled['db_end_time'] = False
            self.VO_db_params_filled['data_end_time'] = False
            self.set_gui_components_enabled(False)
        elif status_code == self.config_data["status"]["aborted"]:
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.set_gui_components_enabled(True)
        elif status_code == self.config_data["status"]["ended"]:
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.set_gui_components_enabled(True)
            self.write_VO_db_params_to_db()
        elif status_code == self.config_data["status"]["ended_manually"]:
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.set_gui_components_enabled(True)
            self.write_VO_db_params_to_db()
        else:
            logger.log(logging.WARNING, f"Received unknown status: {status_code}", extra=extra)

    def set_gui_components_enabled(self, enabled):
        if not enabled:
            # If disabling, check the state of self.state_edit
            if self.state_edit_check_was_checked:
                self.toggle_state_edit(False)  # Disable the state boxes
                self.state_edit_check_was_checked = True
            else:
                self.state_edit_check_was_checked = False
            self.state_edit_check.setEnabled(False)
            self.state_edit_undo_button.setEnabled(False)
            self.state_edit_set_button.setEnabled(False)

        else:
            # If enabling, check the previous state stored in self.state_edit_check_was_checked
            self.toggle_state_edit(self.state_edit_check_was_checked)  # Re-enable the state boxes
            self.state_edit_check.setEnabled(True)
            self.state_edit_undo_button.setEnabled(True)
            self.state_edit_set_button.setEnabled(True)

        # Enable or disable the other components
        self.obs_params_undo_button.setEnabled(enabled)
        self.obs_params_set_button.setEnabled(enabled)
        self.obs_params_save_path_line.setEnabled(enabled)
        self.obs_params_sourceid_line.setEnabled(enabled)
        self.obs_params_veritas_runid_spin.setEnabled(enabled)
        self.obs_params_veritas_runid_query_button.setEnabled(enabled)
        self.obs_params_run_type_combo.setEnabled(enabled)
        self.obs_params_duration_spin.setEnabled(enabled)
        self.veritas_sql_ping_button.setEnabled(enabled)
        self.fadc_gate_array_window_set_button.setEnabled(enabled)
        self.fadc_gate_array_window_combo.setEnabled(enabled)



    def got_heartbeat(self):
        datagram = self.heartbeatSocket.receiveDatagram(8000)
        # Process the received datagram
        #print(f"Received heartbeat: {datagram.data().decode()}")
        self.VO_server_status_line.setStyleSheet("background-color: green; color: white;")
        self.VO_server_status_line.setText("Connected")
        self.reset_heartbeat_timer()

    def reset_heartbeat_timer(self):
        self.heartbeatRecvTimer.stop()
        self.heartbeatRecvTimer.start(3000)  # Reset the timer with a 10-second interval

    def handle_heartbeat_timeout(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.VO_server_status_line.setStyleSheet("background-color: red; color: white;")
        self.VO_server_status_line.setText("Disconnected")
        logger.log(logging.WARNING, "Heartbeat timeout. VO server disconnected.", extra=extra)

    def send_heartbeat(self):
        server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
        server_control_port = int(server_control_port)

        # Create the JSON object
        heartbeat_message = json.dumps({"command": 7})
        datagram = heartbeat_message.encode()

        self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port)
        #print(f"Sent heartbeat to {server_heartbeat_ip}:{server_heartbeat_port} with message: {heartbeat_message}")

    def send_stop_message(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
        server_control_port = int(server_control_port)

        # Create the JSON object
        stop_message = json.dumps({"command": 8})
        datagram = stop_message.encode()

        self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port) 
        logger.log(logging.INFO, 'Run Stop requested.', extra=extra)  

    def load_config_file(self):
        try:
            with open(self.config_file, 'r') as file:
                self.config_data = json.load(file)
            self.obs_params_save_path_line.setText(self.config_data["dataSavePath"])
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "Error", f"Failed to load config file: {e}")
            logger.log(logging.ERROR, f"Failed to load config file: {e}")

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

            # Start the thread
            self.db_thread.start()
            self.startWorkerSignal.emit()
            self.db_worker_active = True
            logger.log(logging.INFO, "Started VERITAS SQL database thread.", extra=extra)

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
            self.db_thread.wait()

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


    def test(self):
        print("test")

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

    def clear_time_series_data(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        # Reset the time series data to zero
        self.pixelTimeSeriesData1 = np.zeros(1000)
        self.pixelTimeSeriesData2 = np.zeros(1000)
        self.pixelTimeSeriesData3 = np.zeros(1000)
        self.pixelTimeSeriesData4 = np.zeros(1000)
        self.pixelTimeSeriesDataCurve1.setData(self.pixelTimeSeriesData1)
        self.pixelTimeSeriesDataCurve2.setData(self.pixelTimeSeriesData2)
        self.pixelTimeSeriesDataCurve3.setData(self.pixelTimeSeriesData3)
        self.pixelTimeSeriesDataCurve4.setData(self.pixelTimeSeriesData4)
        self.ptr1 = -1000
        logger.log(logging.INFO, "Time series data cleared.", extra=extra)

    def requestStarField(self):
        self.star_field_request = True

    def calculate_telescope_mask(self):
        mask = 0
        for i in range(4):
            telescope = self.state_data['telescopes'][i]
            mask |= telescope['missing'] << i
        return mask
    
    def calculate_harvester_mask(self):
        mask = 0
        for i in range(4):
            telescope = self.state_data['telescopes'][i]
            for j in range(8):
                harvester = telescope['harvesters'][j]
                mask |= harvester['missing'] << (i*8+j)
        return mask


    def load_state_file(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load State File", "", "JSON Files (*.json);;All Files (*)")
        if file_name:
            with open(file_name, 'r') as file:
                self.state_data = json.load(file)
                self.state_data_temp = self.state_data.copy()
                self.update_widgets_from_state()
                self.connect_signals_to_mark_modified()
            self.state_edit_set_button.setEnabled(True)
            self.state_edit_undo_button.setEnabled(True)
            self.state_edit_check.setEnabled(True)
            self.VO_db_params_telescope_mask_line.setText(bin(self.calculate_telescope_mask()))
            self.VO_db_params_harvester_mask_line.setText(hex(self.calculate_harvester_mask()))


    def undo_changes(self):
        self.update_widgets_from_state()
        self.restore_original_colors()

    def set_changes(self):
        for i in range(4):  # Assuming there are 4 telescopes
            telescope = self.state_data['telescopes'][i]
            telescope['missing'] = getattr(self, f't{i+1}_state_telescope_missing_check').isChecked()
            
            for j in range(8):  # Assuming there are 8 harvesters per telescope
                harvester = telescope['harvesters'][j]
                harvester['arrayPosition'] = getattr(self, f't{i+1}_state_array_position_spin_{j+1}').value()
                harvester['localPosition'] = getattr(self, f't{i+1}_state_local_position_spin_{j+1}').value()
                harvester['missing'] = getattr(self, f't{i+1}_state_harvester_missing_check_{j+1}').isChecked()
                harvester['ip'] = getattr(self, f't{i+1}_state_ip_line_{j+1}').text()
                harvester['channel'][0] = getattr(self, f't{i+1}_state_channel_start_spin_{j+1}').value()
                harvester['channel'][1] = getattr(self, f't{i+1}_state_channel_end_spin_{j+1}').value()
                harvester['pixelIndex'][0] = getattr(self, f't{i+1}_state_pixel_index_start_spin_{j+1}').value()
                harvester['pixelIndex'][1] = getattr(self, f't{i+1}_state_pixel_index_end_spin_{j+1}').value()
        
        self.restore_original_colors()
        self.connect_signals_to_mark_modified()  # Reconnect signals to update original values
        self.VO_db_params_telescope_mask_line.setText(bin(self.calculate_telescope_mask()))
        self.VO_db_params_harvester_mask_line.setText(hex(self.calculate_harvester_mask()))
                
    def update_widgets_from_state(self):
        for i in range(4):  # Assuming there are 4 telescopes
            telescope = self.state_data['telescopes'][i]
            getattr(self, f't{i+1}_state_telescope_missing_check').setChecked(telescope['missing'])
            
            for j in range(8):  # Assuming there are 8 harvesters per telescope
                harvester = telescope['harvesters'][j]
                getattr(self, f't{i+1}_state_array_position_spin_{j+1}').setValue(harvester['arrayPosition'])
                getattr(self, f't{i+1}_state_local_position_spin_{j+1}').setValue(harvester['localPosition'])
                getattr(self, f't{i+1}_state_harvester_missing_check_{j+1}').setChecked(harvester['missing'])
                getattr(self, f't{i+1}_state_ip_line_{j+1}').setText(harvester['ip'])
                getattr(self, f't{i+1}_state_channel_start_spin_{j+1}').setValue(harvester['channel'][0])
                getattr(self, f't{i+1}_state_channel_end_spin_{j+1}').setValue(harvester['channel'][1])
                getattr(self, f't{i+1}_state_pixel_index_start_spin_{j+1}').setValue(harvester['pixelIndex'][0])
                getattr(self, f't{i+1}_state_pixel_index_end_spin_{j+1}').setValue(harvester['pixelIndex'][1])

    def toggle_state_edit(self, checked):
        for i in range(1, 5):  # Assuming there are 4 telescopes
            getattr(self, f't{i}_state_telescope_missing_check').setEnabled(checked)
            
            for j in range(1, 9):  # Assuming there are 7 harvesters per telescope
                getattr(self, f't{i}_state_array_position_spin_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_local_position_spin_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_harvester_missing_check_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_ip_line_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_channel_start_spin_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_channel_end_spin_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_pixel_index_start_spin_{j}').setEnabled(checked)
                getattr(self, f't{i}_state_pixel_index_end_spin_{j}').setEnabled(checked)
        self.state_edit_check_was_checked = checked

    def mark_widget_as_modified(self, widget, original_value):
        current_value = None
        
        if isinstance(widget, QtWidgets.QCheckBox):
            current_value = widget.isChecked()
        elif isinstance(widget, QtWidgets.QLineEdit):
            current_value = widget.text()
        elif isinstance(widget, QtWidgets.QSpinBox):
            current_value = widget.value()
        
        if current_value == original_value:
            if widget in self.original_styles:
                widget.setStyleSheet(self.original_styles[widget])
        else:
            if not hasattr(self, 'original_styles'):
                self.original_styles = {}
            
            if widget not in self.original_styles:
                self.original_styles[widget] = widget.styleSheet()
            
            widget.setStyleSheet("background-color: yellow;")
    
    def restore_original_colors(self):
        if hasattr(self, 'original_styles'):
            for widget, style in self.original_styles.items():
                widget.setStyleSheet(style)
            self.original_styles.clear()

    def connect_signals_to_mark_modified(self):
        for i in range(1, 5):  # Assuming there are 4 telescopes
            widget = getattr(self, f't{i}_state_telescope_missing_check')
            original_value = self.state_data['telescopes'][i-1]['missing']
            widget.stateChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
            
            for j in range(1, 9):  # Assuming there are 8 harvesters per telescope
                widget = getattr(self, f't{i}_state_array_position_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['arrayPosition']
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_local_position_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['localPosition']
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_harvester_missing_check_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['missing']
                widget.stateChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_ip_line_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['ip']
                widget.textChanged.connect(lambda text, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_channel_start_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['channel'][0]
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_channel_end_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['channel'][1]
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_pixel_index_start_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['pixelIndex'][0]
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))
                
                widget = getattr(self, f't{i}_state_pixel_index_end_spin_{j}')
                original_value = self.state_data['telescopes'][i-1]['harvesters'][j-1]['pixelIndex'][1]
                widget.valueChanged.connect(lambda value, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

    def obs_connect_signals_to_mark_modified(self):
        widget = getattr(self, f'obs_params_save_path_line')
        original_value = self.obs_params['SavePath']
        widget.textChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

        widget = getattr(self, f'obs_params_sourceid_line')
        original_value = self.obs_params['SourceID']
        widget.textChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

        widget = getattr(self, f'obs_params_veritas_runid_spin')
        original_value = self.obs_params['VERITASRunNumber']
        widget.valueChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

        widget = getattr(self, f'obs_params_run_type_combo')
        original_value = self.obs_params['RunType']
        widget.currentTextChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

        widget = getattr(self, f'obs_params_duration_spin')
        original_value = self.obs_params['RunDuration']
        widget.valueChanged.connect(lambda state, w=widget, v=original_value: self.mark_widget_as_modified(w, v))

    def obs_undo_changes(self):
        self.obs_update_widgets_from_state()
        self.restore_original_colors()

    def obs_update_widgets_from_state(self):

        getattr(self, f'obs_params_save_path_line').setText(self.obs_params['SavePath'])
        getattr(self, f'obs_params_sourceid_line').setText(self.obs_params['SourceID'])
        getattr(self, f'obs_params_veritas_runid_spin').setValue(self.obs_params['VERITASRunNumber'])
        getattr(self, f'obs_params_run_type_combo').setCurrentText(self.obs_params['RunType'])
        getattr(self, f'obs_params_duration_spin').setValue(self.obs_params['RunDuration'])

    def obs_set_changes(self):

        self.obs_params['SavePath'] = getattr(self, f'obs_params_save_path_line').text()
        self.obs_params['SourceID'] = getattr(self, f'obs_params_sourceid_line').text()
        self.obs_params['VERITASRunNumber'] = getattr(self, f'obs_params_veritas_runid_spin').value()
        self.obs_params['RunType'] = getattr(self, f'obs_params_run_type_combo').currentText()
        self.obs_params['RunDuration'] = getattr(self, f'obs_params_duration_spin').value()

        self.VO_db_params_sourceid_line.setText(self.obs_params['SourceID'])
        self.VO_db_params_vrunid_line.setText(str(self.obs_params['VERITASRunNumber']))
        self.VO_db_params_run_type_line.setText(self.obs_params['RunType'])
        self.VO_db_params_duration_line.setText(str(self.obs_params['RunDuration']))
        
        self.restore_original_colors()
        self.obs_connect_signals_to_mark_modified()  # Reconnect signals to update original values


    def stopWorker(self):
        if self.db_worker_active:
            self.stopWorkerSignal.emit()
            self.db_thread.quit()
            self.db_thread.wait()

    def closeEvent(self, event):
        self.stopWorker()
        self.stop_server() # Make a purpose-built function to stop the server
        event.accept()

    def handle_VPM_data(self, vpm):

        # Handle the new data fetched from the database
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = '\n'
        for key, value in vpm.items():
            print_string += f"Telescope {key} - Elevation: {value['elevation_raw']}, Azimuth: {value['azimuth_raw']}\n"
        #logger.log(logging.INFO, print_string, extra=extra)

    def handle_star_field_data(self, star_positions):

        # Handle the new data fetched from the database
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = '\n'
        for i, telescope in enumerate(star_positions):
            print_string += f"Telescope {i+1} - Stars in FOV: {len(telescope)}\n"
            for star in telescope:
                print_string += f"Star: {star}\n"
        logger.log(logging.INFO, print_string, extra=extra)



    def draw_star_field(self, star_field_data):
        #print("self.star_field", self.star_field)
        #print("star_positions", array_star_positions)
        array_star_positions = star_field_data['offsets']
        array_star_labels = star_field_data['labels']
        #print(self.star_field_labels)
        for i in range(4):
            if self.star_field[i] is not None:
                self.ws[i].removeItem(self.star_field[i])
            if self.star_field_labels[i] is not None:
                for text_item in self.star_field_labels[i]:
                    self.ws[i].removeItem(text_item)
        self.star_field = [None, None, None, None]
        self.star_field_labels = [None, None, None, None]
        border_pen = pg.mkPen(color='k', width=1)  # Black border with width 1
        for i, star_positions in enumerate(array_star_positions):
            if len(star_positions) > 0:
                xs, ys = list(zip(*star_positions))
                #print("telescope", i)
                #print("xys", xs, ys)
                scatter_plot = pg.ScatterPlotItem(
                    x=xs,
                    y=ys,
                    brush=pg.mkColor('r'),
                    size=20,
                    pen=border_pen,
                    hoverSize=25,
                    symbol='star',
                    pxMode=True,  # Set pxMode=False to allow spots to transform with the view
                    hoverable=True,
                    useCache=True,
                    antialias=False,
                    data=array_star_labels[i]
                )
                self.star_field[i] = scatter_plot
                self.ws[i].addItem(scatter_plot)
                font = QtGui.QFont()
                font.setPointSize(8)  # Set the font size to 12
                font.setBold(True)
                for j, point in enumerate(scatter_plot.points()):
                    x, y = point.pos()
                    text_item = pg.TextItem(text=array_star_labels[i][j], anchor=(0, 0.75))
                    text_item.setParentItem(scatter_plot)
                    text_item.setPos(x, y)
                    text_item.setFont(font)
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
                    offset = (f"{array_star_positions[i][j][0]:.3f}", f"{array_star_positions[i][j][1]:.3f}")
                    print_string += f"Star {j+1}: {star}\n"
                    print_string += f"Offset: {offset}\n"
                    print_string += f"-----------------------------------\n"
            logger.log(logging.INFO, print_string, extra=extra)
            self.star_field_request = False
        return


    def getDatagramAndQueue(self):
        datagram = self.listenSocket.receiveDatagram(8000)
        pixelData = np.frombuffer(datagram.data(), dtype=np.float32)
        self.pixelData = pixelData
        #print(self.pixelData)
        self.update()

    def updateLog(self, status, record):
        color = self.COLORS.get(record.levelno, 'black')
        s = '<pre><font color="%s">%s</font></pre>' % (color, status)
        self.log_edit.appendHtml(s)
        
    def update(self):
        #self.pixelData = self.listenOutQueue.get()
       # print(self.pixelData)
        
        #self.pixelData = np.random.randint(0, 63508, size=2000)
        self.brushes1 = self.colors2[np.searchsorted(self.valueRange, self.pixelData[:499])]
        self.brushes2 = self.colors2[np.searchsorted(self.valueRange, self.pixelData[500:999])]
        self.brushes3 = self.colors2[np.searchsorted(self.valueRange, self.pixelData[1000:1499])]
        self.brushes4 = self.colors2[np.searchsorted(self.valueRange, self.pixelData[1500:1999])]
    
        self.s1.setBrush(self.brushes1) # Is there a faster way to do this?
        self.s2.setBrush(self.brushes2)
        self.s3.setBrush(self.brushes3)
        self.s4.setBrush(self.brushes4)

        #print(help(self.s1.points()[0]))

        # Update data attribute of each point
        #for i, point in enumerate(self.s1.points()):
        #   point.setData(self.pixelData[i])
        #for i, point in enumerate(self.s2.points()):
        #    point.data = self.pixelData[500 + i]
        #for i, point in enumerate(self.s3.points()):
        #    point.data = self.pixelData[1000 + i]
        #for i, point in enumerate(self.s4.points()):
        #    point.data = self.pixelData[1500 + i]

        #self.s1.data = self.pixelData[:499]

        self.pixelTimeSeriesData1 = np.roll(self.pixelTimeSeriesData1, -1)
        self.pixelTimeSeriesData2 = np.roll(self.pixelTimeSeriesData2, -1)
        self.pixelTimeSeriesData3 = np.roll(self.pixelTimeSeriesData3, -1)
        self.pixelTimeSeriesData4 = np.roll(self.pixelTimeSeriesData4, -1)
        
        if len(self.selected) != 0:
            self.pixelTimeSeriesData1[-1] = np.average(self.pixelData[:499][self.selected])
            self.pixelTimeSeriesData2[-1] = np.average(self.pixelData[500:999][self.selected])
            self.pixelTimeSeriesData3[-1] = np.average(self.pixelData[1000:1499][self.selected])
            self.pixelTimeSeriesData4[-1] = np.average(self.pixelData[1500:1999][self.selected])
        else:
            self.pixelTimeSeriesData1[-1] = 0
            self.pixelTimeSeriesData2[-1] = 0
            self.pixelTimeSeriesData3[-1] = 0
            self.pixelTimeSeriesData4[-1] = 0

        self.pixelTimeSeriesDataCurve1.setData(self.pixelTimeSeriesData1)
        self.pixelTimeSeriesDataCurve1.setPos(self.ptr1, 0)
        self.pixelTimeSeriesDataCurve2.setData(self.pixelTimeSeriesData2)
        self.pixelTimeSeriesDataCurve2.setPos(self.ptr1, 0)
        self.pixelTimeSeriesDataCurve3.setData(self.pixelTimeSeriesData3)
        self.pixelTimeSeriesDataCurve3.setPos(self.ptr1, 0)
        self.pixelTimeSeriesDataCurve4.setData(self.pixelTimeSeriesData4)
        self.pixelTimeSeriesDataCurve4.setPos(self.ptr1, 0)
        self.ptr1 += 1
        
        self.now = perf_counter()
        self.dt = self.now - self.lastTime
        self.lastTime = self.now
        if self.fps is None:
            self.fps = 1.0 / self.dt
        else:
            self.s = np.clip(self.dt * 3., 0, 1)
            self.fps = self.fps * (1 - self.s) + (1.0 / self.dt) * self.s
    
        self.setWindowTitle('%0.2f fps' % self.fps)


        
    def startRun(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        logger.log(logging.INFO, 'Run started.', extra=extra)

    def stopRun(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        logger.log(logging.INFO, 'Run Stop requested.', extra=extra)       
        
    def updateROI(self, roi):
        
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        roiPos = roi.pos()
        roiSize = roi.size()
        for thisROI in self.rois:
            if thisROI is not roi:
                thisROI.setPos(roiPos)
                thisROI.setSize(roiSize)
                
        #print(extra)
        self.roiShape = roi.mapToItem(self.s1, roi.shape())
        # Get list of all points inside shape
        self.selectedHold = np.array([i for i, pt in enumerate(self.points) if self.roiShape.contains(QtCore.QPointF(pt[0], pt[1]))])
        if np.array_equal(self.selectedHold, self.selected) is False:
            self.data_display_pmt_line.setText(",".join(np.char.mod('%d', self.selectedHold)))
            logger.log(logging.DEBUG, 'New PMTs selected: ' + ",".join(np.char.mod('%d', self.selectedHold)), extra=extra)
            self.selected = self.selectedHold

    def onMouseMoved(self, point):
        p = self.w1.mapSceneToView(point)
        #print("{}   {}".format(p.x(), p.y()))        
        
    def createCameraPixelArray(self, w):
        s = pg.ScatterPlotItem(
               pxMode=True,  # Set pxMode=False to allow spots to transform with the view
               hoverable=True,
               brush=pg.mkColor('b'),
               hoverPen=pg.mkPen('g'),
               hoverSize=self.hexSize,
               useCache=True,
               antialias=False
        )
        spots = []
        file = 'trueLocations_VERITAS.dat'
        
        with open(file, 'r') as f:
            lines = [x for x in f]
            
        xs = np.array([le(x.split()[0]) for x in lines])#*1e6
        ys = np.array([le(y.split()[1]) for y in lines])#*1e6
        labels = np.array([le(label.split()[2]) for label in lines])
        #xs, ys, labels = drawHexGridLoop2((0, 0), 14, 1e-6, 0)
        #xs, ys, labels = drawHexGridLoop2((0, 0), 14, 5, 0)
    
        for i, thing in enumerate(xs):
            spots.append({'pos': (xs[i], ys[i]), 'size': self.hexSize, 'brush':pg.intColor(10, 10), 'symbol':'h', 'data':'Pixel ' + str(labels[i])})
        s.addPoints(spots)
        w.addItem(s)
    #, 'pen': {'color': 'w', 'width': 0.1}
        return w, s, spots, xs, ys, labels

def load_stylesheet(app, qss_file):
    with open(qss_file, "r") as file:
        app.setStyleSheet(file.read())

if __name__ == "__main__":
        
    QtCore.QThread.currentThread().setObjectName('MainThread')
    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    load_stylesheet(app, "Genetive.qss")
    window.show()
    sys.exit(app.exec())