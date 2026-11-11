"""Editing the array state file in place.

state.json describes which telescopes and harvesters take part in a run.
The GUI is the source of truth for it: the whole file is sent to the
server with startRunCmd.
"""

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
import json
import logging
import os

from qt_logging import logger

# Where File > Load state file opens, resolved from this file rather than the CWD.
DEFAULT_STATE_FILE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'server', 'internal', 'state.json'))

class StateEditorMixin:
    """state.json loading and in-place editing.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_state_editor(self):
        """Extracted verbatim from Window.__init__ (lines 560-567 of the pre-split file)."""


        self.actionLoad_state_file.triggered.connect(self.load_state_file)
        #self.actionLoad_config_file.triggered.connect(self.load_config_file)
        self.state_edit_check.toggled.connect(self.toggle_state_edit)  # Connect the checkbox to the function
        self.state_edit_check_was_checked = self.state_edit_check.isChecked()  # Store the initial state of the checkbox
        self.state_edit_set_button.clicked.connect(self.set_changes)
        self.state_edit_undo_button.clicked.connect(self.undo_changes)

        # Connected once, here. They used to be connected again on every load
        # and Set, each copy holding the value current at the time, so a
        # second state file lit up fields it had just loaded.
        self.state_data = None
        self.state_widget_map = self.build_state_widget_map()
        for widget, value_in_state in self.state_widget_map:
            self.connect_modified_signal(widget, value_in_state)

    def build_state_widget_map(self):
        """Pair every state-editor widget with a function returning its value in self.state_data."""
        widget_map = []
        for i in range(4):
            widget_map.append((getattr(self, f't{i+1}_state_telescope_missing_check'),
                               lambda i=i: self.state_data['telescopes'][i]['missing']))
            for j in range(8):
                h = lambda i=i, j=j: self.state_data['telescopes'][i]['harvesters'][j]
                widget_map += [
                    (getattr(self, f't{i+1}_state_array_position_spin_{j+1}'), lambda h=h: h()['arrayPosition']),
                    (getattr(self, f't{i+1}_state_local_position_spin_{j+1}'), lambda h=h: h()['localPosition']),
                    (getattr(self, f't{i+1}_state_harvester_missing_check_{j+1}'), lambda h=h: h()['missing']),
                    (getattr(self, f't{i+1}_state_ip_line_{j+1}'), lambda h=h: h()['ip']),
                    (getattr(self, f't{i+1}_state_channel_start_spin_{j+1}'), lambda h=h: h()['channel'][0]),
                    (getattr(self, f't{i+1}_state_channel_end_spin_{j+1}'), lambda h=h: h()['channel'][1]),
                    (getattr(self, f't{i+1}_state_pixel_index_start_spin_{j+1}'), lambda h=h: h()['pixelIndex'][0]),
                    (getattr(self, f't{i+1}_state_pixel_index_end_spin_{j+1}'), lambda h=h: h()['pixelIndex'][1]),
                ]
        return widget_map

    def state_has_unsaved_edits(self):
        """True if any state-editor widget differs from the loaded state (i.e. Set not pressed)."""
        if self.state_data is None:
            return False
        return any(self.widget_value(w) != value_in_state() for w, value_in_state in self.state_widget_map)

    def calculate_telescope_mask(self):
        mask = 0
        for i in range(4):
            telescope = self.state_data['telescopes'][i]
            mask |= telescope['missing'] << i
        return mask

    def calculate_harvester_mask(self):
        # A missing telescope takes all its harvesters with it, whatever their
        # own flags say -- the server never listens to them either.
        mask = 0
        for i in range(4):
            telescope = self.state_data['telescopes'][i]
            for j in range(8):
                harvester = telescope['harvesters'][j]
                mask |= (telescope['missing'] or harvester['missing']) << (i*8+j)
        return mask

    def load_state_file(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        # Start at server/internal/state.json (pre-selected) wherever the GUI was launched from.
        start = DEFAULT_STATE_FILE
        if not os.path.exists(start):
            start = os.path.dirname(start) if os.path.isdir(os.path.dirname(start)) else ""
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load State File", start, "JSON Files (*.json);;All Files (*)")
        if not file_name:
            return
        try:
            with open(file_name, 'r') as file:
                new_state = json.load(file)
            # Touch every field the editor needs, so a wrong-shaped file fails
            # here rather than half-way through filling the widgets.
            for i in range(4):
                new_state['telescopes'][i]['missing']
                for j in range(8):
                    h = new_state['telescopes'][i]['harvesters'][j]
                    h['arrayPosition'], h['localPosition'], h['missing'], h['ip'], h['channel'][1], h['pixelIndex'][1]
        except Exception as e:
            logger.log(logging.ERROR, f"Could not load state file {file_name}: {e!r}. The previous state is unchanged.", extra=extra)
            return

        self.state_data = new_state
        self.update_widgets_from_state()
        self.restore_original_colors(self.state_widgets())
        self.state_edit_set_button.setEnabled(True)
        self.state_edit_undo_button.setEnabled(True)
        self.state_edit_check.setEnabled(True)
        self.VO_db_params_telescope_mask_line.setText(bin(self.calculate_telescope_mask()))
        self.VO_db_params_harvester_mask_line.setText(hex(self.calculate_harvester_mask()))
        logger.log(logging.INFO, f"Loaded state file {file_name}.", extra=extra)
        self.refresh_start_button()

    def state_widgets(self):
        return [w for w, _ in self.state_widget_map]

    def undo_changes(self):
        if self.state_data is None:
            return
        self.update_widgets_from_state()
        self.restore_original_colors(self.state_widgets())
        self.refresh_start_button()

    def set_changes(self):
        if self.state_data is None:
            return
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
        
        self.restore_original_colors(self.state_widgets())
        self.VO_db_params_telescope_mask_line.setText(bin(self.calculate_telescope_mask()))
        self.VO_db_params_harvester_mask_line.setText(hex(self.calculate_harvester_mask()))
        self.refresh_start_button()

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

    def widget_value(self, widget):
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        if isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            return widget.value()
        return None

    def connect_modified_signal(self, widget, value_in_state):
        """Highlight ``widget`` whenever it differs from ``value_in_state()``, read at signal time."""
        def on_change(*_):
            try:
                original_value = value_in_state()
            except (TypeError, KeyError, IndexError):
                return  # Nothing loaded yet.
            self.mark_widget_as_modified(widget, original_value)
            self.refresh_start_button()

        if isinstance(widget, QtWidgets.QCheckBox):
            widget.toggled.connect(on_change)
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(on_change)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.currentTextChanged.connect(on_change)
        else:
            widget.valueChanged.connect(on_change)

    def mark_widget_as_modified(self, widget, original_value):
        if not hasattr(self, 'original_styles'):
            self.original_styles = {}

        if self.widget_value(widget) == original_value:
            if widget in self.original_styles:
                widget.setStyleSheet(self.original_styles.pop(widget))
        else:
            if widget not in self.original_styles:
                self.original_styles[widget] = widget.styleSheet()

            widget.setStyleSheet("background-color: yellow;")

    def restore_original_colors(self, widgets=None):
        """Undo the yellow highlight on ``widgets``, or on every highlighted widget if None.

        Callers pass their own panel's widgets: Set or Undo on the observing
        parameters used to clear the state editor's highlights too.
        """
        if not hasattr(self, 'original_styles'):
            return
        for widget in list(self.original_styles):
            if widgets is None or widget in widgets:
                widget.setStyleSheet(self.original_styles.pop(widget))
