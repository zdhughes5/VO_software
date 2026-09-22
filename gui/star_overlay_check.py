#!/usr/bin/env python3
"""Offline checks for the GUI's star overlay geometry.

No Qt, no database. Run from ``gui/`` so the relative paths to
``catalogs/asu2.dat`` and ``trueLocations_VERITAS.dat`` resolve the way they do
for the GUI itself.

    python star_overlay_check.py --verify-reference
    python star_overlay_check.py --self-test
    python star_overlay_check.py --alt 70 --az 120 [--time 2026-09-21T06:00:00]

``--verify-reference`` re-runs the two facts the camera-frame convention rests
on, as assertions. ``--self-test`` checks that field rotation through the zenith
still comes out right. The third form prints what the overlay would draw,
including the nearest pixel number -- that is the column to compare against the
hot pixel when a bright star is in the field.

See docs/2026-09-21-star-overlay-camera-orientation-plan.md.
"""

import argparse
import glob
import os
import re
import sys
from decimal import Decimal

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time

import star_field
from db_worker_process import parse_vdb_timestamp

# Same site as Realtime_GUI.database_worker.
BASECAMP = EarthLocation(lat=31.6716989799*u.deg, lon=-110.951291195*u.deg, height=1268*u.m)

# ref/ is gitignored, so this may legitimately be absent.
PMPIX_GLOB = '../ref/Eventdisplay_AnalysisFiles_VTS-*/DetectorGeometry/EVN_V6_Upgrade_*.txt'

# From PMPIX pixel 2 of telescope 1: 31.40 mm at a 0.150 deg pitch.
DEG_PER_MM = 0.150 / 31.40


def read_pmpix(path, telescope=1):
    """Pixel positions in degrees from an Eventdisplay detector file."""
    pixels = {}
    pattern = re.compile(r'\s*\*?\s*PMPIX\s+(\d+)\s+(\d+)\s+\S+\s+\S+\s+(\S+)\s+(\S+)')

    with open(path, 'r') as f:
        for line in f:
            m = pattern.match(line)
            if m and int(m.group(1)) == telescope:
                pixels[int(m.group(2))] = (
                    float(m.group(3)) * DEG_PER_MM,
                    float(m.group(4)) * DEG_PER_MM,
                )

    return pixels


def verify_pixel_layout():
    """trueLocations_VERITAS.dat must be the Eventdisplay camera frame."""
    matches = sorted(glob.glob(PMPIX_GLOB))
    if not matches:
        print('SKIP  pixel layout vs Eventdisplay: no detector file at')
        print(f'      {PMPIX_GLOB}')
        print('      ref/ is gitignored; the recorded result is a 0.00046 deg max')
        print('      difference over all 499 pixels (see the docs plan).')
        return None

    path = matches[-1]
    ed = read_pmpix(path)
    xs, ys, numbers = star_field.load_pixel_layout()
    layout = {int(n): (float(x), float(y)) for x, y, n in zip(xs, ys, numbers)}

    common = sorted(set(ed) & set(layout))
    assert len(common) == 499, f'expected 499 shared pixels, got {len(common)}'

    diff = np.array([[layout[i][0] - ed[i][0], layout[i][1] - ed[i][1]] for i in common])
    worst = np.abs(diff).max()

    # Guard against an accidental match: the y-flipped variant must be far off.
    flipped = np.array([[layout[i][0] - ed[i][0], layout[i][1] + ed[i][1]] for i in common])
    worst_flipped = np.abs(flipped).max()

    print(f'      reference: {os.path.basename(path)}')
    print(f'      {len(common)} pixels, max difference {worst:.5f} deg '
          f'({worst / 0.15 * 100:.2f}% of pixel pitch)')
    print(f'      y-flipped variant would differ by {worst_flipped:.5f} deg')

    assert worst < 0.001, f'pixel layout disagrees with Eventdisplay by {worst:.5f} deg'
    assert worst_flipped > 1.0, 'y-flip is not distinguishable -- check is meaningless'
    print('PASS  pixel layout is the Eventdisplay camera frame')
    return worst


