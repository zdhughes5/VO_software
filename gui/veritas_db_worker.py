import time
import mysql.connector
from PyQt5 import QtCore

class VeritasDBWorker(QtCore.QObject):
    """
    A worker class to interact with the VERITAS MySQL database.
    It connects to the 'romulus' database and periodically fetches
    run information from the 'tblRun_Info' table.
    """
    finished = QtCore.pyqtSignal()
    status = QtCore.pyqtSignal(str)
    run_info = QtCore.pyqtSignal(str, str, str)  # run_status, run_type, source_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.connection = None
        self.run_status = None
        self.run_type = None
        self.source_id = None

    def start(self):
        """Starts the worker's execution loop."""
        self.active = True
        self.run()

    def stop(self):
        """Stops the worker's execution loop."""
        self.active = False

    def run(self):
        """The main execution loop of the worker."""
        while self.active:
            try:
                if not self.connection or not self.connection.is_connected():
                    self.status.emit("disconnected")
                    # Establish connection to the VERITAS database
                    self.connection = mysql.connector.connect(
                        host="romulus.ucsc.edu",
                        user="readonly",
                        password="",
                        database="VERITAS"
                    )
                    self.status.emit("connected")

                with self.connection.cursor() as cursor:
                    # Fetch the latest run ID
                    cursor.execute("SELECT MAX(run_id) FROM tblRun_Info")
                    latest_run_id = cursor.fetchone()[0]

                    if latest_run_id is not None:
                        # Fetch run information for the latest run
                        cursor.execute(
                            "SELECT run_status, run_type, source_id FROM tblRun_Info WHERE run_id = %s",
                            (latest_run_id,)
                        )
                        result = cursor.fetchone()
                        if result:
                            new_run_status, new_run_type, new_source_id = result
                            # Check if the data has changed before emitting the signal
                            if (new_run_status != self.run_status or
                                new_run_type != self.run_type or
                                new_source_id != self.source_id):
                                self.run_status = new_run_status
                                self.run_type = new_run_type
                                self.source_id = new_source_id
                                self.run_info.emit(self.run_status, self.run_type, self.source_id)

                time.sleep(0.5)

            except mysql.connector.Error as err:
                self.status.emit("disconnected")
                if self.connection and self.connection.is_connected():
                    self.connection.close()
                self.connection = None
                print(f"MySQL Error: {err}")
                time.sleep(5)  # Wait before retrying connection
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                self.active = False

        if self.connection and self.connection.is_connected():
            self.connection.close()
        self.finished.emit()
