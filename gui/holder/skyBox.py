#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec 13 20:47:29 2022

@author: zdhughes
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 21 18:55:11 2022

@author: zdhughes
"""
import warnings
from skyUI import Ui_MainWindow
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
from time import perf_counter
from pyqtgraph.Qt.QtGui import QBrush, QColor
from ast import literal_eval as  le
import sys
from time import sleep
import ctypes
import os 
import logging
from functools import cached_property
import zmq
import pickle
import uuid
import msgpack
import msgpack_numpy as m
from string import ascii_lowercase as alc
from string import ascii_uppercase as auc
import astroplan as apl
import astropy as apy
from astropy import units as u
import datetime
import pickle
from time import time

VERITAS_lon = -110.951291195
VERITAS_lat = 31.6716989799
VERITAS_alt = 1268
starFileNamed ='/home/zdhughes/VERITAS_optical/data/bsc.dat'
starFile ='/home/zdhughes/VERITAS_optical/data/asu2.dat'

ENDPOINT = "ipc://routing.ipc"
ENDPOINT = "tcp://*:5555"
ENDPOINT2 = "tcp://*:5556"

def timer_func(func):
    # This function shows the execution time of 
    # the function object passed
    def wrap_func(*args, **kwargs):
        t1 = time()
        result = func(*args, **kwargs)
        t2 = time()
        print(f'Function {func.__name__!r} executed in {(t2-t1):.4f}s')
        return result
    return wrap_func

class Worker():
    
    def __init__(self):
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(ENDPOINT2)
        




class Window(QtWidgets.QMainWindow, Ui_MainWindow):
    

    def sendPos(self):
        print('Sending Pos.')
        print(self.posToSend)
        self.worker.socket.send_pyobj(self.posToSend)
        
    def __init__(self):
        #Execute the QMainWindow __init__. 
        #QMainWindow is a QWidget; a widget without a parent is a window.
        super().__init__()

        self.posToSend = [(0,0)]
        self.worker = Worker()
# =============================================================================
#         self.posClock = QtCore.QTimer()
#         self.posClock.timeout.connect(self.sendPos)
#         self.posClock.start(1000)
# =============================================================================
        
        #Draw all the stuff from the UI file.
        self.setupUi(self)
        self.basecampLocation = apy.coordinates.EarthLocation.from_geodetic(VERITAS_lon, VERITAS_lat, height=VERITAS_alt)
        self.observer = apl.Observer(location=self.basecampLocation, name="VERITAS")
        
        self.timeOffsetText = '0'
        self.ANGLE_OFFSET = None # The time offset turned into degrees.
        self.TIME_OFFSET = None
        self.TimeEdit.setText(self.timeOffsetText)
        self.setTimeOffset()
        self.TimeButton.clicked.connect(self.setTimeOffset)
        
        self.realTime = None # This is a time
        self.offsetTime = None # This is a time
        self.realLST = None # This is an angle in hms
        self.offsetLST = None # This is an angle in hms
        self.realZenith = None # RA Dec in deg.
        self.offsetZenith = None # RA Dec in deg.
        self.updateTimeDependencies()
        
        self.currentPointing = self.offsetZenith
        self.desiredPointing = self.currentPointing
        self.lastPointing = self.currentPointing
        self.startingPointing = self.currentPointing
        
        self.stars = None
        self.star_names = None
        self.star_RA_deg = None
        self.star_DEC_deg = None
        self.star_V_mags = None
        self.starLocations = None
        self.starFile = starFile
        self.loadStars()

        self.n = 0

        
        self.widget.canvas.setupProperties(self.basecampLocation, self.offsetLST, self.stars, self.offsetZenith)
        self.TestScatter.canvas.setupProperties(self.basecampLocation, 'Az.', 'Alt.')
        self.TestScatter_2.canvas.setupProperties(self.basecampLocation, 'R.A.', 'Dec.')
        self.TestScatter_3.canvas.setupProperties(self.basecampLocation, 'Az.', 'Alt.')

        
        self.skyClock = QtCore.QTimer()
        self.skyClock.timeout.connect(self.updatePlot)
        #self.skyClock.start(60000)
        self.slewClock = QtCore.QTimer()
        self.slewClock.timeout.connect(self.setInstantPointingAndDraw)
        
        self.FFClock = QtCore.QTimer()
        self.FFClock.timeout.connect(self.forward4Min)
        self.FFButton.clicked.connect(self.StartFF)
        self.StopFFButton.clicked.connect(self.StopFF)

        
        self.StarBox.currentIndexChanged.connect(self.newStarSelected)
        self.ForwardButton.clicked.connect(self.forward1Hour)
        self.BackButton.clicked.connect(self.back1Hour)
        self.ForwardMButton.clicked.connect(self.forward4Min)
        self.BackMButton.clicked.connect(self.back4Min)
        self.SlewButton.clicked.connect(self.startSlew)
        self.StopButton.clicked.connect(self.stopSlew)

    #@timer_func
    def loadStars(self):
        with open(self.starFile, 'r') as f:
            lines = [x for x in f]
        
        self.star_names = np.array([x.split()[0] for x in lines])
        self.star_RA_deg = np.array([le(x.split()[1]) for x in lines])
        self.star_DEC_deg = np.array([le(x.split()[2]) for x in lines])
        self.star_V_mags = np.array([le(x.split()[3]) for x in lines])
        self.starLocations = apy.coordinates.SkyCoord(ra=self.star_RA_deg, dec=self.star_DEC_deg, unit="deg")

        self.stars = (self.star_names, self.starLocations, self.star_V_mags)
        self.StarBox.addItems(self.star_names)
        
    #@timer_func
    def newStarSelected(self, i):
        self.selectedStar = i # initialize this in init, actually check all vars.
        self.desiredPointing = self.stars[1][i]
        self.widget.canvas.setDesiredPointing(self.desiredPointing)
        self.startingPointing = self.currentPointing
        self.widget.canvas.setStartingPointing(self.startingPointing)
        self.updatePlot()
        self.printPointings()

    
    #@timer_func
    def updateTimeDependencies(self):
        self.realTime = apy.time.Time(datetime.datetime.utcnow(), scale='utc', location=self.basecampLocation) # This is a time
        self.offsetTime = self.realTime + self.TIME_OFFSET  # This is a time
        self.realLST = self.realTime.sidereal_time('mean')  # This is an angle in hms
        self.offsetLST = self.offsetTime.sidereal_time('mean') # This is an angle in hms
        self.realZenith = apy.coordinates.SkyCoord(self.realLST.deg, VERITAS_lat, unit="deg")
        self.offsetZenith = apy.coordinates.SkyCoord(self.offsetLST.deg, VERITAS_lat, unit="deg")

    #@timer_func
    def printTimeDependencies(self):
        print('---------------')
        print('Time Dependencies:')
        print('\nrealTime')
        print(self.realTime)
        print('\noffsetTime')
        print(self.offsetTime)
        print('\nrealLST')
        print(self.realLST)
        print('\noffsetLST')
        print(self.offsetLST)
        print('\nrealZenith')
        print(self.realZenith)
        print('\noffsetZenith')
        print(self.offsetZenith)
        print('---------------')
        
    def printPointings(self):
        
        print('---------------')
        print('Current Pointing:')
        print(self.currentPointing)
        print('Desired Pointing:')
        print(self.desiredPointing)
        print('Last Pointing:')
        print(self.lastPointing)
        print('Starting Pointing:')
        print(self.startingPointing)
        print('---------------')

    #@timer_func
    def updatePlot(self):
        self.updateTimeDependencies()
        self.widget.canvas.updateLST(self.offsetLST)
        self.widget.canvas.updateCelestialSphere()
        #test = self.getStarsInsideAltAz(self.currentPointing)
        self.getStarsInsideAltAz(self.currentPointing)
        
    def forward1Hour(self):
        self.timeOffsetText = str(le(self.timeOffsetText) + 3600)
        self.TimeEdit.setText(self.timeOffsetText)
        self.setTimeOffset()
        
    def back1Hour(self):
        self.timeOffsetText = str(le(self.timeOffsetText) - 3600)
        self.TimeEdit.setText(self.timeOffsetText)
        self.setTimeOffset()
        
    def forward4Min(self):
        self.timeOffsetText = str(le(self.timeOffsetText) + 240)
        self.TimeEdit.setText(self.timeOffsetText)
        self.setTimeOffset()
        
    def back4Min(self):
        self.timeOffsetText = str(le(self.timeOffsetText) - 240)
        self.TimeEdit.setText(self.timeOffsetText)
        self.setTimeOffset()
        
    def StartFF(self):
        self.FFClock.start(100)

    def StopFF(self):
        self.FFClock.stop()
    
    #@timer_func
    def setTimeOffset(self):
        try:
            self.timeOffsetText = self.TimeEdit.text()
            self.TimeEchoEdit.setText(self.timeOffsetText)
            self.ANGLE_OFFSET = apy.coordinates.Angle( self.timeOffsetText + 's') * 15
            self.TIME_OFFSET = le(self.timeOffsetText) * u.s
            self.updatePlot()
        except Exception as e:
            print(e)

    def getDistance(self, xs, ys):
        return np.sqrt((xs[1] - xs[0])**2 + (ys[1] - ys[0])**2)

    def split(self, start, end, segments):
        x_delta = (end[0] - start[0]) / float(segments)
        y_delta = (end[1] - start[1]) / float(segments)
        points = []
        for i in range(1, segments):
            points.append([start[0] + i * x_delta, start[1] + i * y_delta])
        return [start] + points + [end]

    def startSlew(self):
        self.startingPointing = self.currentPointing
        self.widget.canvas.setStartingPointing(self.startingPointing)
        sep = 3*int(self.currentPointing.separation(self.desiredPointing).deg)
        start = (self.currentPointing.ra.deg, self.currentPointing.dec.deg)
        stop = (self.desiredPointing.ra.deg, self.desiredPointing.dec.deg)
        ras, decs = zip(*self.split(start, stop, sep))
        self.slewPoints = apy.coordinates.SkyCoord(list(ras), list(decs), unit="deg")
        self.n = 0
        self.slewClock.start(500)

    def getStarsInsideAltAz(self, point):
        starsInside = self.stars[1][point.separation(self.stars[1]) < 1.75*u.deg]
        pointAltAz = self.observer.altaz(self.offsetTime, target=point)
        starsAltAz = self.observer.altaz(self.offsetTime, target=starsInside)
        self.dazs, self.dalts = pointAltAz.spherical_offsets_to(starsAltAz)
        dras, ddecs = point.spherical_offsets_to(starsInside)
        print('\n\n')
        print('++++++++++++++++++++++++')
        print('getStarsInsideAltAz:')
        print('STARS = ', len(dras))
        print('TIME = ', time)
        print(type(self.dalts))
        self.posToSend = []
        for j in range(len(dras)):
            print('-----')
            print('Star ', j, ':')
            print('Camera Coords (RA, dec): ( ', dras[j].deg,', ' , ddecs[j].deg, ' )')
            print('Camera Coords (Alt, Az): ( ', self.dalts[j].deg,', ' , self.dazs[j].deg, ' )')
            self.posToSend.append((self.dalts[j].deg, self.dazs[j].deg))
            print('Alt, Az: ( ', starsAltAz[j].alt,', ' , starsAltAz[j].az, ' )')
            print('-----')
        print('++++++++++++++++++++++++')
        print('self.postToSend')
        print(type(self.posToSend))
        print(self.posToSend)
        self.sendPos()
        self.TestScatter.canvas.updateWTF(self.dalts, self.dazs)
        self.TestScatter_2.canvas.updateWTF(dras, ddecs)
        self.TestScatter_3.canvas.updateWTF(starsAltAz.az, starsAltAz.alt)
    
    def setInstantPointingAndDraw(self):
        try:
            if self.n > 0:
                self.widget.canvas.setLastPointing(self.slewPoints[self.n-1])
            self.currentPointing = self.slewPoints[self.n]
            self.widget.canvas.setCurrentPointing(self.currentPointing)
            self.updatePlot()
            self.n += 1
            self.printPointings()
        except IndexError as e:
            print(e)
            print('Got stop at n=', self.n)
            self.slewClock.stop()
            self.n = 0
            self.widget.canvas.setCurrentPointing(self.slewPoints[-1])
            self.currentPointing = self.slewPoints[-1]
            
    def stopSlew(self):
        self.slewClock.stop()

        
        
        
QtCore.QThread.currentThread().setObjectName('MainThread')
app = QtWidgets.QApplication(sys.argv)
window = Window()
window.show()
sys.exit(app.exec_())       
