#!/usr/bin/env python3
"""Build the star catalog used by the GUI's field-of-view overlay.

Run manually, not at GUI startup: the output is committed so the control room
never needs network. Re-run it only to refresh the catalog.

    cd scripts
    python build_star_catalog.py --out ../gui/catalogs/hipparcos.tsv.gz

Sources, joined on catalog numbers only -- no coordinate matching, so a join is
either right or absent:

  I/239/hip_main  base: HIP, RA, Dec, Vmag, HD              (VizieR, 118,218 rows)
  V/50/catalog    Bright Star Cat: HD -> HR, SAO, Name      (VizieR, 9,110 rows)
  I/131A/sao      SAO catalog: HD -> SAO                    (VizieR, 258,998 rows)
  IAU-CSN         HIP -> proper name, Bayer, constellation  (IAU WGSN, 451 names)

IV/27A was evaluated as a source of pre-split Flamsteed/Bayer/constellation
fields and dropped: it holds only 3,526 rows, and clean_bayer_flamsteed()
reproduces its values for 3,142 of 3,142 overlapping stars (100%), so parsing
the BSC Name string directly covers strictly more stars with no loss.

Most stars have no proper name and no Bayer designation; HD and HIP are the
universal fallbacks. The coverage report printed at the end is the check that
this is still true; a shortfall aborts the write unless --force is given.
"""

import argparse
import gzip
import io
import os
import re
import sys
import urllib.request

import numpy as np
import pandas as pd

VIZIER = 'https://vizier.cds.unistra.fr/viz-bin/asu-tsv'
IAU_CSN_URL = 'https://www.pas.rochester.edu/~emamajek/WGSN/IAU-CSN.txt'

COLUMNS = ['hip', 'ra_deg', 'dec_deg', 'vmag', 'hd', 'hr', 'sao',
           'bayer_flamsteed', 'constellation', 'proper_name']

# Expected coverage, from the build that this script was written against.
# A large shortfall means an upstream schema or join key changed.
EXPECTED_COVERAGE = {
    'hip': 118218, 'vmag': 118216, 'hd': 100000,
    'hr': 8500, 'sao': 90000, 'bayer_flamsteed': 3000, 'proper_name': 400,   # 451 IAU names, 411 of them carry a HIP
}

# Bayer codes -> spelled-out Greek. The two source catalogs disagree on
# spelling, so both are mapped: the BSC Name field uses Alp/The/Xi/Mu, while
# IAU-CSN uses alf/tet/ksi/mu. -- verified against the 24 distinct prefixes
# actually present in V/50 (Alp 93, Gam 92, Zet 91, ... Chi 37).
GREEK = {
    # BSC spellings
    'alp': 'alpha', 'bet': 'beta', 'gam': 'gamma', 'del': 'delta',
    'eps': 'epsilon', 'zet': 'zeta', 'eta': 'eta', 'the': 'theta',
    'iot': 'iota', 'kap': 'kappa', 'lam': 'lambda', 'mu': 'mu',
    'nu': 'nu', 'xi': 'xi', 'omi': 'omicron', 'pi': 'pi',
    'rho': 'rho', 'sig': 'sigma', 'tau': 'tau', 'ups': 'upsilon',
    'phi': 'phi', 'chi': 'chi', 'psi': 'psi', 'ome': 'omega',
    # IAU-CSN spellings that differ
    'alf': 'alpha', 'tet': 'theta', 'ksi': 'xi', 'mu.': 'mu',
    'nu.': 'nu', 'pi.': 'pi',
}

# BSC Name prefixes that look like Bayer codes but are not Greek.
NOT_GREEK = {'nov', 'ngc'}

# The numeric tail of an IAU-CSN row: mag, band, HIP, HD, RA, Dec, date.
# Anchored on the ISO date, which nothing else in the row looks like.
# '_' marks a missing value in this file.
CSN_TAIL = re.compile(
    r'\s(?P<mag>-?\d+\.\d+|_)\s+(?P<bnd>[A-Za-z_]+)\s+(?P<hip>\d+|_)\s+(?P<hd>\d+|_)\s+'
    r'(?P<ra>-?\d+\.\d+|_)\s+(?P<dec>[-+]?\d+\.\d+|_)\s+(?P<date>\d{4}-\d{2}-\d{2})'
)


