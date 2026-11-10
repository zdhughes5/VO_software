#!/usr/bin/env python3
"""Preflight check for a two-machine VO deployment.

Run on each machine before a run, from anywhere in the clone:

    python3 deploy/check_deploy.py --role trailer --state server/internal/states/<state>.json
    python3 deploy/check_deploy.py --role control [--ssh]

trailer  the DAQ machine that runs server/bin/server and writes the .bin files
control  the control-room machine that runs the GUI and the run DB

Standard library only, so it works on a fresh install without the conda env.
Prints one PASS / WARN / FAIL / INFO line per check and exits 1 if anything
FAILed. The "config fingerprint" line must be identical on both machines.

The control role sends one heartbeat to the server and waits for the reply, so
the server must be running and the GUI must be closed (it holds the heartbeat
port).
"""

import argparse
import errno
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / 'server' / 'internal' / 'server.json'
DEFAULT_FADC = REPO / 'server' / 'internal' / 'fadc.json'
# The GUI's run-DB connection, hardwired in gui/ui_run_metadata.py (connect_to_vo_db).
RUN_DB = {'host': 'localhost', 'port': '5432', 'dbname': 'telescope_db', 'user': 'vo_admin', 'password': 'lsttkc#$!'}
WANTED_RMEM_MAX = 8 << 20  # server.go harvesterSocketReadBuffer
LOW_DISK_GB = 20

results = []


def report(level, message):
    results.append(level)
    print(f"{level:<5} {message}")


# --- helpers ---------------------------------------------------------------

def parse_addr(text):
    """'ip:port' -> (ip, port). Raises ValueError."""
    ip, sep, port = str(text).rpartition(':')
    if not sep or not ip:
        raise ValueError(f"{text!r} is not ip:port")
    return ip, int(port)


def bind_status(ip, port):
    """'free', 'in use' or 'not local' for a UDP ip:port on this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((ip, port))
        return 'free'
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return 'in use'
        if e.errno == errno.EADDRNOTAVAIL:
            return 'not local'
        return f'error: {e}'
    finally:
        s.close()


def is_local(ip):
    return bind_status(ip, 0) == 'free'


def route_source(ip, port):
    """The local address the kernel would send from to reach ip:port (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, port))
        return s.getsockname()[0]
    finally:
        s.close()


