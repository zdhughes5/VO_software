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

from start2 import Ui_MainWindow
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from time import perf_counter
from pyqtgraph.Qt.QtGui import QBrush, QColor
from ast import literal_eval as  le
#import PyQt5.sip as sip
from PyQt6.QtNetwork import QHostAddress, QUdpSocket
import sys
from time import sleep
import ctypes
import os 
import logging
from functools import cached_property
import zmq
import pickle
import uuid
#import msgpack
#import msgpack_numpy as m
from string import ascii_lowercase as alc
from string import ascii_uppercase as auc
import matplotlib.pyplot as plt
from scipy import spatial
import queue



fs = '[%(asctime)s %(levelname)s] %(message)s'
formatter = logging.Formatter(fs)
logging.basicConfig(format='[%(asctime)s line %(lineno)d %(qThreadName)s %(levelname)s] %(message)s', handlers=[logging.FileHandler("debug.log", mode="w")])
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ENDPOINT = "ipc://routing.ipc"
ENDPOINT = "tcp://localhost:5555"
ENDPOINT2 = "tcp://localhost:5556"


n = 0
m = 0

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


class ListenSocket(QUdpSocket):
    updateGUISignal = QtCore.pyqtSignal()
        
    def __init__(self, inQueue, outQueue):
        super().__init__()
        self.inQueue = inQueue
        self.outQueue = outQueue

    def setupThread(self):
        self.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        self.readyRead.connect(self.getDatagramAndQueue)
        #self.readyRead.connect(self.readPendingDatagrams)

    def getDatagramAndQueue(self):
        datagram = self.receiveDatagram(65507)
        pixelData = np.frombuffer(datagram.data(), dtype=np.float32)
        self.pixelData = pixelData
        self.updateGUISignal.emit()

    def readPendingDatagrams(self):
        #print("Reading pending datagrams")
        newestPixelBytes = None
        while self.hasPendingDatagrams():
            datagram = self.receiveDatagram()
            newestPixelBytes = datagram.data()
        if newestPixelBytes:
            self.handlePixelData(newestPixelBytes)

    def handlePixelData(self, pixelBytes):
        # Convert newestData to a 2000-element float32 NumPy array
        pixelData = np.frombuffer(pixelBytes, dtype=np.float32)
        self.outQueue.put(pixelData)
        self.updateGUISignal.emit()



class Window(QtWidgets.QMainWindow, Ui_MainWindow):
    
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

        self.starPos = [(0,0)]
        self.starScatters = None
        self.weights = np.zeros(499)
        self.hexSize = 14.0
        self.cameraView.ci.setBorder((50, 50, 100))
        self.w1 = self.cameraView.addViewBox(enableMouse=False)
        self.w2 = self.cameraView.addViewBox(enableMouse=False)
        self.cameraView.nextRow()
        self.w3 = self.cameraView.addViewBox(enableMouse=False)
        self.w4 = self.cameraView.addViewBox(enableMouse=False)
        self.cameraView.nextRow()
        self.w5 = self.cameraView.addPlot(colspan=2)
        self.ws = [self.w1, self.w2, self.w3, self.w4, self.w5]

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
        self.colormap = pg.colormap.get('CET-L6')
        self.valueRange = np.linspace(0, 66000, num=self.nPts)
        #self.valueRange = np.linspace(0, 255, num=self.nPts)
        self.colors = self.colormap.getLookupTable(0, 1, nPts=self.nPts+1)
        self.colors2 = np.array([QBrush(QColor(*i)) for i in self.colors])
        print(self.colors2)
        print(self.valueRange)
        
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

        self.roi1 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=(40,90))
        self.roi2 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=(40,90))
        self.roi3 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=(40,90))
        self.roi4 = pg.CircleROI([-0.25, -0.25], [0.5, 0.5], pen=(40,90))
        self.rois = [self.roi1, self.roi2, self.roi3, self.roi4]
        self.w1.addItem(self.roi1)
        self.w2.addItem(self.roi2)
        self.w3.addItem(self.roi3)
        self.w4.addItem(self.roi4)
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

        # listenIP = QHostAddress("127.0.0.1:31255")
        # self.listenInQueue = queue.Queue()
        # self.listenOutQueue = queue.Queue()
        # self.listenSocket = ListenSocket(self.listenInQueue, self.listenOutQueue)
        # self.listenSocket.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        # self.listenThread = QtCore.QThread()
        # self.listenSocket.moveToThread(self.listenThread)
        # self.listenSocket.readyRead.connect(self.listenSocket.getDatagramAndQueue)
        # self.listenSocket.updateGUISignal.connect(self.update)
        # self.listenThread.start()

        self.listenSocket = QUdpSocket()
        self.listenSocket.bind(QHostAddress.SpecialAddress.LocalHost, 31255)
        self.listenSocket.readyRead.connect(self.getDatagramAndQueue)

        #self.timer = QtCore.QTimer()
        #self.timer.timeout.connect(self.update)
        #self.timer.start(0)

        #self.update()

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
            self.PMTLine.setText(",".join(np.char.mod('%d', self.selectedHold)))
            logger.log(logging.DEBUG, 'New PMTs selected: ' + ",".join(np.char.mod('%d', self.selectedHold)), extra=extra)
            self.selected = self.selectedHold

    def onMouseMoved(self, point):
        p = self.w1.mapSceneToView(point)
        #print("{}   {}".format(p.x(), p.y()))        
        
    def createCameraPixelArray(self, w):
        s = pg.ScatterPlotItem(
               pxMode=True,  # Set pxMode=False to allow spots to transform with the view
               hoverable=True,
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
            spots.append({'pos': (xs[i], ys[i]), 'size': self.hexSize, 'brush':pg.intColor(10, 10), 'symbol':'h'})
        s.addPoints(spots)
        w.addItem(s)
    #, 'pen': {'color': 'w', 'width': 0.1}
        return w, s, spots, xs, ys, labels

        
QtCore.QThread.currentThread().setObjectName('MainThread')
app = QtWidgets.QApplication(sys.argv)
window = Window()
window.show()
sys.exit(app.exec())