"""Test-tab controls for server/bin/send_command generate.

Sends dummy 308-byte packets to the harvester addresses of the loaded state,
so a run can be exercised without real harvesters. send_command is run as a
QProcess so the GUI stays responsive and the run can be killed.
"""

from pyqtgraph.Qt import QtCore
import json
import logging
import os
import tempfile

from qt_logging import logger

SEND_COMMAND_PATH = "../server/bin/send_command"


class SendCommandMixin:
    """send_command generate, driven from the Test tab.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_send_command(self):
        self.send_command_process = None
        self.send_command_state_file = None
        self.send_command_partial = {'stdout': '', 'stderr': ''}
        self.sc_generate_button.clicked.connect(self.send_command_generate)
        self.sc_kill_button.clicked.connect(self.send_command_kill)
        self.sc_kill_button.setEnabled(False)

    def send_command_generate(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.send_command_process is not None:
            logger.log(logging.WARNING, "send_command is already running.", extra=extra)
            return
        if self.state_data is None:
            logger.log(logging.ERROR, "send_command: load a state file first; the packets go to its harvester addresses.", extra=extra)
            return
        program = os.path.abspath(SEND_COMMAND_PATH)
        if not os.path.isfile(program):
            logger.log(logging.ERROR, f"send_command: {program} not found -- run make in server/.", extra=extra)
            return
        if self.state_has_unsaved_edits():
            logger.log(logging.WARNING, "send_command: the state editor has unsaved edits; packets go to the last Set state.", extra=extra)

        # send_command reads the harvester addresses from a state file, so hand
        # it the GUI's state rather than its own hardcoded default.
        fd, self.send_command_state_file = tempfile.mkstemp(prefix='vo_state_', suffix='.json')
        with os.fdopen(fd, 'w') as f:
            json.dump(self.state_data, f)

        targets = [h['ip'] for t in self.state_data['telescopes'] if not t['missing']
                   for h in t['harvesters'] if not h['missing']]
        n_packets = self.sc_max_packets_spin.value()
        interval_us = self.sc_interval_us_spin.value()
        logger.log(logging.INFO, f"send_command: generating {n_packets} packets every {interval_us} µs to {', '.join(targets) or 'no harvesters'}.", extra=extra)

        process = QtCore.QProcess(self)
        process.setWorkingDirectory(os.path.dirname(program))
        process.readyReadStandardOutput.connect(lambda: self.send_command_read('stdout'))
        process.readyReadStandardError.connect(lambda: self.send_command_read('stderr'))
        process.finished.connect(self.send_command_finished)
        process.errorOccurred.connect(self.send_command_error)
        self.send_command_process = process
        self.send_command_set_running(True)
        process.start(program, ['--state', self.send_command_state_file, 'generate', str(n_packets), str(interval_us)])

    def send_command_read(self, channel):
        """Forward complete output lines to the log panel; keep any partial line for next time."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        process = self.send_command_process
        if process is None:
            return
        raw = process.readAllStandardOutput() if channel == 'stdout' else process.readAllStandardError()
        text = self.send_command_partial[channel] + bytes(raw).decode(errors='replace')
        *lines, self.send_command_partial[channel] = text.split('\n')
        level = logging.INFO if channel == 'stdout' else logging.WARNING
        for line in lines:
            if line.strip():
                logger.log(level, f"send_command: {line}", extra=extra)

    def send_command_finished(self, exit_code, exit_status):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        for channel in ('stdout', 'stderr'):
            self.send_command_read(channel)
            if self.send_command_partial[channel].strip():
                logger.log(logging.INFO, f"send_command: {self.send_command_partial[channel]}", extra=extra)
            self.send_command_partial[channel] = ''
        if exit_status == QtCore.QProcess.ExitStatus.CrashExit:
            logger.log(logging.WARNING, "send_command was killed.", extra=extra)
        elif exit_code == 0:
            logger.log(logging.INFO, "send_command finished.", extra=extra)
        else:
            logger.log(logging.ERROR, f"send_command exited with code {exit_code}.", extra=extra)
        self.send_command_cleanup()

    def send_command_error(self, error):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        # A process that crashes or is killed also gets finished(); only a
        # failure to start needs cleaning up here.
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            logger.log(logging.ERROR, f"send_command failed to start: {self.send_command_process.errorString()}", extra=extra)
            self.send_command_cleanup()

    def send_command_kill(self):
        if self.send_command_process is not None:
            self.send_command_process.kill()
            # Bounded: returns as soon as the process is gone, and finished()
            # then does the cleanup.
            self.send_command_process.waitForFinished(2000)

    def send_command_cleanup(self):
        if self.send_command_state_file is not None:
            try:
                os.remove(self.send_command_state_file)
            except OSError:
                pass
            self.send_command_state_file = None
        if self.send_command_process is not None:
            self.send_command_process.deleteLater()
            self.send_command_process = None
        self.send_command_set_running(False)

    def send_command_set_running(self, running):
        self.sc_generate_button.setEnabled(not running)
        self.sc_kill_button.setEnabled(running)
        self.sc_status_label.setText('running: generate' if running else 'idle')
