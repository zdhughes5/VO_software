"""Observing parameters and the VO PostgreSQL run-metadata panel.

Two panels that both describe a run: the observing parameters the
operator sets up front, and the row written to the local telescope_db.
"""

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from datetime import datetime
from ast import literal_eval as le
import logging
import psycopg
import time

from qt_logging import logger

class RunMetadataMixin:
    """Observing parameters and run metadata.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_obs_params(self):
        """Extracted verbatim from Window.__init__ (lines 597-611 of the pre-split file)."""
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

    def _setup_vo_db_params(self):
        """Extracted verbatim from Window.__init__ (lines 613-668 of the pre-split file)."""
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

        #self.populate_dt.clicked.connect(self.set_current_datetime)
        self.populate_dt.clicked.connect(self.unlock_start_button)
        self.wrtie_db.clicked.connect(self.write_VO_db_params_to_db)

    def unlock_start_button(self):
        self.VO_db_params_run_window_line.setText(self.fadc_gate_array_window_combo.currentText().split(' ')[0])
        self.StartButton.setEnabled(True)

    def get_VO_db_params_filled_short(self):
        return {key: self.VO_db_params_filled[key] for key in ['run_id', 'veritas_run_id', 'run_type', 'run_window', 'duration', 'telescope_mask', 'harvester_mask', 'source_id']}

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
                le(self.VO_db_params['telescope_mask']),  # integer
                le(self.VO_db_params['harvester_mask']),  # integer
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
