# Onsite checklist — two-machine, multi-board deployment

| Machine | Role |
|---|---|
| **Trailer PC** (new install) | Runs `server/bin/server`, receives harvester UDP, writes the `.bin` files. |
| **Control-room PC** | Runs the GUI, starts and stops runs, shows the cameras, writes the run DB row (PostgreSQL on `localhost`). |

Both machines use **the same `server/internal/server.json`**. Each side reads the
addresses it needs from it. `deploy/check_deploy.py` prints a *config fingerprint*, which
must be identical on the two machines.

Fill these in first. Everything below refers to them.

| Value | Write it here |
|---|---|
| `TRAILER_IP`: trailer address reachable **from the control room** | |
| `HARVESTER_NET_IP`: trailer address the **harvester boards send to** (it may be the same NIC) | |
| `CONTROL_IP`: control-room address reachable **from the trailer** | |
| Trailer user and clone path (`REPO`) | |
| Trailer data directory | |

---

## 1. Settings to change

### `server/internal/server.json`: identical file on both machines

Start from `server/internal/states/server_two_machine.json`. Copy it over `server.json`
and replace every `CHANGE_ME_*`. The preflight script FAILs on any that remain.

| Key | Current value (this laptop) | Onsite value |
|---|---|---|
| `serverControlConnIP` | `127.0.0.1:31250` | `TRAILER_IP:31250` |
| `guiDataConnIP` | `127.0.0.1:31255` | `CONTROL_IP:31255` |
| `guiHeartbeatConnIP` | `127.0.0.1:31256` | `CONTROL_IP:31256` |
| `guiStatusConnIP` | `127.0.0.1:31257` | `CONTROL_IP:31257` |
| `harvesterControlConnIP` | `10.0.10.175:5000` | Harvester control address. Confirm it is still `10.0.10.175`. |
| `dataSavePath` | `/home/zdhughes/optical_data/` | The **trailer's** data directory. ⚠ The GUI sends this value from *its own* copy, and the trailer creates files there. The GUI's "save path" box is display-only. |
| `runFileLayout` | `perHarvester` | Keep `perHarvester`: one `<run>_<tel>_h<pos>.bin` per board. Use `perTelescope` only if a board ID is added to the 308-byte payload. |
| `serverMode` | `local` | `remote`. It only matters on the control room, but keep the files identical. |
| `harvesterCommandsViaServer` | `false` | Start with `false`. Set it to `true` if the harvester command buttons (Arm / Disarm / Test Transmission / UNIX Time Sync) don't reach the boards from the control room (§6). |
| `sendInterval` | `30` | Unchanged. It sets only the GUI display sampling. |
| `commands.harvesterCmd` | `9` | Unchanged. It must be present. |

Never use `0.0.0.0` or `127.0.0.1` for any address above. The other machine cannot send
to them.

### State file: loaded in the GUI with File → Load state

Start from `server/internal/states/state_veritas_multiboard.json`. It has T1 h0–h7
present, and T2–T4 missing.

| Field | Current value | Onsite value |
|---|---|---|
| T1 h0 `ip` | `10.0.60.204:31261` | `HARVESTER_NET_IP:<port board 0 sends to>` |
| T1 h1–h7 `ip` | `10.0.60.204:31262` … `:31268` | ⚠ **Assumed** pattern. Confirm the destination port **programmed into each board**. |
| `missing` | `false` for h0–h7 | `true` for every board that is not installed or not sending |
| `channel` | `[0,70]` … `[490,560]` | Unchanged |

- The IP must be **an address of the trailer PC**. The server *binds* it, and the run
  aborts (status 1001) if it can't.
