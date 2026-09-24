"""The four camera panels and the pixel time series.

Owns the pyqtgraph view boxes, the 499-pixel scatter per telescope, the
colour mapping of variance to brush, the ROI selection and the incoming
8000-byte data datagram.
"""

from pyqtgraph.Qt.QtGui import QBrush, QColor
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from astropy.time import Time
from ast import literal_eval as le
import logging
import numpy as np
from time import perf_counter
import pyqtgraph as pg
import time

from qt_logging import logger

class CameraDisplayMixin:
    """Camera pixel display and time series.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_camera_display(self):
        """Extracted verbatim from Window.__init__ (lines 445-538 of the pre-split file)."""
        self.weights = np.zeros(499)
        self.hexSize = 12.4
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
        self.pixelMax = 66000
        self.colormap = pg.colormap.get('CET-CBL2')
        self.valueRange = np.linspace(0, self.pixelMax, num=self.nPts)
        self.valueRangeLog = np.logspace(0, np.log10(self.pixelMax), num=self.nPts)
        np.insert(self.valueRangeLog, 0, 0.0)
        #self.valueRange = np.linspace(0, 5000, num=self.nPts)
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
        #self.w5.addItem(self.pixelTimeSeriesDataCurve2)
        #self.w5.addItem(self.pixelTimeSeriesDataCurve3)
        #self.w5.addItem(self.pixelTimeSeriesDataCurve4)

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
        self.w5.disableAutoRange()
        self.w5.enableAutoRange(x=True)
        #self.w5.setRange(xRange=[0, 1000], padding=0)
        self.w5.setMouseEnabled(x=False, y=True)


        self.roi1.sigRegionChanged.connect(self.updateROI)
        
        self.updateROI(self.roi1)

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

    def update(self):
        #self.pixelData = self.listenOutQueue.get()
       # print(self.pixelData)
        
        #self.pixelData = np.random.randint(0, 63508, size=2000)
        if self.data_display_log_check.isChecked():
            self.brushes1 = self.colors2[np.searchsorted(self.valueRangeLog, self.pixelData[:499])]
            self.brushes2 = self.colors2[np.searchsorted(self.valueRangeLog, self.pixelData[500:999])]
            self.brushes3 = self.colors2[np.searchsorted(self.valueRangeLog, self.pixelData[1000:1499])]
            self.brushes4 = self.colors2[np.searchsorted(self.valueRangeLog, self.pixelData[1500:1999])]
        else:
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
            if self.sample_average == 1:
                self.pixelTimeSeriesData1[-1] = np.average(self.pixelData[:499][self.selected])
                self.pixelTimeSeriesData2[-1] = np.average(self.pixelData[500:999][self.selected])
                self.pixelTimeSeriesData3[-1] = np.average(self.pixelData[1000:1499][self.selected])
                self.pixelTimeSeriesData4[-1] = np.average(self.pixelData[1500:1999][self.selected])
            else:
                self.pixelTimeSeriesData1[-1] = np.average(self.pixelData[:499][self.selected])
                self.pixelTimeSeriesData2[-1] = np.average(self.pixelData[500:999][self.selected])
                self.pixelTimeSeriesData3[-1] = np.average(self.pixelData[1000:1499][self.selected])
                self.pixelTimeSeriesData4[-1] = np.average(self.pixelData[1500:1999][self.selected])

                # Calculate the average of the last N values including the current one
                self.pixelTimeSeriesData1[-1] = np.average(self.pixelTimeSeriesData1[-self.sample_average:])
                self.pixelTimeSeriesData2[-1] = np.average(self.pixelTimeSeriesData2[-self.sample_average:])
                self.pixelTimeSeriesData3[-1] = np.average(self.pixelTimeSeriesData3[-self.sample_average:])
                self.pixelTimeSeriesData4[-1] = np.average(self.pixelTimeSeriesData4[-self.sample_average:])
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

    def clear_time_series_data(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        # Reset the time series data to zero
        self.pixelTimeSeriesData1 = np.ones(1000)*self.pixelTimeSeriesData1[-1]
        self.pixelTimeSeriesData2 = np.ones(1000)*self.pixelTimeSeriesData2[-1]
        self.pixelTimeSeriesData3 = np.ones(1000)*self.pixelTimeSeriesData3[-1]
        self.pixelTimeSeriesData4 = np.ones(1000)*self.pixelTimeSeriesData4[-1]
        self.pixelTimeSeriesDataCurve1.setData(self.pixelTimeSeriesData1)
        self.pixelTimeSeriesDataCurve2.setData(self.pixelTimeSeriesData2)
        self.pixelTimeSeriesDataCurve3.setData(self.pixelTimeSeriesData3)
        self.pixelTimeSeriesDataCurve4.setData(self.pixelTimeSeriesData4)
        self.ptr1 = -1000
        logger.log(logging.INFO, "Time series data cleared.", extra=extra)

    def update_sample_average(self):
        self.sample_average = self.data_display_sample_spin.value()

    def getDatagramAndQueue(self):
        # Flush the socket, keeping only the latest datagram
        datagram = None
        while self.listenSocket.hasPendingDatagrams():
            datagram = self.listenSocket.receiveDatagram(8000)

        # readyRead can fire with nothing to read, and anything that is not a
        # full 4 x 500 float32 frame would break the slicing in update().
        if datagram is None or len(datagram.data()) != 8000:
            return
        pixelData = np.frombuffer(datagram.data(), dtype=np.float32)
        self.pixelData = pixelData
        #print(self.pixelData)
        self.update()