def fetch(url, timeout=300):
    print(f'  GET {url[:110]}{"..." if len(url) > 110 else ""}', flush=True)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def vizier_tsv(source, columns, extra=''):
    """Fetch a VizieR table as a DataFrame.

    The TSV has a units row and a dashes row under the header, and comment
    lines throughout; both are stripped here.
    """
    url = f'{VIZIER}?-source={source}&-out.max=unlimited&-out={",".join(columns)}{extra}'
    text = fetch(url)

    rows = [ln for ln in text.splitlines() if ln and not ln.startswith('#')]
    try:
        head = next(i for i, ln in enumerate(rows) if ln.split('\t')[0].strip() == columns[0])
    except StopIteration:
        raise RuntimeError(f'{source}: no header row containing {columns[0]!r}')

    # header, then a units line, then a line of dashes
    body = [ln for ln in rows[head + 1:] if not set(ln.replace('\t', '')) <= set('- ')]
    body = [ln for ln in body if ln.split('\t')[0].strip() != columns[0]]
    if body and set(body[0].replace('\t', '').strip()) <= set('mag deg'):
        body = body[1:]

    df = pd.read_csv(io.StringIO('\n'.join([rows[head]] + body)), sep='\t',
                     dtype=str, keep_default_na=False, engine='python')
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    df = df[df[columns[0]] != '']
    print(f'    -> {len(df):,} rows')
    return df


def to_num(series, dtype=float):
    return pd.to_numeric(series.replace('', np.nan), errors='coerce').astype(dtype)


def fetch_hipparcos():
    print('Hipparcos I/239/hip_main (base catalog)')
    df = vizier_tsv('I/239/hip_main', ['HIP', 'RAICRS', 'DEICRS', 'Vmag', 'HD'])
    out = pd.DataFrame({
        'hip': to_num(df['HIP'], 'Int64'),
        'ra_deg': to_num(df['RAICRS']),
        'dec_deg': to_num(df['DEICRS']),
        'vmag': to_num(df['Vmag']),
        'hd': to_num(df['HD'], 'Int64'),
    })
    # A star with no position cannot be drawn.
    return out.dropna(subset=['ra_deg', 'dec_deg']).reset_index(drop=True)


def fetch_bsc():
    print('Bright Star Catalogue V/50 (HD -> HR, SAO, Bayer/Flamsteed)')
    df = vizier_tsv('V/50/catalog', ['HR', 'HD', 'SAO', 'Name'])
    out = pd.DataFrame({
        'hd': to_num(df['HD'], 'Int64'),
        'hr': to_num(df['HR'], 'Int64'),
        'sao_bsc': to_num(df['SAO'], 'Int64'),
        'bsc_name': df['Name'].str.strip(),
    }).dropna(subset=['hd'])
    return out.drop_duplicates(subset=['hd'], keep='first')


def fetch_sao():
    print('SAO catalog I/131A/sao (HD -> SAO)')
    df = vizier_tsv('I/131A/sao', ['SAO', 'HD'])
    out = pd.DataFrame({
        'hd': to_num(df['HD'], 'Int64'),
        'sao_cat': to_num(df['SAO'], 'Int64'),
    }).dropna(subset=['hd'])
    return out.drop_duplicates(subset=['hd'], keep='first')


