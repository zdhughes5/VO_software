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

import os

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


# Identifier used for a star's on-camera label. 'best' walks the list below and
# takes the first the star actually has; any other value pins one scheme, and a
# star lacking it gets no label -- which is the point of pinning one.
LABEL_SCHEMES = ('best', 'proper_name', 'bayer_flamsteed', 'hr', 'hd', 'hip', 'sao')

# Order for 'best': most recognisable first, falling back to the machine IDs
# that essentially every star has.
LABEL_PRIORITY = ('proper_name', 'bayer_flamsteed', 'hr', 'hd', 'hip', 'sao')

# Printed in front of the bare catalog numbers.
ID_PREFIX = {'hr': 'HR', 'hd': 'HD', 'hip': 'HIP', 'sao': 'SAO'}

DEFAULT_CATALOG = 'catalogs/hipparcos.tsv.gz'
LEGACY_CATALOG = 'catalogs/asu2.dat'


class StarCatalog:
    """Star positions, magnitudes and identifiers.

    ``ids`` maps an identifier name to a per-star array. Numeric identifiers
    hold ``-1`` where absent, string identifiers hold ``''``; both mean 'this
    star has no such designation', which is the common case for everything
    except HD and HIP.
    """

    def __init__(self, coords, vmag, ids):
        self.coords = coords
        self.vmag = np.asarray(vmag, dtype=float)
        self.ids = ids

    def __len__(self):
        return len(self.vmag)

    def label(self, i, scheme='best'):
        """Label for star ``i``; '' when it has nothing under ``scheme``."""
        keys = LABEL_PRIORITY if scheme == 'best' else (scheme,)
        for key in keys:
            values = self.ids.get(key)
            if values is None:
                continue
            value = values[i]
            if key in ID_PREFIX:
                if int(value) >= 0:
                    return f'{ID_PREFIX[key]} {int(value)}'
            elif str(value).strip():
                return str(value).strip()
        return ''

    def describe(self, i):
        """Every identifier this star has, for tooltips and the log dump."""
        parts = []
        for key in LABEL_PRIORITY:
            values = self.ids.get(key)
            if values is None:
                continue
            value = values[i]
            if key in ID_PREFIX:
                if int(value) >= 0:
                    parts.append(f'{ID_PREFIX[key]} {int(value)}')
            elif str(value).strip():
                parts.append(str(value).strip())
        return ' | '.join(parts) if parts else '(unidentified)'

    def subset(self, mask):
        return StarCatalog(self.coords[mask], self.vmag[mask],
                           {k: v[mask] for k, v in self.ids.items()})


def load_star_catalog(path=None):
    """Load the star catalog, preferring the enriched Hipparcos file.

    The legacy 4-column ``asu2.dat`` (name, RA, Dec, mag) is still read if the
    enriched catalog is missing, so the GUI keeps working on a checkout that
    has not run ``scripts/build_star_catalog.py``.
    """
    if path is None:
        path = DEFAULT_CATALOG if os.path.exists(DEFAULT_CATALOG) else LEGACY_CATALOG

    if str(path).endswith(('.tsv', '.tsv.gz')):
        return _load_enriched(path)
    return _load_legacy(path)


def _load_enriched(path):
    import pandas as pd

    df = pd.read_csv(path, sep='\t', dtype=str, keep_default_na=False)

    def nums(col):
        return pd.to_numeric(df[col], errors='coerce').fillna(-1).astype(np.int64).to_numpy()

    ra = pd.to_numeric(df['ra_deg'], errors='coerce').to_numpy()
    dec = pd.to_numeric(df['dec_deg'], errors='coerce').to_numpy()
    vmag = pd.to_numeric(df['vmag'], errors='coerce').to_numpy()

    ids = {
        'proper_name': df['proper_name'].to_numpy(dtype=object),
        'bayer_flamsteed': df['bayer_flamsteed'].to_numpy(dtype=object),
        'constellation': df['constellation'].to_numpy(dtype=object),
        'hr': nums('hr'), 'hd': nums('hd'), 'hip': nums('hip'), 'sao': nums('sao'),
    }

    # A star with no magnitude cannot be placed on either side of a threshold;
    # treat it as faint rather than dropping it silently.
    vmag = np.where(np.isfinite(vmag), vmag, 99.0)

    return StarCatalog(SkyCoord(ra=ra * u.deg, dec=dec * u.deg), vmag, ids)


