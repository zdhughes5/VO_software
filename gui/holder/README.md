# gui/holder/ — parked, not deleted

Files that are no longer part of the running GUI. Kept rather than removed so they are
recoverable without git archaeology; nothing here is imported, loaded or executed.

**This is not `gui/vestigial.py`.** That module *is* live and imported by `Realtime_GUI`;
it holds unreachable `Window` methods so they stay attached to the class. The names are
confusingly similar. `vestigial.py` runs, `holder/` does not.

## Moved 2026-09-23

Everything below was unreachable from both entry points (`Realtime_GUI.py`,
`star_overlay_check.py`) by transitive import closure, opened no file the reachable code
reads, and had no reference anywhere else in the tree.

| File | Why it was parked |
|---|---|
| `main.py` | 2 bytes — a single space. Never imported. |
| `skyBox.py` | Never imported, and **cannot import**: `ModuleNotFoundError: No module named 'skyUI'` |
| `scarp.py` | Never imported; raises `NameError` on an undefined `psycopg2` |
| `start2.py` | pyuic6 output generated from `start.ui`, a file that does not exist in this repo |
| `designer/start2.ui` | The `.ui` behind `start2.py` (note the name mismatch with its own generator header) |
| `GUI_old.ui` | Superseded Qt Designer UI |
| `GUI.xml` | A *third* Designer UI variant, differing from both `GUI.ui` and `GUI_old.ui` |
| `Realtime_GUI.py.old` | Copy predating the 2026-09-22 module split |
| `Incrypt.qss`, `SpyBot.qss`, `VisualScript.qss` | Only `Genetive.qss` is ever loaded |
| `scripts/UDPsender_v7.py` | Superseded by `scripts/UDPsender_v8.py` at the repo root |
| `requirements.txt` | Pinned `astropy==4.2.1`, `numpy==1.20.1`, PyQt5 — conflicted with the root file |
| `LICENSE` | 0 bytes |

## Already here

- `Realtime_GUI.py` — the 1,610-line snapshot from commit `80c6c5b` ("all updates prior
  to trip"). As of the 2026-09-22 module split it is three reorganizations behind the
  live code and is a deletion candidate.

## If you restore something

Check it against the current layout first. `gui/` was reorganized on 2026-09-22: the GUI
is now a `Window` shell plus per-panel mixins, and the Qt Designer sources moved into
`gui/designer/`. Anything here predates that.