- Every board needs its own port.
- After editing, press **Set**. Start stays blocked while there are unsaved edits.
- ⚠ **Pixel placement is unverified for h1–h7.** The server places pixels with
  `ExtractRelevantPixels`, which keeps channels `[0:130] [140:260] [280:410] [420:540]`.
  That gives h6 70 real pixels and h7 50. The state files' `pixelIndex` say 60 and 60.
  `pixelIndex` is display-only in the state editor, so the server's split is the one used.
  Check the camera picture against a known pattern before trusting the h6/h7 sectors.

### `server/internal/fadc.json`: control room

| Key | Current value | Onsite value |
|---|---|---|
| `telescopes[0].crates[0].ip` / `username` | `10.0.0.102` / `vdaq` | The T1 crate. This is the only crate the GUI uses (`ui_server.py:255`). |
| `commandOptions` | legacy `ssh-rsa` / `aes128-cbc` flags | Unchanged, unless the crate has changed |

The `set_variance` path is hardwired at `gui/ui_server.py:261` as
`/home/vdaq/VO/set_variance/set_variance`. Check it exists on the crate. `--ssh` in §5
checks it for you.

### Things that are *not* settings but will bite

- The run DB is `localhost:5432` (`gui/ui_run_metadata.py:191`), so PostgreSQL must run
  on the **control-room** PC.
- `server/bin/` is gitignored, so the binaries must be built or copied onto the trailer
  (§3).

---

## 2. Before leaving (on this laptop)

- [ ] `cd server && make static`
  - This builds *statically linked* `bin/server` and `bin/send_command`. The normal
    `make` links against this Manjaro's glibc, which the new install may not have.
  - Building on the trailer instead needs Go ≥ 1.21 **and internet** to fetch cobra.
  - Run `make static` last before copying: a later plain `make` says "nothing to be done"
    and leaves the static binaries in place, but the reverse is not true.
- [ ] Copy the clone to the trailer, `server/bin/` included (`rsync -a VO_software/ trailer:REPO/`).
- [ ] Prepare `server.json` with the real IPs (§1) and copy it to **both** machines.
- [ ] Prepare the multiboard state file with the real board ports.

## 3. Trailer PC (new install)

- [ ] Python 3 (stdlib only) for the preflight. Go and make only if building here.
- [ ] Data directory: `mkdir -p <dataSavePath>`, owned by the user the server runs as.
      Check the free disk space.
- [ ] Socket buffers. The server asks for 8 MiB per board, and the kernel caps that silently:
  ```
  echo 'net.core.rmem_max=8388608' | sudo tee /etc/sysctl.d/90-vo.conf
  sudo sysctl --system
  ```
- [ ] Firewall: allow inbound UDP **31250** (control, from the control room) and **every
      harvester port** in the state file (from the boards).
      For example, with firewalld: `sudo firewall-cmd --permanent --add-port=31250/udp --add-port=31261-31268/udp && sudo firewall-cmd --reload`
- [ ] Clock synchronised (NTP). `timedatectl` should say `System clock synchronized: yes`.
- [ ] Install the server as a service:
  ```
  sed -e "s#@REPO@#$REPO#g" -e "s#@USER@#$USER#g" deploy/vo-server.service | sudo tee /etc/systemd/system/vo-server.service
  sudo systemctl daemon-reload && sudo systemctl enable --now vo-server
  systemctl status vo-server
  ```
  - The no-root alternative: `tmux new -s vo 'cd REPO/server/bin && ./server'`.
  - After changing `server.json`: `sudo systemctl restart vo-server`.
- [ ] `python3 deploy/check_deploy.py --role trailer --state <state file>`
  - Run it once **before** starting the service: ports read "free" and the harvester IPs
    are bindable.
  - Run it again after: the control port reads "in use", as expected.
  - 0 FAIL required. Note the fingerprint.

## 4. Control-room PC

