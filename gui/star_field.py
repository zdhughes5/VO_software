"""Sky-to-camera geometry for the GUI's star overlay.

Kept free of Qt so the geometry can be exercised headlessly — see
``star_overlay_check.py``, which turns the two facts below into runnable
assertions.

The camera coordinate frame
---------------------------
VERITAS is an alt-azimuth mount with the camera bolted to the optical support
structure and no field derotator, so the camera focal plane *is* the alt/az
tangent plane at the pointing direction. Field rotation needs no explicit term:
it appears on its own as long as each star's alt/az is recomputed every cycle.
(Tracking through the zenith, a companion star fixed 1 deg due north crosses
from x = -1 to x = +1 as the pointing azimuth swings 180 deg.)

What does need care is the sign of y::

    x_cam = +delta_az        y_cam = -delta_alt

That is Eventdisplay's convention, and ``trueLocations_VERITAS.dat`` is
expressed in it. Both halves were verified against the Eventdisplay tree:

1. Every one of the 499 entries in ``trueLocations_VERITAS.dat`` matches the
   telescope-1 ``PMPIX`` records in
   ``Eventdisplay_AnalysisFiles_VTS-490.7.3/DetectorGeometry/EVN_V6_Upgrade_20121127_v420.txt``
   to 0.00046 deg (0.31% of the 0.15 deg pixel pitch); the y-flipped variant is
   off by 3.4 deg. The mm-to-degree conversion carries no sign flip
   (``VCameraRead.cpp:584``, ``:1040``, ``:1043``, with the coordinate
   transformers defaulting to (1., 1.) in ``VEvndispRunParameter.cpp:112``).

2. ``VSkyCoordinatesUtilities::getDifferenceInCameraCoordinates``
   (``VSkyCoordinatesUtilities.cpp:219-252``) takes x along the direction of
   increasing azimuth and y along increasing elevation, then flips y at line
   238. ``altaz_to_camera`` below is a direct port.

Do not change ``CAMERA_Y_SIGN`` without reading
``docs/2026-09-21-star-overlay-camera-orientation-plan.md``. Getting it wrong
mirrors the whole overlay vertically, which is how the original bug presented:
the right stars, in the wrong places.
"""

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord

# Eventdisplay flips the elevation axis when forming camera coordinates
# (VSkyCoordinatesUtilities.cpp:238). This single sign is the whole bug fix.
CAMERA_Y_SIGN = -1.0

# Slightly larger than the camera's 1.725 deg corner radius, so stars just
# outside the outermost pixels still show up at the edge of the display.
FOV_RADIUS_DEG = 2.0

_RAD_TO_DEG = 180.0 / np.pi


def load_star_catalog(path='catalogs/asu2.dat'):
    """Read the star catalog into a SkyCoord plus an array of names.

    Columns are name, RA (deg), Dec (deg), magnitude. Positions are treated as
    ICRS; no proper motion is applied, which is irrelevant at the 0.15 deg
    pixel scale.
    """
    with open(path, 'r') as f:
        lines = [x for x in f if x.strip()]

    names = np.array([x.split()[0] for x in lines])
    ra_deg = np.array([float(x.split()[1]) for x in lines])
    dec_deg = np.array([float(x.split()[2]) for x in lines])

    return SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg), names


def altaz_to_camera(tel_alt_deg, tel_az_deg, star_alt_deg, star_az_deg):
    """Convert alt/az directions to VERITAS camera coordinates, in degrees.

    A port of ``VSkyCoordinatesUtilities::getDifferenceInCameraCoordinates``
    (``VSkyCoordinatesUtilities.cpp:219-252``), vectorized over the stars with
    a scalar pointing. The arithmetic is kept identical to the reference: the
    direction cosines are dotted with the two focal-plane basis vectors and the
    components scaled by 180/pi, which is an orthographic projection rather
    than a gnomonic one. It differs from astropy's ``spherical_offsets_to`` by
    up to 1e-3 deg at the field edge (0.6% of a pixel); matching Eventdisplay
    exactly is worth more here than that difference.

    Returns ``(x_deg, y_deg)`` in the frame of ``trueLocations_VERITAS.dat``.
    """
    tel_az = np.radians(tel_az_deg)
    tel_el = np.radians(tel_alt_deg)
    star_az = np.radians(np.asarray(star_az_deg, dtype=float))
    star_el = np.radians(np.asarray(star_alt_deg, dtype=float))

    # Direction cosines of each star in the ENU basis: East, North, Up.
    cx = np.cos(star_el) * np.sin(star_az)
    cy = np.cos(star_el) * np.cos(star_az)
    cz = np.sin(star_el)

    # Component along the telescope's horizontal pointing direction.
    along_horizon = np.sin(tel_az) * cx + np.cos(tel_az) * cy

    # x basis is d(pointing)/d(az), i.e. increasing azimuth.
    x = (np.cos(tel_az) * cx - np.sin(tel_az) * cy) * _RAD_TO_DEG
    # y basis is increasing elevation, then flipped -- see CAMERA_Y_SIGN.
    y = (-np.sin(tel_el) * along_horizon + np.cos(tel_el) * cz) * _RAD_TO_DEG

    return x, CAMERA_Y_SIGN * y


def stars_in_fov(stars, star_names, pointing_altaz, fov_radius_deg=FOV_RADIUS_DEG):
    """Find catalog stars inside the field of view, in camera coordinates.

    ``pointing_altaz`` is a scalar SkyCoord in an AltAz frame carrying the
    obstime and site location.

    The field-of-view cut is done by transforming the *pointing* into ICRS and
    separating there, rather than transforming all ~9100 catalog stars into
    AltAz. Angular separation is frame-independent, so the selection is
    identical (measured: 0.0 arcsec difference) while costing 0.004 s instead
    of 0.374 s -- which is what makes a separate transform per telescope
    affordable inside the 2.5 s update cycle.

    Returns ``(labels, x_deg, y_deg)``; all three are empty when no star is in
    the field.
    """
    separation = pointing_altaz.transform_to('icrs').separation(stars)
    mask = separation < fov_radius_deg * u.deg

    # Reuse the pointing's own frame so the stars and the pointing cannot end
    # up at different obstimes.
    selected = stars[mask].transform_to(pointing_altaz.frame)

    x, y = altaz_to_camera(
        pointing_altaz.alt.degree, pointing_altaz.az.degree,
        selected.alt.degree, selected.az.degree,
    )

    return star_names[mask], x, y


def load_pixel_layout(path='trueLocations_VERITAS.dat'):
    """Read the camera pixel map: returns ``(x_deg, y_deg, pixel_number)``."""
    with open(path, 'r') as f:
        lines = [x for x in f if x.strip()]

    xs = np.array([float(line.split()[0]) for line in lines])
    ys = np.array([float(line.split()[1]) for line in lines])
    numbers = np.array([int(line.split()[2]) for line in lines])

    return xs, ys, numbers


def nearest_pixel(x_deg, y_deg, layout):
    """Nearest pixel to a camera position: ``(pixel_number, distance_deg)``.

    ``layout`` is the tuple returned by :func:`load_pixel_layout`.
    """
    px, py, numbers = layout
    distances = np.hypot(px - x_deg, py - y_deg)
    i = int(np.argmin(distances))

    return int(numbers[i]), float(distances[i])
