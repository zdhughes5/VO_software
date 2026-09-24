# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Data acquisition and monitoring software for the VERITAS optical (VO) intensity-
interferometry setup. FADC boards in the VERITAS telescope crates compute pedestal
variances per PMT channel; "harvester" boards stream those variances over UDP; a Go
server records them to disk and forwards a subsampled stream to a PyQt6 control GUI
that draws four live camera displays. Offline Python scripts re-read the recorded
`.bin` files.

Four largely independent subsystems in one repo:

| Dir | Language | Role |
|---|---|---|
| `server/` | Go 1.21 | UDP DAQ server + `send_command` test/CLI client |
| `gui/` | Python 3.13 / PyQt6 | Operator GUI; launches and controls the server |
| `scripts/` | Python | Offline analysis of recorded `.bin` run files |
| `fadc/` | C | FADC crate library and `set_variance` utility (runs on the VME machine, not here) |

## Required: record every plan and its outcome in `docs/`

Any implementation work that is planned before being carried out — plan mode, an
approved multi-step plan, a task executed from a written plan — **must** leave two
files in [docs/](docs/):

```
docs/YYYY-MM-DD-<slug>-plan.md       saved BEFORE the first implementation edit
docs/YYYY-MM-DD-<slug>-summary.md    saved AFTER execution finishes
```

Both files share one kebab-case `<slug>`; append `-2` if a slug repeats on a date.
Commit them along with the work. [docs/README.md](docs/README.md) specifies what each
file contains.

Two rules that make these worth referencing later:

- Save the plan file **before** editing code, not reconstructed afterwards. A plan
  written after the fact records what happened, not what was intended, and loses the
  assumptions that are the reason to keep it.
- The summary must record deviations, skipped work and real verification output. A
  summary that only reports success is not worth keeping.

This applies to planned implementation work. Answering a question, a one-line fix, or
exploratory reading does not need a plan pair.

## Git workflow

**Work on `master`.** As of 2026-09-21 `master` is the working branch and holds the
current code. Earlier practice was to cut a new branch per change, which left ~20
branches and two diverged lineages; do not continue that pattern.

History worth knowing, because the branch names are misleading:

- `master` was fast-forwarded to the tip of the `before_march_trip` lineage (`abb2f8b`).
  That lineage is the one to build on.
- A separate **`baseline` lineage** (`origin/baseline`, tip `8cb60c4`) diverged during
  field testing and was abandoned mid-trip. It contains 11 commits of real work not in
  `master` — automated data-taking, `file clean-up`, `config changes`, `can connect`,
  `firstflip fix and catch disconnection error`. **It is kept deliberately for mining
  later.** Do not delete it, and do not merge it wholesale.
- `before_testTest` and `trip_2025` both point at the dead-end commit `bcbd173`.
  `origin/master` still sits at the old `8941a46` until someone pushes.

## Commands

```bash
# Go server — builds bin/server and bin/send_command
cd server && make            # make clean to remove bin/

# Run the server. CWD MUST be server/bin: it opens ../internal/server.json
# and ../log/server.log by relative path.
cd server/bin && ./server

# Drive the server without the GUI
cd server/bin && ./send_command listen <duration_s> <runID> <sendInterval> <dataSaveDir>
cd server/bin && ./send_command generate <maxPackets> <packetInterval_us>   # fake harvesters
cd server/bin && ./send_command scan <maxPackets> <start_us> <stop_us> <step_us> <dataSaveDir>

# GUI — CWD MUST be gui/: it loads Genetive.qss, catalogs/asu2.dat,
# trueLocations_VERITAS.dat, ../server/internal/server.json and
# ../server/internal/fadc.json by relative path.
conda activate optical9
cd gui && python Realtime_GUI.py

# Offline analysis — run from scripts/, they import utility_functions as a sibling
cd scripts
python dump_events.py <file.bin>                       # hex dump of parsed events
python check_integrity.py <file.bin> [channel]         # event-number / timestamp gaps
python process_to_fits.py <in.bin> <out.fits> [max_events] [--incremental] [--batch-size N]
python break_finder.py <file.bin> break_finder.yaml    # find step discontinuities
python fit_gaussian.py <file.bin> [channel] guesses.yaml
python passthrough_test.py <file.bin> <channel>        # 588-byte passthrough format
python root_converter.py --help                        # needs PyROOT, not in the conda env

# FADC (only on the VME crate host; needs libvme headers)
cd fadc/libfadc && make && make install
cd fadc/src && make           # builds set_variance, symlinks into fadc/bin
```

There is no test suite, linter config, or CI. `server/test/` is an empty placeholder.

