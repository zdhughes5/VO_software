"""Control of the Go DAQ server, the harvesters and the FADC crates.

Covers launching and stopping ../server/bin/server, the UDP control and
heartbeat sockets, run status handling, harvester broadcast commands and
the SSH call that sets the FADC gate window.
"""

from multiprocessing import Process, Queue
from PyQt6.QtNetwork import QHostAddress, QUdpSocket, QNetworkDatagram
from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from datetime import datetime
import json
import logging
import os
import signal
import struct
import subprocess
import time

from qt_logging import logger

class ServerControlMixin:
    """DAQ server, harvester and FADC control.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_server_connection(self):
        """Extracted verbatim from Window.__init__ (lines 540-547 of the pre-split file)."""
        self.StartButton.clicked.connect(self.startRun)
        self.StopButton.clicked.connect(self.send_stop_message)
        self.s1.scene().sigMouseMoved.connect(self.onMouseMoved)


        # Inputs to refresh_start_button that this panel owns.
        self.run_active = False       # From the Start click until the run's end status.
        self.run_confirmed = False    # Server has sent "started" for the current run.
        self.server_connected = False # Heartbeats are coming back.
        self.heartbeatSendTimer = None
        self.heartbeatRecvTimer = None
        self.start_confirm_timer = QtCore.QTimer(self)
        self.start_confirm_timer.setSingleShot(True)
        self.start_confirm_timer.timeout.connect(self.handle_start_not_confirmed)

        # Window.__init__ sets this from --config; the default keeps the old path.
        if not getattr(self, 'config_file', None):
            self.config_file = '../server/internal/server.json'
        self.load_config_file()
        self.establish_connections()

        # serverMode "local": this GUI launches and stops server/bin/server
        # itself. "remote": the server runs on another machine (the trailer
        # PC) as a service; this GUI only heartbeats it and starts/stops runs,
        # and never asks it to exit.
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.server_mode = (self.config_data or {}).get('serverMode', 'local')
        if self.server_mode not in ('local', 'remote'):
            logger.log(logging.WARNING, f"Unknown serverMode {self.server_mode!r} in {self.config_file}; using 'local'.", extra=extra)
            self.server_mode = 'local'
        if self.server_mode == 'remote':
            self.VO_server_start_button.setText('Connect')
            self.VO_server_stop_button.setText('Disconnect')
            # After __init__ finishes, so every widget and attribute exists.
            QtCore.QTimer.singleShot(0, self.start_server)

    def is_remote_server(self):
        return getattr(self, 'server_mode', 'local') == 'remote'

    def _setup_fadc_and_run_buttons(self):
        """Extracted verbatim from Window.__init__ (lines 670-673 of the pre-split file)."""
        self.fadc_gate_array_window_set_button.clicked.connect(self.set_fadc_gate_array_window)

        self.send_stop_button.clicked.connect(self.send_stop_message)
        #self.StartButton.clicked.connect(self.request_listen)

    def _setup_harvester_controls(self):
        """Extracted verbatim from Window.__init__ (lines 675-689 of the pre-split file)."""
        self.harvester_command_c001_button.clicked.connect(lambda: self.send_harvester_packet('c001', log=True))
        self.harvester_command_c002_button.clicked.connect(lambda: self.send_harvester_packet('c002', log=True))
        self.harvester_command_c003_button.clicked.connect(lambda: self.send_harvester_packet('c003', log=True))
        self.harvester_command_c004_button.clicked.connect(lambda: self.send_harvester_packet('c004', log=True))
        
        # Initialize the timer
        self.harvester_timer = QtCore.QTimer(self)
        self.harvester_timer.timeout.connect(lambda: self.send_harvester_packet('c004'))
        
        self.harvester_command_start_time_pulse_button.clicked.connect(self.start_harvester_timer)
        self.harvester_command_stop_time_pulse_button.clicked.connect(self.stop_harvester_timer)

        self.sample_average = 1

        self.data_display_sample_button.clicked.connect(self.update_sample_average)

    def start_harvester_timer(self):
        self.harvester_timer.start(1000)  # Start the timer with a 1-second interval
        self.harvester_command_time_status_label.setStyleSheet("background-color: green; color: white;")
        self.harvester_command_time_status_label.setText("Active")

    def stop_harvester_timer(self):
        self.harvester_timer.stop()  # Stop the timer
        self.harvester_command_time_status_label.setStyleSheet("background-color: yellow; color: black;")
        self.harvester_command_time_status_label.setText("Inactive")

    def send_harvester_packet(self, command, log=False):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        try:
            # Define the host and port from the configuration
            host = QHostAddress(self.config_data['harvesterControlConnIP'].split(':')[0])
            port = int(self.config_data['harvesterControlConnIP'].split(':')[1])
            #host = QHostAddress.SpecialAddress.Broadcast
            #host = QHostAddress('255.255.255.255')
            #port = 5000
            socket = QUdpSocket()
            logger.log(logging.INFO, f'HOST IS BROADCAST: {QHostAddress.isBroadcast(host)}', extra=extra)

            
            # Prepare the data to be sent
            if command == 'c004':
                hex_timestamp = self.get_hex_timestamp()
                big_send = True
            else:
                big_send = False
            
            if big_send:
                hex_timestamp = int(hex_timestamp, 16)
                datum = struct.pack('>HI', int(command, 16), hex_timestamp)
            else:
                datum = struct.pack('>HI', int(command, 16), 0)

            if self.config_data.get('harvesterCommandsViaServer', False):
                # Relay through the DAQ server, for when this machine cannot
                # reach the harvester network itself. Same bytes, hex-encoded.
                server_ip, server_port = self.config_data['serverControlConnIP'].split(':')
                message = json.dumps({
                    "command": int(self.config_data['commands']['harvesterCmd']),
                    "payload": datum.hex(),
                    "log": bool(log),
                })
                nSent = self.heartbeatSocket.writeDatagram(message.encode(), QHostAddress(server_ip), int(server_port))
                if log:
                    logger.log(logging.INFO, f"Sent {datum!r} to the server at {server_ip}:{server_port} for relay to {self.config_data['harvesterControlConnIP']} ({nSent} bytes)", extra=extra)
                return

            # Send the datagram using self.heartbeatSocket
            datagram = QNetworkDatagram()
            datagram.setDestination(host, port)
            datagram.setHopLimit(255)
            datagram.setData(datum)
            nSent = socket.writeDatagram(datagram)
            if log:
                logger.log(logging.INFO, f'Sent datagram of size {nSent} and contents: {datum}', extra=extra)
        except Exception as e:
            logger.log(logging.ERROR, f'Failed to send UDP packet: {e}', extra=extra)

    def get_hex_timestamp(self):
        timestamp = int(time.time())
        return hex(timestamp)[2:]

    def request_listen(self):
        """Send startRunCmd for the current VO DB parameters. Returns True if it was sent."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.state_data is None:
            logger.log(logging.ERROR, "Cannot start: no state file loaded.", extra=extra)
            return False
        try:
            int(self.VO_db_params['run_id'])
            int(self.VO_db_params['duration'])
        except ValueError:
            logger.log(logging.ERROR, f"Cannot start: run ID {self.VO_db_params['run_id']!r} or duration {self.VO_db_params['duration']!r} is not a number.", extra=extra)
            return False

        # Create data_map with parameters from VO_db_params and self.config_data
        data_map = {
            "command": int(self.config_data['commands']['startRunCmd']),
            "runNumber": int(self.VO_db_params['run_id']),
            "duration": int(self.VO_db_params['duration']),
            "sendInterval": int(self.config_data['sendInterval']),
            "dataSaveDir": self.config_data['dataSavePath'],
            "state": json.dumps(self.state_data)  # Use self.state_data instead of reading the state.json file
        }

        # Convert map to JSON



        try:
            json_data = json.dumps(data_map)
        except (TypeError, ValueError) as err:
            logger.log(logging.ERROR, f"Error marshaling JSON: {err}", extra=extra)
            return False

        #print(f"command is type {type(data_map['command'])}")

        server_control_ip, server_control_port = self.config_data['serverControlConnIP'].split(':')
        server_control_port = int(server_control_port)

        datagram = json_data.encode()

        nSent = self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port)
        if nSent != len(datagram):
            logger.log(logging.ERROR, f"Error sending start command over UDP: {self.heartbeatSocket.errorString()}", extra=extra)
            return False
        return True

    def execute_binary_over_ssh(self, hostname, username, binary_path, argument, options=''):
        """
        Executes a binary on a remote server over SSH.

        :param hostname: The hostname or IP address of the remote server.
        :param username: The username for the SSH connection.
        :param binary_path: The path to the binary on the remote server.
        :param argument: The command line argument to pass to the binary.
        """
        try:
            # Construct the SSH command
            ssh_command = f"ssh {options} -t {username}@{hostname} '{binary_path} {argument}'"
            print(ssh_command)
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
            logger.log(logging.INFO, f'Sent request: {ssh_command}', extra=extra)
            print('e')
            
            # Execute the command
            process = subprocess.Popen(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,  preexec_fn=lambda: signal.alarm(5))
            #process = subprocess.run(['/home/labuser/VO_software/gui/variance_script.sh'], capture_output=True, text=True, timeout=10)
            print('f')
            # Read the output and error streams

            output, error = process.communicate()
            #except subprocess.TimeoutExpired:
            #    process.kill()
            #    stdout, stderr = process.communicate()
            print('g')
            # Decode the output and error
            output = output.decode()
            error = error.decode()
            #output = process.stdout
            #error = process.stderr

            if output == '':
                logger.log(logging.WARNING, f'Got no output from set_variance. Probably timed out. Did the window really get set?', extra=extra)
            
            # Log the output and errors
            if output:
                logger.log(logging.INFO, f'Output: {output}', extra=extra)
            if error:
                logger.log(logging.ERROR, f'Error (unless it is a closed connection): {error}', extra=extra)
            
        except Exception as e:
            logger.log(logging.ERROR, f"Failed to execute binary over SSH: {str(e)}", extra=extra)

    def set_fadc_gate_array_window(self):
        with open('../server/internal/fadc.json', 'r') as f:
            fadc_data = json.load(f)
        ip = fadc_data['telescopes'][0]['crates'][0]['ip']
        username = fadc_data['telescopes'][0]['crates'][0]['username']
        options = fadc_data['telescopes'][0]['crates'][0]['commandOptions']
        self.VO_db_params_run_window_line.setText(self.fadc_gate_array_window_combo.currentText().split(' ')[0])
        #self.execute_binary_over_ssh('10.0.10.102', 'vdaq', '/home/vdaq/VO/set_variance/set_variance', f'{self.fadc_gate_array_window_combo.currentText().split(' ')[0]}')
        #THIS BEFORE self.execute_binary_over_ssh('10.0.7.20', 'observer', '/home/observer/zach/VERITAS_upgrade/washu-fadc/set_variance/set_variance', f'{self.fadc_gate_array_window_combo.currentText().split(' ')[0]}')
        self.execute_binary_over_ssh(ip, username, '/home/vdaq/VO/set_variance/set_variance', f'{self.fadc_gate_array_window_combo.currentText().split(' ')[0]}', options=options)
        #self.execute_binary_over_ssh(ip, username, 'ls', '-a', options=options)

    def start_heartbeats(self):
        """Heartbeat the server once a second and declare it lost after 3 s of silence."""
        self.stop_heartbeat_timers()

        self.heartbeatSendTimer = QtCore.QTimer()
        self.heartbeatSendTimer.timeout.connect(self.send_heartbeat)
        self.heartbeatSendTimer.start(1000)  # Send a heartbeat every 1 seconds

        self.heartbeatRecvTimer = QtCore.QTimer()
        self.heartbeatRecvTimer.timeout.connect(self.handle_heartbeat_timeout)
        self.heartbeatRecvTimer.start(3000)  # Declare the server lost after 3 s without a heartbeat

    def connect_remote_server(self):
        """serverMode remote: start heartbeating a server that runs elsewhere."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.heartbeatSendTimer is not None:
            logger.log(logging.WARNING, "Already connected (or connecting) to the remote server.", extra=extra)
            return
        logger.log(logging.INFO,
                   f"Connecting to remote server at {self.config_data['serverControlConnIP']} "
                   f"(serverMode remote; replies expected on {self.config_data['guiHeartbeatConnIP']}).",
                   extra=extra)
        self.VO_server_status_line.setStyleSheet("background-color: yellow; color: black;")
        self.VO_server_status_line.setText("Connecting")
        self.start_heartbeats()
        self.send_heartbeat()  # Don't wait a second for the first one.

    def disconnect_remote_server(self):
        """serverMode remote: stop heartbeating. The server itself keeps running."""
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.run_active:
            logger.log(logging.WARNING,
                       f"Disconnecting during run {self.VO_db_params['run_id']}: the run continues on the server, "
                       f"but this GUI will not see its end status or write its DB row.",
                       extra=extra)
        self.stop_heartbeat_timers()
        self.server_connected = False
        self.VO_server_status_line.setStyleSheet("background-color: yellow; color: black;")
        self.VO_server_status_line.setText("Not connected")
        logger.log(logging.INFO, "Stopped heartbeating the remote server; it is still running on its own machine.", extra=extra)
        self.refresh_start_button()

    def start_server(self):
        if self.is_remote_server():
            self.connect_remote_server()
            return
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        # poll() rather than a bare truth test: a server that died on its own
        # leaves its Popen behind, and that used to block every restart.
        if self.server_process is not None and self.server_process.poll() is not None:
            logger.log(logging.WARNING, f"Previous server (PID {self.server_process.pid}) had exited with code {self.server_process.returncode}.", extra=extra)
            self.stop_heartbeat_timers()
            self.server_process = None
        if not self.server_process:
            try:
                server_path = os.path.abspath("../server/bin/server")
                server_dir = os.path.dirname(server_path)
                self.server_process = subprocess.Popen([server_path], cwd=server_dir)

                self.start_heartbeats()

                logger.log(logging.INFO, f"Server started successfully with PID: {self.server_process.pid}", extra=extra)
            except Exception as e:
                logger.log(logging.ERROR, f"Failed to start server: {e}", extra=extra)
        else:
            print_string = f"Server is already running at PID: {self.server_process.pid}"
            logger.log(logging.WARNING, print_string, extra=extra)

    def stop_heartbeat_timers(self):
        for timer in (getattr(self, 'heartbeatSendTimer', None), self.heartbeatRecvTimer):
            if timer is not None:
                timer.stop()
                try:
                    timer.timeout.disconnect()
                except TypeError:
                    pass  # Nothing connected.
        self.heartbeatSendTimer = None
        self.heartbeatRecvTimer = None

    def stop_server(self):
        """Ask the server to exit, and make sure it has, without blocking the GUI for long.

        The old unbounded wait() froze the GUI -- and closing it -- whenever
        the server did not exit on request.

        In serverMode remote this only disconnects: the server belongs to the
        trailer machine's service and is never told to exit from here.
        """
        if self.is_remote_server():
            self.disconnect_remote_server()
            return
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if not self.server_process:
            logger.log(logging.INFO, "Server is not running.", extra=extra)
            return

        try:
            server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
            exit_message = json.dumps({"command": int(self.config_data['commands']['exitCmd'])})
            self.heartbeatSocket.writeDatagram(exit_message.encode(), QHostAddress(server_control_ip), int(server_control_port))
        except Exception as e:
            logger.log(logging.ERROR, f"Failed to send exit command to server: {e}", extra=extra)

        self.stop_heartbeat_timers()

        process = self.server_process
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.log(logging.WARNING, f"Server PID {process.pid} ignored the exit command; terminating it.", extra=extra)
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logger.log(logging.WARNING, f"Server PID {process.pid} ignored SIGTERM; killing it.", extra=extra)
                process.kill()
                process.wait()
        logger.log(logging.INFO, f"Server process with PID {process.pid} has exited (code {process.returncode}).", extra=extra)

        self.server_process = None
        self.server_connected = False
        self.VO_server_status_line.setStyleSheet("background-color: yellow; color: black;")
        self.VO_server_status_line.setText("Stopped")
        self.refresh_start_button()

    def bind_or_complain(self, socket, name, ip, port):
        """Bind a UDP socket, and say so loudly if the port is already taken.

        An unchecked bind is how this fails in practice: if something else
        already holds the port, Qt returns False, the socket stays dead, and
        the only symptom is "Heartbeat timeout" every three seconds with no
        indication why. That happened for real -- an orphaned process held
        31255/31256/31257 for a day while the server replied correctly into
        its socket. The usual cause is a second GUI, or a crashed one whose
        process is still alive.
        """
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }

        if socket.bind(QHostAddress(ip), int(port)):
            return True

        logger.log(logging.ERROR,
                   f"Could not bind the {name} socket to {ip}:{port} ({socket.errorString()}). "
                   f"Something else is using that port -- most likely another copy of this GUI, "
                   f"or one that was killed without releasing it (check: ss -lunp | grep {port}). "
                   f"This socket will receive nothing until that is cleared.",
                   extra=extra)
        return False

    def establish_connections(self):

        gui_data_ip, gui_data_port = self.config_data["guiDataConnIP"].split(':')
        gui_heartbeat_ip, gui_heartbeat_port = self.config_data["guiHeartbeatConnIP"].split(':')
        gui_status_ip, gui_status_port = self.config_data["guiStatusConnIP"].split(':')

        self.listenSocket = QUdpSocket()
        self.bind_or_complain(self.listenSocket, 'data', gui_data_ip, gui_data_port)
        self.listenSocket.readyRead.connect(self.getDatagramAndQueue)

        self.VO_server_ip_line.setText(self.config_data["serverControlConnIP"])

        self.heartbeatSocket = QUdpSocket()
        self.bind_or_complain(self.heartbeatSocket, 'heartbeat', gui_heartbeat_ip, gui_heartbeat_port)
        self.heartbeatSocket.readyRead.connect(self.got_heartbeat)

        self.statusSocket = QUdpSocket()
        self.bind_or_complain(self.statusSocket, 'status', gui_status_ip, gui_status_port)
        self.statusSocket.readyRead.connect(self.got_status)

    def invert_dict(self, d):
        return {v: k for k, v in d.items()}

    def get_key_from_value(self, inverted_dictionary, value):
        return inverted_dictionary.get(value, None)

    def got_status(self):
        # Read every pending datagram: a short run's "started" and "ended" can
        # arrive together, and an unread one may not raise readyRead again.
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        while self.statusSocket.hasPendingDatagrams():
            datagram = self.statusSocket.receiveDatagram(8000)
            try:
                self.handle_status(bytes(datagram.data()))
            except Exception as e:
                logger.log(logging.ERROR, f"Error handling server status {bytes(datagram.data())!r}: {e!r}", extra=extra)
        self.refresh_start_button()

    def handle_status(self, data):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if len(data) != 4:
            logger.log(logging.WARNING, f"Ignoring {len(data)}-byte datagram on the status port.", extra=extra)
            return
        status_code = struct.unpack('>I', data)[0]  # '>I' for big-endian unsigned int
        statuses = self.invert_dict(self.config_data["status"])
        status_key = self.get_key_from_value(statuses, status_code)

        logger.log(logging.INFO, f"Received status: {status_code}, corresponding to {status_key}", extra=extra)

        if status_code == self.config_data["status"]["started"]:
            self.start_confirm_timer.stop()
            self.run_active = True
            self.run_confirmed = True
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_start_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_db_end_time_line.setText('null')
            self.VO_db_params_data_end_time_line.setText('null')
            self.VO_db_params_filled['db_end_time'] = False
            self.VO_db_params_filled['data_end_time'] = False
            self.set_gui_components_enabled(False)
        elif status_code == self.config_data["status"]["aborted"]:
            # Sent when the server could not set the run up (bad data dir,
            # harvester address not on this host, ...). The server log says which.
            logger.log(logging.ERROR, "The server aborted the run during setup; see server/log/server.log.", extra=extra)
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.end_run()
        elif status_code in (self.config_data["status"]["ended"], self.config_data["status"]["ended_manually"]):
            self.VO_db_params_run_status_line.setText(status_key)
            self.VO_db_params_db_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.VO_db_params_data_end_time_line.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.write_VO_db_params_to_db()
            self.end_run()
        else:
            logger.log(logging.WARNING, f"Received unknown status: {status_code}", extra=extra)

    def end_run(self):
        """Release the GUI after a run, however it ended, and move to the next run ID."""
        self.start_confirm_timer.stop()
        self.run_active = False
        self.run_confirmed = False
        self.set_gui_components_enabled(True)
        self.read_last_run_id()
        self.refresh_start_button()

    def handle_start_not_confirmed(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.run_active and not self.run_confirmed:
            logger.log(logging.ERROR, "The server did not confirm the run start within 5 s; releasing the controls. Check the server status and server/log/server.log.", extra=extra)
            self.end_run()

    def set_gui_components_enabled(self, enabled):
        if not enabled:
            # If disabling, check the state of self.state_edit
            if self.state_edit_check_was_checked:
                self.toggle_state_edit(False)  # Disable the state boxes
                self.state_edit_check_was_checked = True
            else:
                self.state_edit_check_was_checked = False
            self.state_edit_check.setEnabled(False)
            self.state_edit_undo_button.setEnabled(False)
            self.state_edit_set_button.setEnabled(False)

        else:
            # If enabling, check the previous state stored in self.state_edit_check_was_checked
            self.toggle_state_edit(self.state_edit_check_was_checked)  # Re-enable the state boxes
            self.state_edit_check.setEnabled(True)
            self.state_edit_undo_button.setEnabled(True)
            self.state_edit_set_button.setEnabled(True)

        # Enable or disable the other components
        self.obs_params_undo_button.setEnabled(enabled)
        self.obs_params_set_button.setEnabled(enabled)
        self.obs_params_save_path_line.setEnabled(enabled)
        self.obs_params_sourceid_line.setEnabled(enabled)
        self.obs_params_veritas_runid_spin.setEnabled(enabled)
        self.obs_params_veritas_runid_query_button.setEnabled(enabled)
        self.obs_params_run_type_combo.setEnabled(enabled)
        self.obs_params_duration_spin.setEnabled(enabled)
        self.veritas_sql_ping_button.setEnabled(enabled)
        self.fadc_gate_array_window_set_button.setEnabled(enabled)
        self.fadc_gate_array_window_combo.setEnabled(enabled)
        # A new state mid-run would change the masks written to the DB for the
        # run in progress; stopping the server mid-run loses its DB row.
        self.actionLoad_state_file.setEnabled(enabled)
        self.VO_server_stop_button.setEnabled(enabled)
        self.populate_dt.setEnabled(enabled)
        self.wrtie_db.setEnabled(enabled)

    def got_heartbeat(self):
        while self.heartbeatSocket.hasPendingDatagrams():
            self.heartbeatSocket.receiveDatagram(8000)
        self.VO_server_status_line.setStyleSheet("background-color: green; color: white;")
        self.VO_server_status_line.setText("Connected")
        if self.heartbeatRecvTimer is not None:
            self.reset_heartbeat_timer()
        if not self.server_connected:
            self.server_connected = True
            self.refresh_start_button()

    def reset_heartbeat_timer(self):
        self.heartbeatRecvTimer.stop()
        self.heartbeatRecvTimer.start(3000)  # Reset the 3-second timeout

    def handle_heartbeat_timeout(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        self.VO_server_status_line.setStyleSheet("background-color: red; color: white;")
        self.VO_server_status_line.setText("Disconnected")
        logger.log(logging.WARNING, "Heartbeat timeout. VO server disconnected.", extra=extra)
        self.server_connected = False
        if self.run_active:
            # No end status will come from a dead server; without this the
            # controls would stay locked for good.
            logger.log(logging.ERROR, f"Lost the server during run {self.VO_db_params['run_id']}; releasing the controls. No DB row will be written unless the server recovers and reports the run's end.", extra=extra)
            self.end_run()
        self.refresh_start_button()

    def send_heartbeat(self):
        server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
        server_control_port = int(server_control_port)

        # Create the JSON object
        heartbeat_message = json.dumps({"command": 7})
        datagram = heartbeat_message.encode()

        self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port)
        #print(f"Sent heartbeat to {server_heartbeat_ip}:{server_heartbeat_port} with message: {heartbeat_message}")

    def send_stop_message(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        server_control_ip, server_control_port = self.config_data["serverControlConnIP"].split(':')
        server_control_port = int(server_control_port)

        # Create the JSON object
        stop_message = json.dumps({"command": 8})
        datagram = stop_message.encode()

        self.heartbeatSocket.writeDatagram(datagram, QHostAddress(server_control_ip), server_control_port) 
        logger.log(logging.INFO, 'Run Stop requested.', extra=extra)  

    def load_config_file(self):
        try:
            with open(self.config_file, 'r') as file:
                self.config_data = json.load(file)
            self.obs_params_save_path_line.setText(self.config_data["dataSavePath"])
        except Exception as e:
            QtWidgets.QMessageBox.critical(None, "Error", f"Failed to load config file: {e}")
            logger.log(logging.ERROR, f"Failed to load config file: {e}")

    def startRun(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        if self.state_data is None:
            logger.log(logging.ERROR, "Cannot start: no state file loaded.", extra=extra)
            return

        run_id = self.reserve_run_id()
        if run_id is None:
            try:
                run_id = int(self.VO_db_params['run_id'])
            except ValueError:
                logger.log(logging.ERROR, "Cannot start: no run ID, and none could be reserved from the DB.", extra=extra)
                return
            logger.log(logging.WARNING, f"Using the previewed run ID {run_id}; check the DB row matches the .bin files.", extra=extra)
        self.VO_db_params_runid_line.setText(str(run_id))
        self.last_used_run_id = run_id

        if not self.request_listen():
            self.read_last_run_id()
            return
        logger.log(logging.INFO, f'Run {run_id} start requested.', extra=extra)

        # Lock straight away rather than on the server's "started", so a
        # second click cannot send a second start; release after 5 s if the
        # server never confirms.
        self.run_active = True
        self.run_confirmed = False
        self.start_confirm_timer.start(5000)
        self.set_gui_components_enabled(False)
        self.refresh_start_button()

    def stopRun(self):
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        logger.log(logging.INFO, 'Run Stop requested.', extra=extra)       