def verify_camera_transform(n=400, seed=0):
    """altaz_to_camera must equal (+delta_az, -delta_alt) from astropy."""
    rng = np.random.default_rng(seed)
    frame = AltAz(obstime=Time('2026-09-21T06:00:00'), location=BASECAMP)
    worst = 0.0

    for _ in range(n):
        alt, az = rng.uniform(20, 88), rng.uniform(0, 360)
        pointing = SkyCoord(alt=alt*u.deg, az=az*u.deg, frame=frame)

        dalt, daz = rng.uniform(-1.7, 1.7), rng.uniform(-1.7, 1.7)
        star = SkyCoord(
            alt=(alt + dalt)*u.deg,
            az=(az + daz / np.cos(np.radians(alt)))*u.deg,
            frame=frame,
        )

        ref_daz, ref_dalt = pointing.spherical_offsets_to(star)
        x, y = star_field.altaz_to_camera(alt, az, star.alt.degree, star.az.degree)

        worst = max(worst,
                    abs(float(x) - ref_daz.degree),
                    abs(float(y) - star_field.CAMERA_Y_SIGN * ref_dalt.degree))

    print(f'      {n} random pointings, max |port - astropy| = {worst:.3e} deg')
    print(f'      (tangent-plane vs arc-length projection difference, '
          f'{worst / 0.15 * 100:.2f}% of pixel pitch)')

    assert worst < 2e-3, f'camera transform disagrees with astropy by {worst:.3e} deg'
    assert star_field.CAMERA_Y_SIGN == -1.0, 'CAMERA_Y_SIGN must be -1 for the VERITAS camera frame'
    print('PASS  altaz_to_camera matches (+delta_az, -delta_alt)')
    return worst


def verify_timestamp_parsing():
    """VERITAS packed-decimal pointing timestamps must decode to UTC.

    The four sample values are real rows observed from
    tblPositioner_TelescopeN_Status on 2026-09-21.
    """
    from datetime import datetime

    samples = {
        20260922022408512: datetime(2026, 9, 22, 2, 24, 8, 512000),
        20260922025312757: datetime(2026, 9, 22, 2, 53, 12, 757000),
        20260922034802258: datetime(2026, 9, 22, 3, 48, 2, 258000),
        20260922032339514: datetime(2026, 9, 22, 3, 23, 39, 514000),
    }

    for raw, expected in samples.items():
        got = parse_vdb_timestamp(raw)
        assert got == expected, f'{raw} -> {got}, expected {expected}'
        print(f'      {raw} -> {got.isoformat()} UTC')

    # A str or Decimal from the driver must behave the same as an int.
    assert parse_vdb_timestamp('20260922022408512') == samples[20260922022408512]
    assert parse_vdb_timestamp(Decimal('20260922022408512')) == samples[20260922022408512]
    # A real datetime passes through untouched.
    assert parse_vdb_timestamp(samples[20260922022408512]) == samples[20260922022408512]

    # Anything else must raise rather than silently become the wrong time.
    for bad in (None, '', 'not-a-time', 202609220224085, 1758500000, '2026-09-22 02:24:08'):
        try:
            parse_vdb_timestamp(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f'parse_vdb_timestamp({bad!r}) should have raised')

    print('PASS  packed-decimal timestamps decode to UTC; bad input raises')