## Python environment

The live env is conda `optical9` (Python 3.13). Four overlapping dependency files
exist — they are not interchangeable:

| File | Format | Use |
|---|---|---|
| `requirements.txt` | pip, pinned (`astroplan==0.10.1`) | what `create_conda_env.sh` parses — it splits on `==`, so **do not replace this with a conda name-list** |
| `enviroment.yml` | conda env YAML, `name: optical9` | `conda env create -f enviroment.yml` |
| `enviroment.txt` | conda `@EXPLICIT` URL list | exact rebuild of optical9 |
| `conda_packages.txt` | conda name-only list | informational only |
| `gui/holder/requirements.txt` | pip, pinned | **stale and conflicting** — pins `astropy==4.2.1`, `numpy==1.20.1`, `PyQt5`. Moved out of `gui/` on 2026-09-23; use the root file. |

`root_converter.py` needs PyROOT, which is not in `optical9`.

## Wire format 1: the 308-byte variance packet

The normal DAQ packet. Defined twice — in Go (`server/pkg/data_parsing/data_parsing.go`)
and in Python (`scripts/utility_functions.py:parse_data_from_event`) — so any format
change must be made in both.

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | event number |
| 4 | 4 | UNIX timestamp seconds |
| 8 | 4 | UNIX timestamp nanoseconds |
| 12 | 6 | extra registers 1–3 (uint16 each) |
| 18 | 2 | window size (top 3 bits) + high 6 bits of channel mask |
| 20 | 8 | low 64 bits of channel mask (mask is 70 bits total) |
| 28 | 280 | 70 variance words, 4 bytes each |

Variance words are **16.16 fixed point, big-endian**: `integer = word >> 16`,
fraction = sum of set bits of the low 16. `ConvertToDecimal` (Go) and
`convert_to_decimal` (Python) are the same function.

Endianness gotcha: the Python parsers read every field big-endian, but the Go server
reads the event number **little-endian** (`extractEventNumber(buf, true)` in
`server.go`), and `send_command generate` writes its synthetic event numbers
little-endian to match. The server only uses that value for the `% sendInterval`
subsampling decision, so a mismatch degrades GUI sampling rather than the recorded
data — but do not assume the two parsers agree.

## Wire format 2: the 588-byte passthrough packet

`scripts/passthrough_test.py` handles a second, distinct format used when the FADC is
in passthrough mode: the **raw accumulators** instead of a precomputed variance.
Same 28-byte header as above, then 70 channels × 8 bytes (= 560), total 588.

Each channel's two big-endian dwords are bit-packed:

- `sum` (27 bits) = `dword1[31:16]` as the high 16 bits, `dword1[15:5]` as the low 11
- `sum_sq` (35 bits) = `dword1[2:0]` as the high 3 bits, all of `dword2` as the low 32

Variance is then computed in software as `(sum_sq / N) - (sum / N)**2` with
`N = WINDOW_SIZE = 499968` samples — which is the point of the format: it lets you check
the FADC's own on-board variance against one you derive yourself. This format is
**not** understood by `utility_functions.py` or by the Go server — passthrough files are
analysed only by `passthrough_test.py`.

## Channel → pixel mapping

A telescope has 8 harvesters × 70 channels = 560 slots, but only 500 are real PMTs;
60 are gaps. `ExtractRelevantPixels` copies `[0:130] [140:260] [280:410] [420:540]`
out of the padded 560-array into a dense 500-array. The harvester→slot ranges come
from `channel` in the state file; `pixelIndex` is the corresponding dense range.