- [ ] `server.json` identical to the trailer's (fingerprint matches), `serverMode: remote`.
- [ ] Firewall: allow inbound UDP **31255, 31256, 31257** from the trailer.
- [ ] PostgreSQL running (`telescope_db`).
- [ ] Clock synchronised. The DB times and the UNIX Time Sync pulse (c004) use this clock.
- [ ] SSH to the FADC crate works **without a password**. The GUI cannot answer a prompt.
- [ ] With the server running on the trailer and the **GUI closed**:
      `python3 deploy/check_deploy.py --role control --ssh`. 0 FAIL required, including
      "heartbeat round trip".
- [ ] Start the GUI. It connects automatically: the server status turns green
      "Connected", and the buttons read Connect/Disconnect.
  - Closing the GUI or pressing Disconnect **does not** stop the server.

## 5. Bring-up sequence

1. **Network only, no boards.**
   - In the GUI, load the state and run a short Start.
   - Then use the Test tab: enable the debug controls, then **send_command generate**
     (e.g. 2000 packets, 500 µs).
   - The packets go from the control room to the trailer's harvester ports, which proves
     that path and that firewall.
   - On the trailer, `ls -l <dataSavePath>/<run>_1_h*.bin` should show every present board
     at exactly 2000 × 308 = 616000 bytes.
2. **One real board.** Mark only h0 present (central board, as before) and run.
3. **All boards.** Mark the installed boards present and run.
   - On the trailer, after the run:
     `grep -E "received 0 packets|Got .* events" REPO/server/log/server.log | tail -20`
   - A `WARNING ... h<N> received 0 packets` means board N's destination IP or port
     doesn't match the state file, or the board isn't sending.
   - The camera shows the boards that *are* sending. A silent board is a dark sector,
     not a blank camera.
4. Offline sanity check per board:
   `cd scripts && python check_integrity.py <run>_1_h<N>.bin`.
   - With `generate` data, "event numbers are not monotonic" is expected: `generate`
     writes little-endian event numbers and the scripts read big-endian.

## 6. Harvester control commands

| Button | Command |
|---|---|
| Arm Harvester | `0xc001` |
| Disarm Harvester | `0xc002` |
| Test Transmission | `0xc003` |
| UNIX Time Sync | `0xc004` + timestamp (also sent every 1 s while the time pulse is started) |

- These go from the **control room** straight to `harvesterControlConnIP`.
- If the boards don't respond, set `"harvesterCommandsViaServer": true` in the control
  room's `server.json` and restart the GUI. The trailer forwards the same bytes instead.
- Confirm the relay in the trailer's `server.log`:
  `Relayed 6-byte harvester command c001... to 10.0.10.175:5000`.
- The trailer must then be able to reach the harvester control address. Check with
  `ip route get 10.0.10.175` on the trailer.

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| GUI server status red "Disconnected" | Check, in order: server not running on the trailer (`systemctl status vo-server`); trailer firewall (31250); control firewall (31256); the **trailer's** `guiHeartbeatConnIP` is not `CONTROL_IP`. |
| Start released after 5 s with "did not confirm the run start" | Look at the trailer's `server.log`. "bad JSON" means the start datagram was cut (e.g. by a firewall dropping IP fragments: the start is ~5 kB, more than one MTU). Otherwise status 1001 never arrived, so check the control firewall (31257). |
| Status **aborted** (1001) | See `server.log` for "aborted during setup". Usually the data dir is missing, or a harvester IP is not a trailer address. |
| Run starts, but the camera stays black | Check the control firewall (31255), and that the trailer's `guiDataConnIP` is `CONTROL_IP`. Also check that no board is sending at all (0-packet warnings). |
| One board's `.bin` is 0 bytes | That board's destination port or IP differs from the state file, or the trailer firewall blocks that port. |
| `.bin` named `<run>_1_h0_<hex>.bin` | The run number was reused, and the server refuses to overwrite. |
| "Could not bind the … socket" at GUI start | Another GUI is holding 31255–31257 (`ss -lunp \| grep 3125`). |
| FADC window set gives no output | SSH needs a key (no prompt possible), or the `set_variance` path is wrong. Run `check_deploy.py --role control --ssh`. |
