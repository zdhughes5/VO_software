"""Qt logging bridge and the GUI log panel.

The shared ``logger`` lives here and every other module imports it from
this one. That matters: the log panel works by attaching ``QLogHandler``
to this exact logger object, so a module that called
``logging.getLogger(__name__)`` instead would still write to debug.log
(appended across sessions) but would silently stop appearing in the operator's log panel.

Every ``logger.log`` call must pass ``extra={'qThreadName': ...}``;
the basicConfig format string references %(qThreadName)s.
"""

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
import logging
import os
import sys
import traceback

fs = '[%(asctime)s %(levelname)s] %(message)s'
formatter = logging.Formatter(fs)

# The persistent log: everything the log panel shows (INFO and up), plus DEBUG
# records and other libraries' warnings, which the panel leaves out.
# Appended, never truncated, so it keeps the history of every session. "w"
# mode also corrupted it: a second GUI truncated the file under the first,
# which kept writing at its old offset and left a hole of NUL bytes.
# Anchored to this directory, not the current one, so it is always gui/debug.log.
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug.log')


class _DefaultThreadName(logging.Filter):
    """Supply qThreadName for records that lack it (other libraries' loggers).

    Without it the format string raises KeyError and the record is lost from
    the file, with only a '--- Logging error ---' on the terminal.
    """
    def filter(self, record):
        if not hasattr(record, 'qThreadName'):
            record.qThreadName = record.threadName
        return True


_file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
_file_handler.addFilter(_DefaultThreadName())
logging.basicConfig(format='[%(asctime)s line %(lineno)d %(qThreadName)s %(levelname)s] %(message)s', handlers=[_file_handler])
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Marks where each session starts. Logged before the panel's handler is
# attached, so it goes to the file only.
logger.log(logging.INFO, f"===== GUI session started (pid {os.getpid()}) =====",
           extra={'qThreadName': 'MainThread'})

class LogSignalEmitter(QtCore.QObject):
    logSignal = QtCore.pyqtSignal(str, logging.LogRecord)


class QLogHandler(logging.Handler):
    def __init__(self, emitter, slotFunc, *args, **kwargs):
        super(QLogHandler, self).__init__(*args, **kwargs)
        self._emitter = emitter
        self._emitter.logSignal.connect(slotFunc)

    @property
    def emitter(self):
        return self._emitter

    def emit(self, record):
        msg = self.format(record)
        self.emitter.logSignal.emit(msg, record)


class LogPanelMixin:
    """The log panel at the bottom right of the main window.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def _setup_log_panel(self):
        """Extracted verbatim from Window.__init__ (lines 430-435 of the pre-split file)."""

        self.logEmitter = LogSignalEmitter()
        self.logHandler = QLogHandler(self.logEmitter, self.updateLog)
        self.logHandler.setFormatter(formatter)
        logger.addHandler(self.logHandler)
        self.logHandler.setLevel('INFO')

    def updateLog(self, status, record):
        color = self.COLORS.get(record.levelno, 'black')
        s = '<pre><font color="%s">%s</font></pre>' % (color, status)
        self.log_edit.appendHtml(s)


def install_exception_logger():
    """Also send unhandled exceptions to the log panel, not only the terminal.

    Chains onto whatever hook is installed. Importing pyqtgraph.Qt already
    replaced PyQt's default abort-on-exception with a hook that prints and
    carries on, so a failing slot does not kill the GUI -- but its traceback
    only reached a terminal the operator may not be watching.
    """
    previous_hook = sys.excepthook

    def log_and_chain(exc_type, exc_value, exc_traceback):
        try:
            extra = {'qThreadName': QtCore.QThread.currentThread().objectName()}
            text = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            logger.log(logging.ERROR, f"Unhandled exception:\n{text}", extra=extra)
        except Exception:
            pass  # Never let the logging itself hide the original error.
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_and_chain