The datagram the server sends to the GUI is **8000 bytes = 4 telescopes × 500
float32**, little-endian, telescope *n* at byte offset `(n-1)*2000`
(`GetTelescopeSendByteOffset`). The GUI slices it as `[:499] [500:999] [1000:1499]
[1500:1999]` ([ui_camera.py:158](gui/ui_camera.py#L158)) — each slice drops its
last pixel, so pixels 499/999/1499/1999 are never displayed.

## Server architecture (`server/cmd/server/server.go`)

Single UDP control socket (`serverControlConnIP`) consumes JSON commands in a
`for` loop forever; command numbers come from `server.json`, not from the Go `const`
block (that enum is stale and unused by the dispatch). On `startRunCmd` the request
carries the **entire state.json as a JSON string**, which becomes the server's
`globalState` — the GUI, not the server, is the source of truth for array layout.

`startHarvestersForRun` then fans out per run:
- one `startHarvesterListener` goroutine per present harvester → writes raw 308-byte
  packets straight to `<dataSaveDir><runNumber>_<telescope>.bin` and, every
  `sendInterval` events, forwards to that telescope's event-builder channel;
- one `eventBuilder` goroutine per present telescope → accumulates harvester
  fragments into the padded 560-array;
- one `guiListener` goroutine → packs all four telescopes into the 8000-byte datagram.

Each run has its own `time.Timer` and a buffered `stopRun` channel; `stopRunCmd` does a
non-blocking send on it, so a stop that arrives before the run goroutine is waiting is
still honoured. `runActive` (an `atomic.Bool`) guards against overlapping runs, and a
start during a run is rejected **before** its state is unmarshalled, so it cannot
overwrite `globalState` under the live run. Status codes go to the GUI on
`guiStatusConnIP`: 1000 started, 1002 ended, 1003 ended manually, and 1001 **aborted**,
sent when run setup fails (data dir missing, harvester address not on this host, bad
state). Setup errors abort the run, not the process — they used to `log.Panic` inside
the goroutine and kill the server. A malformed control datagram is logged and ignored.

Deliberate sloppiness to be aware of before "fixing" it: the event builder does **not**
match event numbers across harvesters, so it flushes and resets its partial event every
32 iterations to bound staleness; `guiChannel` is drained rather than closed (closing it
panicked the GUI listener); `stopListening` channels are closed, not signalled. Every
run goroutine selects on `stopListening`, and the run waits for its listeners before
closing the `.bin` files, so nothing leaks between runs.

`CreateRunFile` never overwrites — if `<run>_<telescope>.bin` exists it shunts to
`<run>_<telescope>_<random hex>.bin` and logs a warning, so a duplicated run number
produces silently renamed files rather than an error.

`send_command` loads its state file from a hardcoded `configFile` path relative to
`server/bin/`, and **discards the load error** (`pGlobalState, _ := ...`). A wrong path
therefore yields an empty state and a run with zero telescopes rather than a failure —
which is exactly how a doubled `states/states/` path in that constant went unnoticed.
Check the path resolves before blaming the hardware.

## Config and state files

- `server/internal/server.json` — socket addresses, `dataSavePath`, `sendInterval`, and
  the command/status number tables. Loaded by **both** the server and the GUI
  ([ui_server.py:515](gui/ui_server.py#L515)).
- `server/internal/state.json` — the array: 4 telescopes × 8 harvesters, each with
  `missing`, `ip`, `channel`, `pixelIndex`. `missing: true` removes it from a run.
- `server/internal/states/` — presets: `state_local.json`, `state_remote.json`,
  `state_washu.json`, `state_veritas_2025.json` (T1 harvester 0 live at
  `10.0.60.204:31261`, everything else missing). The GUI loads one through a file
  dialog and can edit it in place before starting a run. Note `server_192.json` also
  lives here but is a *server* config, not a state file — the older variant with
  `harvesterControlConnIP: 192.168.1.128:5000`.
- `server/internal/fadc.json` — FADC crate SSH inventory: per telescope, four crates
  with `username`, `hostname`, `ip`, and a `commandOptions` string carrying the legacy
  SSH algorithm flags (`+ssh-rsa`, `+aes128-cbc`, `diffie-hellman-group-exchange-sha1`)
  the old crate machines need.

Default ports: control 31250, GUI data 31255, heartbeat 31256, status 31257; harvesters
listen on 3000x / 3126x per the state file. Harvester *control* commands
(`send_harvester_packet`) are UDP sent to `harvesterControlConnIP` from the config
(currently `10.0.10.175:5000`); the broadcast `255.255.255.255:5000` variant is
commented out in the code.

## GUI notes (`gui/`)

`gui/Realtime_GUI.py` is now just the `Window` shell (~120 lines); the behaviour lives in
mixins, one module per panel — `qt_logging`, `star_display`, `veritas_db`, `ui_camera`,
`ui_server`, `ui_run_metadata`, `ui_state_editor`, `ui_star_overlay`, `vestigial`. See
[docs/2026-09-22-gui-module-split-plan.md](docs/2026-09-22-gui-module-split-plan.md).
The mixins share `Window`'s namespace, so every `self` in them is the window.

`gui/GUI.py` (the `Ui_MainWindow` it imports) and `gui/star_options_ui.py` are
**pyuic6-generated** from `designer/GUI.ui` and `designer/star_options.ui` — edit the
`.ui` and run `make` in `gui/`, never edit the `.py`. `make check` reports drift between
a generated module and its source; use it, because `GUI.py` and `GUI.ui` silently
diverged for a year after commit `80c6c5b` hand-edited the generated file.

`resources_rc.py` is the exception: it was built by **PyQt5's** resource compiler, and
PyQt6 has no `pyrcc6`, so `resources.qrc` and `images/` describe the committed blob but
cannot regenerate it with the current toolchain. Leave all three alone.

It owns the whole run: spawns `../server/bin/server` as a subprocess with
`cwd=server/bin`, heartbeats it once a second, sends `startRunCmd` with the current
state embedded, and writes run metadata rows into a **local PostgreSQL** `telescope_db`
via `psycopg` (credentials are hardcoded in `connect_to_vo_db` and
`write_VO_db_params_to_db` in [ui_run_metadata.py](gui/ui_run_metadata.py)). The run
number is **reserved with `nextval` at Start** and inserted explicitly as `run_id`, so the
`.bin` names and the DB row always agree; the number shown before Start is only a
preview. `vo_admin` has USAGE/SELECT on the sequence but not UPDATE, so `setval` is not
available. Separately it reads the **VERITAS MySQL** DB at
`romulus.ucsc.edu` read-only for telescope pointing; that query runs in a
`multiprocessing.Process` (`db_worker_process.py`) rather than a thread, because the
driver blocked the Qt event loop. Star overlays come from astropy / astroplan against
`catalogs/asu2.dat`.

**Start button gating** is a single function, `refresh_start_button` in
[ui_run_metadata.py](gui/ui_run_metadata.py), and `start_blockers` lists its conditions:
no run active, server heartbeat connected, state file loaded with no unsaved edits, a
numeric VO run ID, a source ID (not `null`), and the FADC window set. Anything that
changes one of those calls `refresh_start_button`. Start's tooltip names whatever is
blocking. Start locks as soon as it is clicked. It is released on
ended / ended_manually / aborted, after 5 s if the server never confirms the start, or on
a heartbeat timeout. The Test tab's controls sit behind the **Enable debug controls**
checkbox, and its *populate dt* force-enables Start until the checkbox is cleared.

Exceptions in Qt slots do not abort the GUI: importing `pyqtgraph.Qt` replaces
`sys.excepthook`. `install_exception_logger` (qt_logging) chains onto that hook so the
traceback also reaches the log panel.

FADC gate window changes are applied by SSHing to a crate and running `set_variance`
there (`execute_binary_over_ssh(..., options='')`). `set_fadc_gate_array_window` reads
the host, user and SSH options from `fadc.json`, but is hardwired to
`telescopes[0].crates[0]` and to the binary path
`/home/vdaq/VO/set_variance/set_variance`. `gui/variance_script.sh` is a minimal
standalone SSH smoke test for the same path.

`gui/optical_database.txt` is a saved `psql` dump of `tblrun_info` — useful as a
reference for the run-metadata schema and for what real rows look like.

**Unused files now live in `gui/holder/`** — as of 2026-09-23, everything not reachable
from `Realtime_GUI.py` or `star_overlay_check.py` was moved there: `skyBox.py` (imports a
nonexistent `skyUI`), `scarp.py`, `main.py`, `start2.py`, `designer/start2.ui`,
`GUI_old.ui`, `GUI.xml`, `Realtime_GUI.py.old`, three unused `.qss` themes,
`scripts/UDPsender_v7.py` (superseded by `scripts/UDPsender_v8.py`, which targets
`10.0.10.175` instead of `192.168.0.0/24`), the stale `gui/requirements.txt`, and an
empty `LICENSE`. `gui/holder/README.md` lists them with the evidence.

Do not confuse `gui/holder/` with `gui/vestigial.py`: the latter is a **live, imported**
module that parks unreachable `Window` methods, not a dead file.

Still vestigial and outside that cleanup: the root `GUI.py` stub.

## Analysis scripts

`scripts/utility_functions.py` is the shared library — parsing, FITS writers,
`DataProcessor` (tidy long-form pandas frame indexed by `(event_number, channel)`).
Note it carries two generations of parsers: `read_binary_file`/`extract_data` (older,
returns `number`) and `read_events_from_binary_file`/`parse_data_from_event` (newer,
generator-based, returns `event_number`). New scripts use the generator pair. The FITS
writers still expect the older `number` key, so feeding them `parse_data_from_event`
output requires a rename.

`break_finder.py` and `fit_gaussian.py` take a YAML config (`break_finder.yaml`,
`guesses.yaml`) with tuned per-dataset parameters; those checked-in values are tuning
state for specific long runs — e.g. `guesses.yaml` spans indices 60000–169000, so they
find nothing on a short file. The `.bin`/`.fits` files in `scripts/` are sample run data
and are gitignored.