def parse_iau_csn(text):
    """Parse the IAU Catalog of Star Names into HIP -> name/Bayer/constellation.

    The file is **fixed-width**, not whitespace-delimited: 'Designation' holds
    values like 'HR 897' and names like 'Polaris Australis' contain spaces, so
    splitting on whitespace mis-assigns columns. Column offsets are derived
    from the file's own header line, whose leading '#' occupies the first
    character of the name field and so stays aligned with the data.

    '_' means 'no value' in this file.
    """
    lines = text.splitlines()

    header = next((ln for ln in lines
                   if ln.startswith('#Name/ASCII') and 'HIP' in ln), None)
    if header is None:
        raise RuntimeError('IAU-CSN: could not find the #Name/ASCII header line')

    # Start offset of every column, taken from the header.
    starts, names = [], []
    for m in re.finditer(r'\S+', header):
        starts.append(m.start())
        names.append(m.group())
    # 'ID' appears twice -- ASCII Bayer ('tet01') then diacritic ('θ1').
    # Keep the first occurrence of each name so 'ID' means the ASCII one.
    bounds = {}
    for i, key in enumerate(names):
        if key not in bounds:
            end = starts[i + 1] if i + 1 < len(starts) else len(header) + 200
            bounds[key] = (starts[i], end)

    def field(line, key):
        lo, hi = bounds[key]
        return line[lo:hi].strip()

    records, skipped = [], 0
    for line in lines:
        if not line.strip() or line.startswith('#') or line.startswith('$'):
            continue

        # The numeric tail is matched by regex, not by column: header labels
        # are left-aligned but the numbers under them are right-aligned, so
        # the HIP slice taken from the header offset straddles two fields.
        m = CSN_TAIL.search(line)
        if m is None:
            skipped += 1
            continue

        hip = m.group('hip')
        bayer, con = field(line, 'ID'), field(line, 'Con')
        records.append({
            'hip': int(hip) if hip.isdigit() else pd.NA,
            'proper_name': field(line, '#Name/ASCII'),
            'csn_bayer': '' if bayer == '_' else bayer,
            'constellation': '' if con == '_' else con,
        })

    df = pd.DataFrame.from_records(records)
    df['hip'] = df['hip'].astype('Int64')

    n_hip = int(df['hip'].notna().sum())
    print(f'    -> {len(df):,} named stars ({n_hip:,} with a HIP number, {skipped} unparsed)')
    if n_hip < 0.8 * len(df):
        raise RuntimeError(
            f'IAU-CSN: only {n_hip} of {len(df)} rows yielded a HIP number -- '
            'the fixed-width layout has probably changed')
    return df


def fetch_iau_names():
    print('IAU Catalog of Star Names (HIP -> proper name)')
    return parse_iau_csn(fetch(IAU_CSN_URL, timeout=120))


_BSC_BODY = re.compile(r'^(?P<flam>\d+)?\s*(?P<bayer>[A-Za-z]{2,4}?)?\.?(?P<sup>\d+)?$')


def _greek(code, sup):
    """'Alp','' -> 'alpha';  'Bet','1' -> 'beta1'.  None if not a Greek code."""
    name = GREEK.get(code.lower().rstrip('.'))
    if name is None:
        return None
    return f'{name}{sup.lstrip("0")}' if sup else name


def clean_bayer_flamsteed(bsc_name, csn_bayer, constellation):
    """Normalise a BSC Name field into a readable designation.

    BSC packs Flamsteed number, Bayer code and constellation into ten fixed
    columns: '33    Psc', '9Alp CMa', '7Zet2CrB', 'Bet1Tuc'. The Bayer form is
    preferred when present ('alpha UMi'), since that is how these stars are
    normally written and searched for; otherwise the Flamsteed form is used
    ('33 Psc'). The IAU file supplies a cleaner Bayer code where it has one.
    """
    name = (bsc_name or '').strip()
    con = (constellation or '').strip()

    if csn_bayer:
        code = csn_bayer.rstrip('0123456789')
        sup = csn_bayer[len(code):]
        greek = _greek(code, sup)
        if greek:
            return f'{greek} {con}'.strip()

    if not name:
        return ''

    # The trailing three characters of a BSC name are the constellation.
    body, bsc_con = name[:-3].strip(), name[-3:].strip()
    con = con or bsc_con

    m = _BSC_BODY.match(body)
    if not m:
        return f'{body} {con}'.strip()

    flam = m.group('flam') or ''
    bayer = m.group('bayer') or ''
    sup = m.group('sup') or ''

    if bayer and bayer.lower() not in NOT_GREEK:
        greek = _greek(bayer, sup)
        if greek:
            return f'{greek} {con}'.strip()
        return f'{bayer}{sup} {con}'.strip()

    if bayer:                                  # NOVA, NGC and friends
        return f'{bayer}{sup} {con}'.strip()

    return f'{flam} {con}'.strip() if flam else con


