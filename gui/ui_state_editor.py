"""Editing the array state file in place.

state.json describes which telescopes and harvesters take part in a run.
The GUI is the source of truth for it: the whole file is sent to the
server with startRunCmd.
"""

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
import json

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
