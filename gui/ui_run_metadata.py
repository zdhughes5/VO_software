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
        self.obs_widget_map = [
            (self.obs_params_save_path_line, lambda: self.obs_params['SavePath']),
            (self.obs_params_sourceid_line, lambda: self.obs_params['SourceID']),
            (self.obs_params_veritas_runid_spin, lambda: self.obs_params['VERITASRunNumber']),
            (self.obs_params_run_type_combo, lambda: self.obs_params['RunType']),
            (self.obs_params_duration_spin, lambda: self.obs_params['RunDuration']),
        ]
        for widget, value_in_state in self.obs_widget_map:
            self.connect_modified_signal(widget, value_in_state)
        self.obs_params_set_button.clicked.connect(self.obs_set_changes)
        self.obs_params_undo_button.clicked.connect(self.obs_undo_changes)
        self.obs_params_veritas_runid_query_button.clicked.connect(self.query_veritas_sql)

    def _setup_vo_db_params(self):
        """Extracted verbatim from Window.__init__ (lines 613-668 of the pre-split file)."""
        self.start_override = False  # Debug override of the Start checks; read by refresh_start_button.
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
        self.populate_dt.clicked.connect(self.force_unlock_start_button)
        self.wrtie_db.clicked.connect(self.write_VO_db_params_to_db)

        # The Test tab's controls bypass the run checks, so they sit behind a
        # checkbox. They stay available, so the GUI can never lock you out
        # completely, but they cannot be hit by accident.
        self.debug_controls_frame.setEnabled(False)
        self.debug_mode_check.toggled.connect(self.set_debug_mode)

        self.refresh_start_button()

    def set_debug_mode(self, enabled):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.debug_controls_frame.setEnabled(enabled)
        if not enabled:
            self.start_override = False
        logger.log(logging.WARNING if enabled else logging.INFO,
                   f"Debug controls {'enabled -- populate dt overrides the Start checks' if enabled else 'disabled'}.", extra=extra)
        self.refresh_start_button()

    def force_unlock_start_button(self):
        """Debug override: enable Start whatever the checks say, until debug mode is switched off."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.VO_db_params_run_window_line.setText(self.fadc_gate_array_window_combo.currentText().split(' ')[0])
        self.start_override = True
        logger.log(logging.WARNING, "Start force-enabled by the debug override. Missing: " + (", ".join(self.start_blockers()) or "nothing"), extra=extra)
        self.refresh_start_button()

    def start_blockers(self):
        """Everything that currently stops a run from starting, in operator terms."""
        blockers = []
        if self.run_active:
            blockers.append("a run is in progress")
        if not self.server_connected:
            blockers.append("DAQ server not connected (start it, wait for heartbeat)")
        if self.state_data is None:
            blockers.append("no state file loaded (File > Load state file)")
        elif self.state_has_unsaved_edits():
            blockers.append("unsaved state edits (press Set or Undo in the state editor)")
        try:
            int(self.VO_db_params['run_id'])
        except ValueError:
            blockers.append("no VO run ID (is the local PostgreSQL running?)")
        labels = {'veritas_run_id': 'VERITAS run ID', 'run_type': 'run type', 'duration': 'duration',
                  'source_id': 'source ID (set it and press Set)', 'run_window': 'FADC window (press Set)'}
        for key, label in labels.items():
            if not self.VO_db_params_filled[key]:
                blockers.append(f"{label} not set")
        return blockers

    def refresh_start_button(self):
        """Recompute whether Start is allowed. Called whenever any input to that decision changes."""
        blockers = self.start_blockers()
        if self.start_override and self.debug_mode_check.isChecked():
            self.StartButton.setEnabled(True)
            self.StartButton.setToolTip("Debug override is on. Checks that would otherwise block Start:\n- "
                                        + "\n- ".join(blockers or ["none"]))
        else:
            self.StartButton.setEnabled(not blockers)
            self.StartButton.setToolTip("Ready to start." if not blockers
                                        else "Start is locked until:\n- " + "\n- ".join(blockers))

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
            INSERT INTO tblrun_info (run_id, veritas_run_id, run_type, run_status, run_window, db_start_time, db_end_time, data_start_time, data_end_time, duration, telescope_mask, harvester_mask, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # run_id is given explicitly: it is the number the .bin files were
            # named with, reserved from the sequence in reserve_run_id. Letting
            # the serial default pick it let the two drift apart.
            run_data = (
                int(self.VO_db_params['run_id']),  # integer
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
            logger.log(logging.INFO, f"VO DB parameters inserted successfully for run {self.VO_db_params['run_id']}", extra=extra)
        except Exception as e:
            logger.log(logging.ERROR, f"Error inserting VO DB parameters for run {self.VO_db_params['run_id']} -- its .bin files have no DB row: {e}", extra=extra)
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
            value = self.VO_db_params[key]
            self.VO_db_params_filled[key] = bool(value) and value != 'null'

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
        self.refresh_start_button()

    def dump_VO_db_params(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = "Current VO DB parameters:\n"
        for key, value in self.VO_db_params.items():
            print_string += f"{key}: {value} {self.VO_db_params_filled[key]}\n"
        logger.log(logging.INFO, print_string, extra=extra)

    def connect_to_vo_db(self):
        return psycopg.connect(
            dbname="telescope_db",
            user="vo_admin",
            password="lsttkc#$!",
            host="localhost",
            port="5432",
            connect_timeout=3
        )

    def read_last_run_id(self):
        """Show the run ID the next run will most likely get.

        Only a preview: reserve_run_id takes the real number from the sequence
        at Start. Never goes backwards past a number already used this
        session, so a run whose DB row failed to insert is not reused (the
        server would silently shunt its files to <run>_<tel>[_h<pos>]_<hex>.bin).
        """
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        next_run_id = None
        try:
            with self.connect_to_vo_db() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT last_value, is_called FROM tblrun_info_run_id_seq;")
                last_value, is_called = cursor.fetchone()
                cursor.execute("SELECT COALESCE(MAX(run_id), 0) FROM tblrun_info;")
                max_run_id = cursor.fetchone()[0]
            next_run_id = max(last_value + 1 if is_called else last_value, max_run_id + 1)
        except Exception as e:
            logger.log(logging.ERROR, f"Could not read the next run ID from the VO PostgreSQL DB: {e}", extra=extra)

        last_used = getattr(self, 'last_used_run_id', None)
        if last_used is not None:
            next_run_id = max(next_run_id or 0, last_used + 1)
        if next_run_id is not None:
            self.VO_db_params_runid_line.setText(str(next_run_id))

    def reserve_run_id(self):
        """Take the run ID for the run being started from the DB sequence.

        Returns the ID, or None if the DB could not be reached; the caller then
        falls back to the previewed number.
        """
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        try:
            with self.connect_to_vo_db() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT nextval('tblrun_info_run_id_seq');")
                run_id = cursor.fetchone()[0]
        except Exception as e:
            logger.log(logging.ERROR, f"Could not reserve a run ID from the VO PostgreSQL DB: {e}", extra=extra)
            return None

        # Numbers below last_used were taken this session without a DB row.
        last_used = getattr(self, 'last_used_run_id', None)
        if last_used is not None and run_id <= last_used:
            logger.log(logging.ERROR, f"Sequence gave run ID {run_id}, but {last_used} was already used this session; not using it.", extra=extra)
            return None
        return run_id

    def obs_widgets(self):
        return [w for w, _ in self.obs_widget_map]

    def obs_undo_changes(self):
        self.obs_update_widgets_from_state()
        self.restore_original_colors(self.obs_widgets())

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
        
        self.restore_original_colors(self.obs_widgets())
