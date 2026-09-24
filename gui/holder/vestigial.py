"""Code that is no longer reachable, kept out of the way.

None of this is referenced anywhere: ``NamedSkyCoord`` is never
instantiated, ``handle_star_field_data`` is never connected to a signal,
and ``test`` is never called. Parked here rather than deleted so it is
recoverable without git archaeology. ``Window`` still inherits
``VestigialMixin`` so its method set is unchanged.
"""

from pyqtgraph.Qt import QtWidgets, QtCore, QtGui
from astropy.coordinates import Angle, SkyCoord, EarthLocation
import logging

from qt_logging import logger

class NamedSkyCoord(SkyCoord):
    def __init__(self, *args, star_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.star_name = star_name

    def __repr__(self):
        base_repr = super().__repr__()
        return f"{base_repr}, star_name={self.star_name}"

    def __str__(self):
        base_str = super().__str__()
        return f"{base_str}, star_name={self.star_name}"

    def __getitem__(self, item):
        sliced_obj = super().__getitem__(item)
        if isinstance(sliced_obj, SkyCoord):
            return NamedSkyCoord(sliced_obj, star_name=self.star_name[item])
        return sliced_obj


class VestigialMixin:
    """Unreachable Window methods. Do not add to this.

    A mixin on Window: it has no state of its own and every ``self``
    here is the Window instance. See docs/2026-09-22-gui-module-split-plan.md.
    """

    def handle_star_field_data(self, star_positions):

        # Handle the new data fetched from the database
        extra = {'qThreadName': QtCore.QThread.currentThread().objectName() }
        print_string = '\n'
        for i, telescope in enumerate(star_positions):
            print_string += f"Telescope {i+1} - Stars in FOV: {len(telescope)}\n"
            for star in telescope:
                print_string += f"Star: {star}\n"
        logger.log(logging.INFO, print_string, extra=extra)

    def test(self):
        print("test")