def _load_legacy(path):
    with open(path, 'r') as f:
        lines = [x for x in f if x.strip()]

    names = np.array([x.split()[0] for x in lines], dtype=object)
    ra_deg = np.array([float(x.split()[1]) for x in lines])
    dec_deg = np.array([float(x.split()[2]) for x in lines])
    vmag = np.array([float(x.split()[3]) if len(x.split()) > 3 else 99.0 for x in lines])

    empty_num = np.full(len(names), -1, dtype=np.int64)
    ids = {
        'proper_name': np.full(len(names), '', dtype=object),
        'bayer_flamsteed': names,
        'constellation': np.full(len(names), '', dtype=object),
        'hr': empty_num, 'hd': empty_num.copy(),
        'hip': empty_num.copy(), 'sao': empty_num.copy(),
    }
    return StarCatalog(SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg), vmag, ids)


def filter_by_magnitude(catalog, mag_min=-2.0, mag_max=99.0):
    """Stars with mag_min <= Vmag <= mag_max."""
    mask = (catalog.vmag >= mag_min) & (catalog.vmag <= mag_max)
    return catalog.subset(mask)


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


def stars_in_fov(catalog, pointing_altaz, fov_radius_deg=FOV_RADIUS_DEG,
                 mag_min=-2.0, mag_max=99.0, label_mag_max=None,
                 label_scheme='best'):
    """Find catalog stars inside the field of view, in camera coordinates.

    ``catalog`` is a :class:`StarCatalog`; ``pointing_altaz`` is a scalar
    SkyCoord in an AltAz frame carrying the obstime and site location.

    The field-of-view cut is done by transforming the *pointing* into ICRS and
    separating there, rather than transforming every catalog star into AltAz.
    Angular separation is frame-independent, so the selection is identical
    (measured: 0.0 arcsec difference) while costing 0.004 s instead of 0.374 s
    at BSC depth -- which is what makes a separate transform per telescope
    affordable inside the 2.5 s update cycle.

    ``mag_min``/``mag_max`` bound which stars get a marker; ``label_mag_max``
    bounds which of those also get text, and defaults to ``mag_max`` (label
    everything drawn). Stars outside it get an empty label, so a dense field
    can show every marker without turning into a wall of text.

    Returns ``(labels, x_deg, y_deg, vmag, descriptions)``, all empty when no
    star is in the field.
    """
    if label_mag_max is None:
        label_mag_max = mag_max

    in_mag = (catalog.vmag >= mag_min) & (catalog.vmag <= mag_max)

    separation = pointing_altaz.transform_to('icrs').separation(catalog.coords)
    mask = in_mag & (separation < fov_radius_deg * u.deg)
    (indices,) = np.nonzero(mask)

    # Reuse the pointing's own frame so the stars and the pointing cannot end
    # up at different obstimes.
    selected = catalog.coords[mask].transform_to(pointing_altaz.frame)

    x, y = altaz_to_camera(
        pointing_altaz.alt.degree, pointing_altaz.az.degree,
        selected.alt.degree, selected.az.degree,
    )

    vmag = catalog.vmag[mask]
    labels = np.array(
        [catalog.label(i, label_scheme) if m <= label_mag_max else ''
         for i, m in zip(indices, vmag)],
        dtype=object,
    )
    descriptions = np.array([catalog.describe(i) for i in indices], dtype=object)

    return labels, x, y, vmag, descriptions


def marker_sizes(vmag, brightest=0.0, faintest=9.0, size_max=22.0, size_min=7.0):
    """Marker size in pixels, scaled so brighter stars draw larger.

    At Hipparcos depth an unsized field is a wall of identical markers, and the
    operator's question is which of them is the bright one.
    """
    v = np.clip(np.asarray(vmag, dtype=float), brightest, faintest)
    frac = (v - brightest) / max(faintest - brightest, 1e-9)
    return size_max - frac * (size_max - size_min)


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
