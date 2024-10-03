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



fs = '[%(asctime)s %(levelname)s] %(message)s'
formatter = logging.Formatter(fs)
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
    query_timeout_signal = QtCore.pyqtSignal()
    query_run_number_signal = QtCore.pyqtSignal(int)
    query_timeout_signal = QtCore.pyqtSignal()
    query_ok_signal = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.vpm_timer = QtCore.QTimer()
        self.vpm_timer.timeout.connect(self.get_stars_in_fov)
        self.running = False
        self.basecamp = EarthLocation(lat=31.6716989799*u.deg, lon=-110.951291195*u.deg, height=1268*u.m)
        self.observer = apl.Observer(location=self.basecamp, name="VERITAS")
        with open('/home/zdhughes/VERITAS_optical/data/asu2.dat', 'r') as f:
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
        self.process = None

        self.start_querying_VPM_signal.connect(self.start_querying)
        self.stop_querying_VPM_signal.connect(self.stop_querying)

    def start_querying(self):
        if self.process is not None:
            self.stop_querying()
        self.process = Process(target=query_last_pointing, args=(self.queue, self.db_config))
        self.process.start()
        self.vpm_timer.start(int(self.queue_check_interval*1000))  # Check the queue every 2.5 seconds

    def stop_querying(self):
        if self.process is not None:
            self.process.terminate()
            self.process.join()
            self.process = None
        self.vpm_timer.stop()

    def get_stars_in_fov(self):
        if not self.queue.empty():
            vpm = self.queue.get()
            self.VPM_fetched_signal.emit(vpm)
            self.calculate_star_offsets(vpm)
            self.query_ok_signal.emit()
            self.queue_check_counter = 0
        else:
            self.queue_check_counter += 1
            if self.queue_check_counter >= self.maximum_queue_checks:
                self.query_timeout_signal.emit()

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



class Window(QtWidgets.QMainWindow, Ui_MainWindow):

    startWorkerSignal = QtCore.pyqtSignal()
    stopWorkerSignal = QtCore.pyqtSignal()
    
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

        self.logEmitter = LogSignalEmitter()
        self.logHandler = QLogHandler(self.logEmitter, self.updateLog)
        self.logHandler.setFormatter(formatter)
        logger.addHandler(self.logHandler)
        self.logHandler.setLevel('INFO')

        self.actionExit.triggered.connect(self.close)

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
        self.ptr1 = 0
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


        self.roi1.sigRegionChanged.connect(self.updateROI)
        
        self.updateROI(self.roi1)
        
        self.StartButton.clicked.connect(self.startRun)
        self.StopButton.clicked.connect(self.stopRun)
        self.s1.scene().sigMouseMoved.connect(self.onMouseMoved)


        self.listenSocket = QUdpSocket()
        self.listenSocket.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        self.listenSocket.readyRead.connect(self.getDatagramAndQueue)




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



        # Start the thread
        self.db_thread.start()
        self.startWorkerSignal.emit()


    def stopWorker(self):
        self.stopWorkerSignal.emit()
        self.db_thread.quit()
        self.db_thread.wait()

    def closeEvent(self, event):
        self.stopWorker()
        event.accept()

    def handle_VPM_data(self, vpm):

        # Handle the new data fetched from the database
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = '\n'
        for key, value in vpm.items():
            print_string += f"Telescope {key} - Elevation: {value['elevation_raw']}, Azimuth: {value['azimuth_raw']}\n"
        logger.log(logging.INFO, print_string, extra=extra)

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
        self.LogBox.appendHtml(s)
        
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
        logger.log(logging.INFO, 'Run Stopped.', extra=extra)        
        
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
    #load_stylesheet(app, "Genetive.qss")
    window.show()
    sys.exit(app.exec())