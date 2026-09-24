"""Star overlay display settings and angle formatting.

A leaf module: both ``veritas_db`` and ``ui_star_overlay`` need these,
so keeping them here avoids an import cycle between those two.
"""

from astropy.coordinates import Angle, SkyCoord, EarthLocation
import json
import logging
from astropy import units as u

from qt_logging import logger
import star_field


# A pointing row older than this is treated as "positioner parked": its alt/az
# is still where the telescope points, but the sky has moved on.
MAX_POINTING_AGE_S = 60.0

# Shutdown bounds for the VERITAS SQL worker. Both are generous enough that a
# healthy teardown never reaches them -- a normal stop takes well under a
# second -- so they change nothing in the working path. They exist only so that
# a wedged worker degrades to a logged warning instead of a frozen GUI.
DB_THREAD_WAIT_MS = 5000
PROCESS_JOIN_TIMEOUT_S = 2.0

# Star overlay display settings, persisted to STAR_DISPLAY_FILE.
# The default plots to V=7 and labels to V=6: measured Hipparcos counts inside
# the 2 deg FOV cut run to 80 stars at full depth near the galactic plane, which
# is far more text than a 3.5 deg camera panel can carry.
STAR_DISPLAY_FILE = 'star_display.json'
DEFAULT_STAR_DISPLAY = {
    'mag_min': -2.0,
    'mag_max': 7.0,
    'label_mag_max': 6.0,
    'label_scheme': 'best',
}

def load_star_display_settings(path=STAR_DISPLAY_FILE):
    """Read persisted overlay settings, falling back to the defaults."""
    settings = dict(DEFAULT_STAR_DISPLAY)
    try:
        with open(path, 'r') as f:
            stored = json.load(f)
    except FileNotFoundError:
        return settings
    except (OSError, ValueError) as e:
        logger.log(logging.WARNING, f"Could not read {path} ({e}); using default star display settings.",
                   extra={'qThreadName': 'MainThread'})
        return settings

    for key in DEFAULT_STAR_DISPLAY:
        if key in stored:
            settings[key] = stored[key]
    if settings['label_scheme'] not in star_field.LABEL_SCHEMES:
        settings['label_scheme'] = DEFAULT_STAR_DISPLAY['label_scheme']
    return settings


def save_star_display_settings(settings, path=STAR_DISPLAY_FILE):
    try:
        with open(path, 'w') as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        logger.log(logging.WARNING, f"Could not save {path} ({e}).",
                   extra={'qThreadName': 'MainThread'})


def format_sexagesimal(angle):
    """Format an Angle as +DDD MM' SS.ss", e.g. +359 59' 21.53".

    This is the shape Stellarium's search window accepts, so the output can be
    pasted straight in.
    """
    return angle.to_string(unit=u.deg, sep=('° ', "' ", '"'),
                           precision=2, alwayssign=True, pad=True)