def self_test():
    """Field rotation through the zenith, without any explicit rotation term.

    A companion star fixed 1 deg due north of a target that transits the zenith
    must cross the camera as the pointing azimuth swings 180 degrees.
    """
    target = SkyCoord(ra=100*u.deg, dec=31.6717*u.deg)     # transits near zenith
    companion = SkyCoord(ra=100*u.deg, dec=32.6717*u.deg)  # 1 deg due north

    times = Time('2026-09-21T00:00:00') + np.arange(0, 1440, 1)*u.min
    alts = target.transform_to(AltAz(obstime=times, location=BASECAMP)).alt.degree
    transit = times[int(np.argmax(alts))]
    print(f'      transit at {transit.iso}, alt {alts.max():.3f} deg')

    rows = []
    for dt in (-60, -20, -5, 5, 20, 60):
        t = transit + dt*u.min
        frame = AltAz(obstime=t, location=BASECAMP)
        p = target.transform_to(frame)
        c = companion.transform_to(frame)
        x, y = star_field.altaz_to_camera(p.alt.degree, p.az.degree, c.alt.degree, c.az.degree)
        rows.append((dt, p.alt.degree, p.az.degree, float(x), float(y)))
        print(f'      dt={dt:+4d} min  alt={p.alt.degree:7.3f}  az={p.az.degree:8.3f}  '
              f'companion x={x:+7.4f} y={y:+7.4f}')

    before = [r for r in rows if r[0] < 0]
    after = [r for r in rows if r[0] > 0]

    assert all(r[3] < -0.9 for r in before), 'companion should sit at x ~ -1 before transit'
    assert all(r[3] > +0.9 for r in after), 'companion should sit at x ~ +1 after transit'
    assert all(abs(r[4]) < 0.15 for r in rows), 'companion should stay near y ~ 0'
    print('PASS  companion crosses the camera through transit (field rotation works)')

    # A star directly above the pointing centre must draw below it, because the
    # camera frame flips the elevation axis. This is the fixed bug, asserted.
    frame = AltAz(obstime=Time('2026-09-21T06:00:00'), location=BASECAMP)
    p = SkyCoord(alt=60*u.deg, az=90*u.deg, frame=frame)
    higher = SkyCoord(alt=61*u.deg, az=90*u.deg, frame=frame)
    x, y = star_field.altaz_to_camera(60.0, 90.0, higher.alt.degree, higher.az.degree)
    print(f'      star 1 deg higher in elevation draws at x={float(x):+.4f} y={float(y):+.4f}')
    assert float(y) < -0.9, 'a star above the pointing centre must draw below it in camera y'
    print('PASS  elevation axis is flipped, as the VERITAS camera frame requires')


def show_field(alt_deg, az_deg, time_iso=None):
    """Print what the overlay would draw for one pointing."""
    obstime = Time(time_iso) if time_iso else Time.now()
    stars, names = star_field.load_star_catalog()
    layout = star_field.load_pixel_layout()

    pointing = SkyCoord(
        alt=alt_deg*u.deg, az=az_deg*u.deg,
        location=BASECAMP, obstime=obstime, frame='altaz',
    )
    labels, xs, ys = star_field.stars_in_fov(stars, names, pointing)

    radec = pointing.transform_to('icrs')
    print(f'Pointing  alt {alt_deg:.3f}  az {az_deg:.3f}   at {obstime.iso} UTC')
    print(f'          RA {radec.ra.degree:.4f}  Dec {radec.dec.degree:+.4f}')
    print(f'Stars within {star_field.FOV_RADIUS_DEG} deg: {len(labels)}')

    if not len(labels):
        return

    order = np.argsort(np.hypot(xs, ys))
    print(f'\n{"star":<22} {"cam x":>8} {"cam y":>8} {"pixel":>6} {"d(pix)":>8}')
    print('-' * 56)
    for i in order:
        pixel, dist = star_field.nearest_pixel(xs[i], ys[i], layout)
        inside = '' if dist < 0.09 else '   (between pixels)'
        print(f'{labels[i]:<22} {xs[i]:+8.3f} {ys[i]:+8.3f} {pixel:>6} {dist:>8.3f}{inside}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--verify-reference', action='store_true',
                    help='check the pixel layout and camera transform against Eventdisplay')
    ap.add_argument('--self-test', action='store_true',
                    help='check field rotation and the elevation flip')
    ap.add_argument('--alt', type=float, help='pointing elevation in degrees')
    ap.add_argument('--az', type=float, help='pointing azimuth in degrees, north through east')
    ap.add_argument('--time', help='UTC ISO time; default now')
    args = ap.parse_args()

    if args.verify_reference:
        verify_pixel_layout()
        verify_camera_transform()
        verify_timestamp_parsing()
        return 0

    if args.self_test:
        self_test()
        return 0

    if args.alt is None or args.az is None:
        ap.error('give --alt and --az, or --verify-reference, or --self-test')

    show_field(args.alt, args.az, args.time)
    return 0


if __name__ == '__main__':
    sys.exit(main())
