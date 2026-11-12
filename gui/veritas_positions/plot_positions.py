"""Plot the telescope GPS positions on satellite imagery as a visual check.

Reads telescope_positions.txt in this directory, downloads Esri World Imagery
tiles covering the array (cached in ./tile_cache), and writes
telescope_map.png with a labeled dot for each telescope.

Usage: python3 plot_positions.py [--zoom 19] [--margin 60]
"""
import argparse
import io
import math
import os
import urllib.request

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TILE_URL = ('https://server.arcgisonline.com/ArcGIS/rest/services/'
            'World_Imagery/MapServer/tile/{z}/{y}/{x}')
TILE = 256


def load_positions(path):
    tels = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            p = line.split()
            tels.append((p[0], float(p[3]), float(p[4])))
    return tels


def to_pixel(lat, lon, z):
    """Global Web Mercator pixel coordinates at zoom z."""
    n = TILE * 2 ** z
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def get_tile(z, x, y, cache):
    os.makedirs(cache, exist_ok=True)
    fn = os.path.join(cache, f'{z}_{x}_{y}.jpg')
    if not os.path.exists(fn):
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                     headers={'User-Agent': 'python-urllib'})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        with open(fn, 'wb') as f:
            f.write(data)
    return Image.open(fn).convert('RGB')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zoom', type=int, default=19)
    ap.add_argument('--margin', type=float, default=60.0,
                    help='metres of imagery around the telescopes')
    args = ap.parse_args()
    z = args.zoom

    tels = load_positions(os.path.join(HERE, 'telescope_positions.txt'))
    lat0 = sum(t[1] for t in tels) / len(tels)
    m_per_px = 156543.03392 * math.cos(math.radians(lat0)) / 2 ** z
    pad = args.margin / m_per_px

    px = [to_pixel(lat, lon, z) for _, lat, lon in tels]
    x0 = min(p[0] for p in px) - pad
    x1 = max(p[0] for p in px) + pad
    y0 = min(p[1] for p in px) - pad
    y1 = max(p[1] for p in px) + pad

    tx0, tx1 = int(x0 // TILE), int(x1 // TILE)
    ty0, ty1 = int(y0 // TILE), int(y1 // TILE)
    mosaic = Image.new('RGB', ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    cache = os.path.join(HERE, 'tile_cache')
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            mosaic.paste(get_tile(z, tx, ty, cache),
                         ((tx - tx0) * TILE, (ty - ty0) * TILE))
    ox, oy = tx0 * TILE, ty0 * TILE
    crop = mosaic.crop((int(x0 - ox), int(y0 - oy), int(x1 - ox), int(y1 - oy)))

    fig, ax = plt.subplots(figsize=(10, 10 * crop.height / crop.width))
    ax.imshow(crop)
    for (name, lat, lon), (x, y) in zip(tels, px):
        cx, cy = x - x0, y - y0
        ax.plot(cx, cy, 'o', ms=9, mfc='red', mec='white', mew=1.5)
        ax.annotate(name, (cx, cy), xytext=(10, 10), textcoords='offset points',
                    color='yellow', fontsize=16, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.2', fc='black', alpha=0.6))

    # 50 m scale bar, bottom left
    bar = 50.0 / m_per_px
    bx, by = 20, crop.height - 25
    ax.plot([bx, bx + bar], [by, by], color='white', lw=4)
    ax.text(bx + bar / 2, by - 10, '50 m', color='white', ha='center',
            fontsize=12, fontweight='bold')
    ax.annotate('N', xy=(crop.width - 30, 30), xytext=(crop.width - 30, 90),
                color='white', ha='center', fontsize=14, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='white', lw=2))

    ax.set_axis_off()
    ax.set_title('VERITAS telescope GPS positions (Esri World Imagery)')
    out = os.path.join(HERE, 'telescope_map.png')
    fig.savefig(out, dpi=120, bbox_inches='tight')
    print('wrote', out)


if __name__ == '__main__':
    main()