def find_placeholders(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from find_placeholders(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from find_placeholders(v, f"{path}[{i}]")
    elif isinstance(obj, str) and 'CHANGE_ME' in obj:
        yield path, obj


def service_active(name):
    try:
        out = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() == 'active'
    except (OSError, subprocess.TimeoutExpired):
        return False


# --- checks for both roles -----------------------------------------------

def check_config(config_path):
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (OSError, ValueError) as e:
        report('FAIL', f"server config {config_path}: {e}")
        return None
    report('PASS', f"server config {config_path} parses")

    for path, value in find_placeholders(config):
        report('FAIL', f"server config {path} still has a placeholder: {value!r}")

    required = ['serverControlConnIP', 'guiDataConnIP', 'guiHeartbeatConnIP', 'guiStatusConnIP',
                'dataSavePath', 'sendInterval', 'commands', 'status']
    missing = [k for k in required if k not in config]
    if missing:
        report('FAIL', f"server config is missing {', '.join(missing)}")
        return None
    for k in ['serverControlConnIP', 'guiDataConnIP', 'guiHeartbeatConnIP', 'guiStatusConnIP']:
        try:
            ip, _ = parse_addr(config[k])
        except ValueError as e:
            report('FAIL', f"{k}: {e}")
            continue
        if ip == '0.0.0.0':
            report('FAIL', f"{k} is 0.0.0.0: the other machine cannot send to that; use this host's real IP")

    layout = config.get('runFileLayout')
    if layout in ('perHarvester', 'perTelescope'):
        report('PASS', f"runFileLayout {layout}")
    else:
        report('WARN', f"runFileLayout {layout!r} is not perHarvester/perTelescope; the server will use perTelescope "
                       f"(all boards of a telescope in one <run>_<tel>.bin)")
    if config.get('harvesterCommandsViaServer') and 'harvesterCmd' not in config['commands']:
        report('FAIL', "harvesterCommandsViaServer is true but commands.harvesterCmd is missing")

    # serverMode only matters to the GUI, so it is left out: the two copies
    # must otherwise be the same file.
    shared = {k: v for k, v in config.items() if k != 'serverMode'}
    digest = hashlib.sha256(json.dumps(shared, sort_keys=True).encode()).hexdigest()[:12]
    report('INFO', f"config fingerprint {digest} -- must match the other machine's")
    return config


def check_clock():
    try:
        out = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        report('WARN', "could not run timedatectl to check clock sync")
        return
    if out == 'yes':
        report('PASS', "system clock is NTP-synchronised")
    else:
        report('WARN', f"system clock is not NTP-synchronised (NTPSynchronized={out or '?'}); "
                       f"DB times and the c004 time pulse come from the clocks")


def check_firewall(ports_text):
    active = [name for name in ('firewalld', 'ufw', 'nftables', 'iptables') if service_active(name)]
    if active:
        report('WARN', f"firewall service active ({', '.join(active)}): make sure inbound UDP {ports_text} is allowed")
    else:
        report('INFO', f"no firewall service detected as active (inbound UDP needed: {ports_text})")


# --- trailer ---------------------------------------------------------------

def check_trailer(config, state_path):
    for name in ('server', 'send_command'):
        binary = REPO / 'server' / 'bin' / name
        if binary.is_file() and os.access(binary, os.X_OK):
            report('PASS', f"{binary} built")
        else:
            report('FAIL' if name == 'server' else 'WARN', f"{binary} missing -- run make in server/")

    log_dir = REPO / 'server' / 'log'
    if (log_dir.is_dir() and os.access(log_dir, os.W_OK)) or (not log_dir.exists() and os.access(log_dir.parent, os.W_OK)):
        report('PASS', f"{log_dir} writable (the server creates it if absent)")
    else:
        report('FAIL', f"{log_dir} not writable")

    ip, port = parse_addr(config['serverControlConnIP'])
    status = bind_status(ip, port)
    if status == 'free':
        report('PASS', f"serverControlConnIP {ip}:{port} is a local address and free")
    elif status == 'in use':
        report('WARN', f"serverControlConnIP {ip}:{port} is in use -- server already running? (systemctl status vo-server)")
    else:
        report('FAIL', f"serverControlConnIP {ip}:{port}: {status} -- it must be this machine's IP")
    if ip.startswith('127.'):
        report('WARN', f"serverControlConnIP is loopback ({ip}); a GUI on another machine cannot reach it")

    gui_local = [k for k in ('guiDataConnIP', 'guiHeartbeatConnIP', 'guiStatusConnIP') if is_local(parse_addr(config[k])[0])]
    if gui_local:
        report('WARN', f"{', '.join(gui_local)} point at THIS machine; for a two-machine setup they are the control-room IP")
    else:
        report('PASS', f"GUI addresses point elsewhere ({parse_addr(config['guiDataConnIP'])[0]})")

    data_dir = Path(config['dataSavePath'])
    if not data_dir.is_dir():
        report('FAIL', f"dataSavePath {data_dir} does not exist (mkdir -p it); runs would abort")
    elif not os.access(data_dir, os.W_OK):
        report('FAIL', f"dataSavePath {data_dir} is not writable")
    else:
        free_gb = shutil.disk_usage(data_dir).free / 1e9
        report('PASS' if free_gb >= LOW_DISK_GB else 'WARN', f"dataSavePath {data_dir} writable, {free_gb:.0f} GB free")

    try:
        rmem_max = int(Path('/proc/sys/net/core/rmem_max').read_text())
        if rmem_max >= WANTED_RMEM_MAX:
            report('PASS', f"net.core.rmem_max {rmem_max}")
        else:
            report('WARN', f"net.core.rmem_max is {rmem_max}; harvester sockets ask for {WANTED_RMEM_MAX}. "
                           f"sudo sysctl -w net.core.rmem_max={WANTED_RMEM_MAX} (and persist it in /etc/sysctl.d/)")
    except OSError as e:
        report('WARN', f"could not read net.core.rmem_max: {e}")

    harvester_ports = check_state(state_path)
    check_firewall(f"{port} (control)" + (f", {harvester_ports} (harvesters)" if harvester_ports else ""))
    check_clock()


def check_state(state_path):
    """Check the harvester addresses a run would listen on. Returns a port summary."""
    if state_path is None:
        report('WARN', "no --state given: harvester addresses not checked (pass the state file the GUI will load)")
        return ''
    try:
        with open(state_path) as f:
            state = json.load(f)
    except (OSError, ValueError) as e:
        report('FAIL', f"state file {state_path}: {e}")
        return ''
    report('PASS', f"state file {state_path} parses")

    seen = {}
    ports = []
    present_telescopes = [t for t in state.get('telescopes', []) if not t.get('missing')]
    if not present_telescopes:
        report('FAIL', "state has no present telescope")
    for t in present_telescopes:
        tel = t.get('telescope')
        if tel not in (1, 2, 3, 4):
            report('FAIL', f"telescope number {tel!r} is outside 1-4")
        present = [h for h in t.get('harvesters', []) if not h.get('missing')]
        report('INFO', f"T{tel}: {len(present)} present harvester(s): "
                       f"{', '.join('h%s' % h.get('localPosition') for h in present) or 'none'}")
        for h in present:
            label = f"T{tel} h{h.get('localPosition')}"
            if not 0 <= int(h.get('localPosition', -1)) <= 7:
                report('FAIL', f"{label}: localPosition outside 0-7")
            a, b = h.get('channel', [0, 0])
            if not (0 <= a < b <= 560):
                report('FAIL', f"{label}: bad channel range {[a, b]}")
            elif b - a != 70:
                report('WARN', f"{label}: channel range {[a, b]} is not 70 wide")
            try:
                ip, port = parse_addr(h.get('ip'))
            except ValueError as e:
                report('FAIL', f"{label}: {e}")
                continue
            if (ip, port) in seen:
                report('FAIL', f"{label} and {seen[(ip, port)]} share {ip}:{port}; each board needs its own port")
                continue
            seen[(ip, port)] = label
            ports.append(port)
            status = bind_status(ip, port)
            if status == 'free':
                report('PASS', f"{label} listens on {ip}:{port} (local, free)")
            elif status == 'in use':
                report('WARN', f"{label} {ip}:{port} is in use -- a run in progress?")
            else:
                report('FAIL', f"{label} {ip}:{port}: {status} -- the harvester IP must be one of this machine's addresses")
    if not ports:
        return ''
    return ', '.join(str(p) for p in sorted(ports))


# --- control -----------------------------------------------------------------

def check_control(config, fadc_path, do_ssh):
    mode = config.get('serverMode', 'local')
    if mode == 'remote':
        report('PASS', "serverMode remote: the GUI connects to the trailer server instead of launching one")
    else:
        report('WARN', f"serverMode is {mode!r}: the GUI will launch its own local server. Set \"remote\" for a two-machine setup")

    server_ip, server_port = parse_addr(config['serverControlConnIP'])
    if is_local(server_ip):
        report('WARN', f"serverControlConnIP {server_ip} is THIS machine; for a two-machine setup it is the trailer's IP")
    try:
        report('PASS', f"route to server {server_ip}:{server_port} via local address {route_source(server_ip, server_port)}")
    except OSError as e:
        report('FAIL', f"no route to server {server_ip}:{server_port}: {e}")

    gui_ports = []
    gui_free = True
    for key, name in (('guiDataConnIP', 'data'), ('guiHeartbeatConnIP', 'heartbeat'), ('guiStatusConnIP', 'status')):
        ip, port = parse_addr(config[key])
        gui_ports.append(str(port))
        status = bind_status(ip, port)
        if status == 'free':
            report('PASS', f"GUI {name} port {ip}:{port} local and free")
        elif status == 'in use':
            gui_free = False
            report('WARN', f"GUI {name} port {ip}:{port} in use -- the GUI is running? close it to run the heartbeat check")
        else:
            report('FAIL', f"GUI {name} address {ip}:{port}: {status} -- it must be this machine's IP")

    if gui_free:
        heartbeat_round_trip(config)

    harvester_ctrl = config.get('harvesterControlConnIP')
    if config.get('harvesterCommandsViaServer'):
        report('INFO', f"harvester commands are relayed by the server to {harvester_ctrl}")
    elif harvester_ctrl:
        try:
            ip, port = parse_addr(harvester_ctrl)
            report('INFO', f"harvester commands go direct to {harvester_ctrl} via local address {route_source(ip, port)} "
                           f"(UDP delivery cannot be confirmed from here; if c001 has no effect set harvesterCommandsViaServer)")
        except (OSError, ValueError) as e:
            report('WARN', f"no route to harvesterControlConnIP {harvester_ctrl} ({e}); consider harvesterCommandsViaServer: true")

    try:
        with socket.create_connection(('localhost', 5432), timeout=3):
            report('PASS', "PostgreSQL is listening on localhost:5432 (run DB)")
        check_run_db()
    except OSError as e:
        report('FAIL', f"PostgreSQL not reachable on localhost:5432 ({e}); runs would have no DB row"
                       f" -- set it up with: sudo deploy/setup_postgres.sh")

    if do_ssh:
        check_fadc_ssh(fadc_path)
    check_firewall(f"{', '.join(gui_ports)} (GUI data/heartbeat/status)")
    check_clock()


def check_run_db():
    """Connect as the GUI does and read the run sequence the way read_last_run_id does.

    Uses the psql client when present (the check stays stdlib-only); catches a
    missing database, table, role or grant, which the port check above cannot.
    """
    psql = shutil.which('psql')
    if psql is None:
        report('INFO', "psql not installed, so telescope_db itself was not checked (only the port)")
        return
    query = ("SELECT GREATEST(CASE WHEN is_called THEN last_value + 1 ELSE last_value END, "
             "(SELECT COALESCE(MAX(run_id), 0) + 1 FROM tblrun_info)) FROM tblrun_info_run_id_seq")
    cmd = [psql, '-X', '-w', '-At', '-h', RUN_DB['host'], '-p', RUN_DB['port'],
           '-U', RUN_DB['user'], '-d', RUN_DB['dbname'], '-c', query]
    env = dict(os.environ, PGPASSWORD=RUN_DB['password'], PGCONNECT_TIMEOUT='3')
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        report('FAIL', f"run DB check via psql failed: {e}")
        return
    if out.returncode == 0 and out.stdout.strip().isdigit():
        report('PASS', f"run DB {RUN_DB['dbname']} usable as {RUN_DB['user']}; next run ID {out.stdout.strip()}")
        check_run_db_columns(cmd[:-1], env)
    else:
        error = out.stderr.strip().splitlines()[-1] if out.stderr.strip() else f"unexpected output {out.stdout!r}"
        report('FAIL', f"run DB {RUN_DB['dbname']} not usable as {RUN_DB['user']}: {error}"
                       f" -- set it up with: sudo deploy/setup_postgres.sh")


def check_run_db_columns(psql_cmd, env):
    """Catch a run DB set up before the notes column, which write_VO_db_params_to_db inserts into."""
    query = ("SELECT count(*) FROM information_schema.columns "
             "WHERE table_schema = 'public' AND table_name = 'tblrun_info' AND column_name = 'notes'")
    try:
        out = subprocess.run(psql_cmd + [query], capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        report('WARN', f"could not check tblrun_info's columns: {e}")
        return
    count = out.stdout.strip()
    if out.returncode != 0 or not count.isdigit():
        report('WARN', f"could not check tblrun_info's columns: {out.stderr.strip() or out.stdout.strip()!r}")
    elif count == '0':
        report('WARN', "tblrun_info has no notes column, so every run's DB insert will fail"
                       " -- migrate it by re-running: sudo deploy/setup_postgres.sh")
    else:
        report('PASS', "tblrun_info has the notes column")


def heartbeat_round_trip(config):
    """Send one heartbeat from the GUI heartbeat port and wait for the server's reply."""
    hb_ip, hb_port = parse_addr(config['guiHeartbeatConnIP'])
    server_ip, server_port = parse_addr(config['serverControlConnIP'])
    command = config['commands'].get('hearbeatCmd', 7)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((hb_ip, hb_port))
        s.settimeout(2.0)
        t0 = time.monotonic()
        s.sendto(json.dumps({"command": command}).encode(), (server_ip, server_port))
        data, sender = s.recvfrom(1024)
        ms = (time.monotonic() - t0) * 1000
        report('PASS', f"heartbeat round trip: reply {data[:20]!r} from {sender[0]}:{sender[1]} in {ms:.1f} ms")
    except socket.timeout:
        report('FAIL', f"no heartbeat reply within 2 s. Check: server running on the trailer (systemctl status vo-server); "
                       f"trailer firewall allows UDP {server_port}; this machine's firewall allows UDP {hb_port}; "
                       f"the TRAILER's server.json has guiHeartbeatConnIP {hb_ip}:{hb_port}")
    except OSError as e:
        report('FAIL', f"heartbeat round trip failed: {e}")
    finally:
        s.close()


def check_fadc_ssh(fadc_path):
    """The GUI's set_fadc_gate_array_window SSHes to telescopes[0].crates[0]'s hostname and runs its
    binary, with no password prompt possible."""
    try:
        with open(fadc_path) as f:
            crate = json.load(f)['telescopes'][0]['crates'][0]
        target = f"{crate['username']}@{crate['hostname']}"
        binary = crate['binary']
    except (OSError, ValueError, KeyError, IndexError) as e:
        report('FAIL', f"fadc config {fadc_path}: {e!r} (the GUI needs username, hostname and binary "
                       f"in telescopes[0].crates[0])")
        return
    # -v only adds noise here; -X/-Y would try to forward a display.
    options = [o for o in shlex.split(crate.get('commandOptions', '')) if o not in ('-v', '-XY', '-X', '-Y')]
    cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', *options, target,
           f"test -x {shlex.quote(binary)} && echo set_variance-ok"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        report('FAIL', f"ssh to FADC crate {target}: {e}")
        return
    if 'set_variance-ok' in out.stdout:
        report('PASS', f"ssh to FADC crate {target} works without a password and {binary} is executable")
    elif out.returncode == 255:
        report('FAIL', f"ssh to FADC crate {target} failed (key auth needed, no password prompt possible): "
                       f"{out.stderr.strip().splitlines()[-1] if out.stderr.strip() else 'no message'}")
    else:
        report('FAIL', f"logged in to {target} but {binary} is not executable there")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--role', required=True, choices=['trailer', 'control'])
    parser.add_argument('--config', default=str(DEFAULT_CONFIG), help=f"server config (default {DEFAULT_CONFIG})")
    parser.add_argument('--state', help="state file the GUI will load (trailer role: checks the harvester addresses)")
    parser.add_argument('--fadc', default=str(DEFAULT_FADC), help=f"FADC crate config (default {DEFAULT_FADC})")
    parser.add_argument('--ssh', action='store_true', help="control role: also test SSH to the FADC crate")
    args = parser.parse_args()

    print(f"VO deployment check, role {args.role}, host {socket.gethostname()}")
    config = check_config(args.config)
    if config is not None:
        if args.role == 'trailer':
            check_trailer(config, args.state)
        else:
            check_control(config, args.fadc, args.ssh)

    fails, warns = results.count('FAIL'), results.count('WARN')
    print(f"\n{fails} FAIL, {warns} WARN")
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
