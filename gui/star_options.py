"""The Star Field Options window.

Logic only; the widget layout lives in ``designer/star_options.ui`` and is
compiled to ``star_options_ui.py`` by ``make``. Edit the .ui and regenerate -- never the
generated module. This mirrors how ``Realtime_GUI.py`` wraps ``GUI.py``.

The window is non-modal so the camera panels update while thresholds are
dragged. It owns no catalog state beyond the magnitudes it needs to draw the
histogram; the settings it emits are applied by ``database_worker``.
"""

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

import star_field
from star_options_ui import Ui_StarOptionsDialog

# Combo entries: (label shown, value stored in the settings dict).
SCHEME_CHOICES = [
    ('Best available', 'best'),
    ('Proper name', 'proper_name'),
    ('Bayer / Flamsteed', 'bayer_flamsteed'),
    ('HR', 'hr'),
    ('HD', 'hd'),
    ('HIP', 'hip'),
    ('SAO', 'sao'),
]

HIST_BIN_WIDTH = 0.25


class StarOptionsDialog(QtWidgets.QDialog, Ui_StarOptionsDialog):
    """Magnitude thresholds and label scheme for the star overlay."""

    settings_changed = QtCore.pyqtSignal(dict)

    def __init__(self, catalog, settings, defaults, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._catalog = catalog
        self._defaults = dict(defaults)
        self._settings = dict(settings)
        self._updating = False          # guards the region <-> spinbox loop

        for text, value in SCHEME_CHOICES:
            self.star_options_scheme_combo.addItem(text, value)

        self._build_histogram()
        self._apply_to_widgets(self._settings)

        self.star_options_mag_min_spin.valueChanged.connect(self._on_spin_changed)
        self.star_options_mag_max_spin.valueChanged.connect(self._on_spin_changed)
        self.star_options_label_mag_spin.valueChanged.connect(self._on_spin_changed)
        self.star_options_scheme_combo.currentIndexChanged.connect(self._on_spin_changed)
        self.star_options_reset_button.clicked.connect(self.reset_to_defaults)
        self.star_options_close_button.clicked.connect(self.close)

    # ------------------------------------------------------------------ setup

    def _build_histogram(self):
        """Magnitude histogram with a draggable range and a label threshold."""
        vmag = self._catalog.vmag
        finite = vmag[np.isfinite(vmag) & (vmag < 30)]

        lo = float(np.floor(finite.min()))
        hi = float(np.ceil(finite.max()))
        edges = np.arange(lo, hi + HIST_BIN_WIDTH, HIST_BIN_WIDTH)
        counts, edges = np.histogram(finite, bins=edges)

        plot = self.star_options_histogram
        plot.setLabel('bottom', 'V magnitude')
        plot.setLabel('left', 'stars per 0.25 mag')
        plot.showGrid(x=True, y=True, alpha=0.3)

        # Faint stars outnumber bright ones by orders of magnitude; on a linear
        # axis the bright end -- the end that matters -- is invisible. The log
        # is taken here rather than with setLogMode because empty bins give
        # log10(0) = -inf, which sends pyqtgraph's autoscaling to 1e173.
        heights = np.log10(np.maximum(counts, 1))
        plot.addItem(pg.BarGraphItem(x0=edges[:-1], x1=edges[1:], height=heights,
                                     brush=pg.mkBrush(110, 140, 200, 180),
                                     pen=pg.mkPen(None)))

        axis = plot.getAxis('left')
        axis.enableAutoSIPrefix(False)
        top = float(np.ceil(heights.max()))
        axis.setTicks([[(v, f'{10 ** v:,.0f}') for v in range(0, int(top) + 1)]])
        plot.setYRange(0, top, padding=0.02)

        self._region = pg.LinearRegionItem(
            values=(self._settings['mag_min'], self._settings['mag_max']),
            brush=pg.mkBrush(255, 200, 80, 45),
            hoverBrush=pg.mkBrush(255, 200, 80, 80),
        )
        self._region.setZValue(10)
        plot.addItem(self._region)

        self._label_line = pg.InfiniteLine(
            pos=self._settings['label_mag_max'], angle=90, movable=True,
            pen=pg.mkPen('r', width=2, style=QtCore.Qt.PenStyle.DashLine),
            label='labels', labelOpts={'position': 0.9, 'color': 'r'},
        )
        self._label_line.setZValue(11)
        plot.addItem(self._label_line)

        plot.setXRange(lo, min(hi, 13.0), padding=0.01)
        plot.setLimits(xMin=lo - 0.5, xMax=hi + 0.5)

        self._region.sigRegionChanged.connect(self._on_region_changed)
        self._label_line.sigPositionChanged.connect(self._on_region_changed)

    # --------------------------------------------------------------- plumbing

    def _apply_to_widgets(self, settings):
        self._updating = True
        try:
            self.star_options_mag_min_spin.setValue(settings['mag_min'])
            self.star_options_mag_max_spin.setValue(settings['mag_max'])
            self.star_options_label_mag_spin.setValue(settings['label_mag_max'])

            index = self.star_options_scheme_combo.findData(settings['label_scheme'])
            self.star_options_scheme_combo.setCurrentIndex(max(index, 0))

            self._region.setRegion((settings['mag_min'], settings['mag_max']))
            self._label_line.setPos(settings['label_mag_max'])
        finally:
            self._updating = False
        self._refresh_readout()

    def _on_region_changed(self):
        if self._updating:
            return
        lo, hi = self._region.getRegion()
        self._commit(lo, hi, self._label_line.value(),
                     self.star_options_scheme_combo.currentData())

    def _on_spin_changed(self):
        if self._updating:
            return
        self._commit(self.star_options_mag_min_spin.value(),
                     self.star_options_mag_max_spin.value(),
                     self.star_options_label_mag_spin.value(),
                     self.star_options_scheme_combo.currentData())

    def _commit(self, mag_min, mag_max, label_mag_max, scheme):
        """Normalise, push back to every widget, then emit."""
        if mag_min > mag_max:
            mag_min, mag_max = mag_max, mag_min

        # Labelling a star that is not drawn is meaningless, so the label
        # threshold is clamped inside the plotted range.
        label_mag_max = min(max(label_mag_max, mag_min), mag_max)

        self._settings = {
            'mag_min': round(float(mag_min), 3),
            'mag_max': round(float(mag_max), 3),
            'label_mag_max': round(float(label_mag_max), 3),
            'label_scheme': scheme or 'best',
        }
        self._apply_to_widgets(self._settings)
        self.settings_changed.emit(dict(self._settings))

    def _refresh_readout(self):
        s = self._settings
        vmag = self._catalog.vmag
        plotted = int(((vmag >= s['mag_min']) & (vmag <= s['mag_max'])).sum())
        labelled = int(((vmag >= s['mag_min']) & (vmag <= s['label_mag_max'])).sum())

        self.star_options_readout_label.setText(
            f"Catalog {len(self._catalog):,} stars   |   "
            f"plotted: {plotted:,} ({plotted / max(len(self._catalog), 1) * 100:.1f}%)   |   "
            f"labelled: {labelled:,}"
        )

    # ------------------------------------------------------------------ public

    def reset_to_defaults(self):
        self._commit(self._defaults['mag_min'], self._defaults['mag_max'],
                     self._defaults['label_mag_max'], self._defaults['label_scheme'])

    def settings(self):
        return dict(self._settings)
