#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Oct 11 20:54:47 2022

@author: zdhughes
"""

# Operator GUI for the VERITAS optical intensity-interferometry setup.
#
# This file holds the main window and little else. The behaviour is split
# across mixins, one module per panel -- see
# docs/2026-09-22-gui-module-split-plan.md for the layout and the reasoning.
#
#   qt_logging        shared logger, log panel
#   star_display      overlay settings, angle formatting
#   veritas_db        VERITAS MySQL workers
#   ui_camera         the four camera panels and the time series
#   ui_server         DAQ server, harvesters, FADC
#   ui_run_metadata   observing parameters and the VO run-metadata row
#   ui_state_editor   state.json editing
#   ui_star_overlay   star overlay and the SQL thread that feeds it
#   ui_send_command   Test-tab send_command generate (dummy packets)
#   vestigial         unreachable code, parked
#
# The mixins share Window's namespace: every `self` inside them is this
# window. That is organizational, not architectural -- real boundaries are a
# later refactor.

import logging
import sys

from pyqtgraph.Qt import QtWidgets, QtCore

from GUI import Ui_MainWindow
import resources_rc

from qt_logging import logger, LogPanelMixin, install_exception_logger
from ui_camera import CameraDisplayMixin
from ui_run_metadata import RunMetadataMixin
from ui_send_command import SendCommandMixin
from ui_server import ServerControlMixin
from ui_star_overlay import StarOverlayMixin
from ui_state_editor import StateEditorMixin
#from gui.holder.vestigial import VestigialMixin


class Window(QtWidgets.QMainWindow, Ui_MainWindow,
             LogPanelMixin, CameraDisplayMixin, ServerControlMixin,
             RunMetadataMixin, StateEditorMixin, StarOverlayMixin,
             SendCommandMixin):

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

        # Each _setup_* method below is a contiguous block lifted verbatim out
        # of the original 268-line __init__. The call order is the original
        # line order and must stay that way: later blocks rely on widgets and
        # attributes that earlier ones create.
        self._setup_log_panel()

        self.actionExit.triggered.connect(self.close)

        self.config_data = None

        self.starPos = [(0,0)]
        self.star_field = [None, None, None, None]
        self.star_field_labels = [None, None, None, None]
        self._setup_camera_display()
        self._setup_server_connection()
        self._setup_db_thread_state()
        self._setup_state_editor()
        self._setup_data_display_buttons()
        self._setup_obs_params()
        self._setup_vo_db_params()
        self._setup_fadc_and_run_buttons()
        self._setup_harvester_controls()
        self._setup_send_command()

    def closeEvent(self, event):
        if self.star_options_dialog is not None:
            self.star_options_dialog.close()
        self.stopWorker()
        self.send_command_kill()
        self.stop_server() # Make a purpose-built function to stop the server
        event.accept()


def load_stylesheet(app, qss_file):
    with open(qss_file, "r") as file:
        app.setStyleSheet(file.read())

if __name__ == "__main__":
        
    QtCore.QThread.currentThread().setObjectName('MainThread')
    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    install_exception_logger()
    load_stylesheet(app, "Genetive.qss")
    window.show()
    sys.exit(app.exec())