def build():
    hip = fetch_hipparcos()
    bsc = fetch_bsc()
    sao = fetch_sao()
    csn = fetch_iau_names()

    print('\nJoining...')
    df = hip.merge(bsc, on='hd', how='left')
    df = df.merge(sao, on='hd', how='left')
    # BSC's SAO where present, otherwise the SAO catalog's own cross-ID.
    df['sao'] = df['sao_bsc'].fillna(df['sao_cat']).astype('Int64')

    csn_by_hip = csn.dropna(subset=['hip']).drop_duplicates(subset=['hip'], keep='first')
    df = df.merge(csn_by_hip[['hip', 'proper_name', 'csn_bayer', 'constellation']],
                  on='hip', how='left')

    for col in ('bsc_name', 'proper_name', 'csn_bayer', 'constellation'):
        df[col] = df[col].fillna('')

    df['bayer_flamsteed'] = [
        clean_bayer_flamsteed(n, b, c)
        for n, b, c in zip(df['bsc_name'], df['csn_bayer'], df['constellation'])
    ]

    df = df.sort_values('vmag', na_position='last').reset_index(drop=True)
    return df[COLUMNS]


def coverage(df):
    return {c: int(df[c].notna().sum()) if df[c].dtype.kind in 'if' or str(df[c].dtype) == 'Int64'
            else int((df[c].astype(str).str.strip() != '').sum())
            for c in COLUMNS if c in EXPECTED_COVERAGE}


def report(df):
    print('\nCoverage')
    print('-' * 56)
    cov = coverage(df)
    shortfalls = []
    for key, expected in EXPECTED_COVERAGE.items():
        got = cov.get(key, 0)
        frac = got / len(df) * 100 if len(df) else 0
        flag = ''
        if got < expected * 0.9:
            flag = f'  <-- EXPECTED >= {expected:,}'
            shortfalls.append(f'{key}: {got:,} < {expected:,}')
        print(f'  {key:<18} {got:>8,}  ({frac:5.1f}%){flag}')

    print(f'\n  total rows          {len(df):>8,}')
    print('\nMagnitude distribution')
    for m in (2, 4, 6, 7, 8, 9, 10):
        print(f'  V < {m:<3}            {int((df["vmag"] < m).sum()):>8,}')

    return shortfalls


def spot_check(df):
    """The three stars whose identifiers are quoted in the docs plan."""
    print('\nSpot check')
    print('-' * 56)
    for hip, expect in ((11767, 'Polaris'), (91262, 'Vega'), (32349, 'Sirius')):
        row = df[df['hip'] == hip]
        if row.empty:
            print(f'  HIP {hip}: MISSING')
            continue
        r = row.iloc[0]
        print(f'  HIP {hip:<7} {r["proper_name"] or "-":<12} {r["bayer_flamsteed"] or "-":<16} '
              f'HD {r["hd"]}  HR {r["hr"]}  V={r["vmag"]}')
        if r['proper_name'] != expect:
            print(f'      WARNING: expected proper name {expect!r}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='../gui/catalogs/hipparcos.tsv.gz',
                    help='output path (gzipped TSV)')
    ap.add_argument('--force', action='store_true',
                    help='write even if coverage falls short of expectations')
    args = ap.parse_args()

    df = build()
    shortfalls = report(df)
    spot_check(df)

    if shortfalls and not args.force:
        print('\nREFUSING TO WRITE: identifier coverage fell short --')
        for s in shortfalls:
            print(f'  {s}')
        print('An upstream schema or join key probably changed. Investigate, or')
        print('pass --force if the drop is genuinely expected.')
        return 1

    with gzip.open(args.out, 'wt', encoding='utf-8', newline='') as f:
        df.to_csv(f, sep='\t', index=False)

    print(f'\nWrote {args.out}  ({os.path.getsize(args.out)/1e6:.2f} MB, {len(df):,} rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
