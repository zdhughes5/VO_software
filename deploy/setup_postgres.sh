#!/bin/bash
#
# Install and set up the VO run-metadata PostgreSQL database on the control-room PC.
#
#   sudo deploy/setup_postgres.sh [--start-run-id N] [--import runs.sql] [--yes]
#
# The GUI (gui/ui_run_metadata.py) writes one row per run into telescope_db on
# localhost:5432 as vo_admin, and reserves each run number from the
# tblrun_info_run_id_seq sequence. This script produces that database on a fresh
# machine:
#
#   1. installs PostgreSQL       dnf (AlmaLinux / Rocky / RHEL / Fedora), apt (Debian / Ubuntu)
#                                or pacman (Arch / Manjaro)
#   2. initialises the cluster   UTF8, en_US.UTF-8, in the distribution's default data dir
#                                (on Debian/Ubuntu the package creates <version>/main itself)
#   3. writes pg_hba.conf        trust for local socket, 127.0.0.1 and ::1 only (as on hypatia)
#   4. enables and starts        the postgresql systemd unit (postgresql@<version>-main on Debian/Ubuntu)
#   5. provisions                role vo_admin, database telescope_db, deploy/telescope_db_schema.sql
#   6. run history (optional)    --import a data-only dump and/or --start-run-id
#
# Safe to re-run: an existing cluster is never re-initialised or deleted, existing
# rows are never touched, and pg_hba.conf is backed up before it is replaced.
#
# Options:
#   --start-run-id N   the next run gets number N (or max(run_id)+1 if that is higher).
#                      Use it so a new machine does not reuse run numbers, which name
#                      the .bin files. Only applies while tblrun_info is empty.
#   --import FILE      load the rows of an old machine's tblrun_info, made there with
#                        pg_dump -h localhost -U vo_admin --data-only -t tblrun_info telescope_db > FILE
#                      The sequence then continues after the highest imported run_id.
#                      Only applies while tblrun_info is empty. Loaded in one transaction.
#   --provision-only   skip steps 1-4 and only provision, connecting with the caller's
#                      PGHOST / PGPORT / PGUSER (which must be a superuser). Does not need
#                      root. For re-provisioning an existing server, and for testing
#                      against a throwaway cluster.
#   --yes              do not ask before installing / initialising
#
# Environment:
#   VO_DB_PASSWORD     vo_admin's password. Default: the one hardcoded in
#                      gui/ui_run_metadata.py. Under trust auth it is not checked, but it
#                      is set so a later switch to password auth works with the GUI as is.
#
# Afterwards: python3 deploy/check_deploy.py --role control

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_SQL="$REPO/deploy/telescope_db_schema.sql"

DB_NAME=telescope_db
DB_ROLE=vo_admin
DB_PORT=5432
SEQUENCE=public.tblrun_info_run_id_seq
# Must match connect_to_vo_db / write_VO_db_params_to_db in gui/ui_run_metadata.py.
GUI_PASSWORD='lsttkc#$!'
VO_DB_PASSWORD="${VO_DB_PASSWORD:-$GUI_PASSWORD}"
PREFERRED_LOCALE=en_US.UTF-8
OS_RELEASE=/etc/os-release
DEBIAN_PG_LIB=/usr/lib/postgresql   # one <major version>/bin per installed server on Debian/Ubuntu

START_RUN_ID=""
IMPORT_FILE=""
PROVISION_ONLY=0
ASSUME_YES=0
ORIG_ARGS="$*"
# Debian/Ubuntu cluster identity, filled in by locate_debian_cluster.
PG_VER=""
PG_CLUSTER=main
OTHER_CLUSTERS=""

info() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }
die()  { echo "ERROR: $*" >&2; exit 1; }

usage() {
    sed -n '3,/^# Afterwards/s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
    exit "${1:-0}"
}

# --- arguments ---------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --start-run-id)
            [[ $# -ge 2 ]] || die "--start-run-id needs a number"
            [[ "$2" =~ ^[1-9][0-9]*$ ]] || die "--start-run-id must be a positive integer, got '$2'"
            START_RUN_ID="$2"; shift 2 ;;
        --import)
            [[ $# -ge 2 ]] || die "--import needs a file"
            IMPORT_FILE="$2"; shift 2 ;;
        --provision-only) PROVISION_ONLY=1; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        -h|--help) usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

[[ -r "$SCHEMA_SQL" ]] || die "schema file $SCHEMA_SQL not found"

if [[ -n "$IMPORT_FILE" ]]; then
    [[ -f "$IMPORT_FILE" && -r "$IMPORT_FILE" ]] || die "--import file '$IMPORT_FILE' is not a readable file"
    # Absolute, because the script later does cd / before the import reads it.
    IMPORT_FILE=$(realpath -- "$IMPORT_FILE")
    # It runs as a superuser, so make sure it is what the help says it is.
    grep -Eq '^(COPY|INSERT INTO) public\.tblrun_info[ (]' "$IMPORT_FILE" \
        || die "'$IMPORT_FILE' has no COPY/INSERT into public.tblrun_info. Make it with:
    pg_dump -h localhost -U vo_admin --data-only -t tblrun_info telescope_db > FILE"
    if grep -Eiq '^[[:space:]]*(DROP|CREATE|ALTER|GRANT|REVOKE|TRUNCATE|DELETE)[[:space:]]' "$IMPORT_FILE"; then
        die "'$IMPORT_FILE' contains DDL or DELETE statements; expected a data-only dump (pg_dump --data-only)"
    fi
fi

# psql, as the postgres OS user (normal mode) or as the caller (--provision-only).
# SQL is always fed on stdin: the postgres user may not be able to read files in
# the repo or the caller's home. NOTICEs ("already exists, skipping") are hidden.
run_psql() {
    if [[ $PROVISION_ONLY -eq 1 ]]; then
        PGOPTIONS='-c client_min_messages=warning' psql -X -q -v ON_ERROR_STOP=1 "$@"
    else
        runuser -u postgres -- env PGOPTIONS='-c client_min_messages=warning' \
            psql -X -q -v ON_ERROR_STOP=1 -p "$DB_PORT" "$@"
    fi
}

# --- steps 1-4: install, initialise, configure, start ----------------------------

detect_family() {
    local id="" id_like="" word
    # os-release is a system file, not part of the repo, so shellcheck cannot follow it.
    # shellcheck disable=SC1090
    id=$(. "$OS_RELEASE" && echo "${ID:-}")
    # shellcheck disable=SC1090
    id_like=$(. "$OS_RELEASE" && echo "${ID_LIKE:-}")
    for word in $id $id_like; do
        case "$word" in
            rhel|centos|fedora|almalinux|rocky) echo rhel; return ;;
            debian|ubuntu) echo debian; return ;;
            arch|manjaro) echo arch; return ;;
        esac
    done
    die "unsupported OS '$id' (ID_LIKE '$id_like'). Supported: RHEL family (dnf), Debian/Ubuntu (apt) and Arch/Manjaro (pacman)."
}

package_installed() {
    case "$FAMILY" in
        rhel) rpm -q postgresql-server postgresql >/dev/null 2>&1 ;;
        debian) [[ "$(dpkg-query -W -f='${Status}' postgresql 2>/dev/null)" == "install ok installed" ]] ;;
        arch) pacman -Q postgresql >/dev/null 2>&1 ;;
    esac
}

install_packages() {
    case "$FAMILY" in
        rhel) dnf install -y postgresql-server postgresql ;;
        debian)
            # The package's postinst creates the cluster <version>/main itself, with the
            # locale taken from the environment, on the first free port from 5432 (checked
            # free above).
            apt-get update
            DEBIAN_FRONTEND=noninteractive LANG="$LOCALE" LC_ALL="$LOCALE" apt-get install -y postgresql ;;
        arch) pacman -S --needed --noconfirm postgresql ;;
    esac
}

# The data directory the postgresql unit will actually use: PGDATA on RHEL,
# PGROOT/data on Arch. Falls back to the distribution default.
unit_data_dir() {
    local env_line word pgdata="" pgroot=""
    env_line=$(systemctl show -p Environment --value postgresql 2>/dev/null || true)
    for word in $env_line; do
        case "$word" in
            PGDATA=*) pgdata="${word#PGDATA=}" ;;
            PGROOT=*) pgroot="${word#PGROOT=}" ;;
        esac
    done
    if [[ -n "$pgdata" ]]; then echo "$pgdata"
    elif [[ -n "$pgroot" ]]; then echo "$pgroot/data"
    elif [[ "$FAMILY" == rhel ]]; then echo /var/lib/pgsql/data
    else echo /var/lib/postgres/data
    fi
}

# Newest PostgreSQL server installed under /usr/lib/postgresql (Debian/Ubuntu), or
# nothing. A version directory with only the client in it has no initdb.
newest_debian_server() {
    local dir
    for dir in "$DEBIAN_PG_LIB"/*/; do
        if [[ -x "${dir}bin/initdb" ]]; then basename "$dir"; fi
    done | sort -V | tail -n 1
}

# Debian/Ubuntu: the cluster that pg_lsclusters lists on port 5432, if any. Sets
# PG_VER, PG_CLUSTER, DATA_DIR, NEED_INIT and OTHER_CLUSTERS (clusters on other ports).
locate_debian_cluster() {
    local ver name port _status _owner datadir _log listing=""
    PG_VER=""; PG_CLUSTER=main; DATA_DIR=""; NEED_INIT=1; OTHER_CLUSTERS=""
    if command -v pg_lsclusters >/dev/null; then
        listing=$(pg_lsclusters -h 2>/dev/null || true)
    fi
    while read -r ver name port _status _owner datadir _log; do
        [[ -n "$ver" ]] || continue
        if [[ "$port" == "$DB_PORT" ]]; then
            PG_VER=$ver; PG_CLUSTER=$name; DATA_DIR=$datadir; NEED_INIT=0
        else
            OTHER_CLUSTERS+="    $ver/$name on port $port ($datadir)"$'\n'
        fi
    done <<< "$listing"
    if [[ $NEED_INIT -eq 1 ]]; then
        PG_VER=$(newest_debian_server)
        DATA_DIR="/var/lib/postgresql/${PG_VER:-<version>}/$PG_CLUSTER"
    fi
}

# Where this machine's cluster is, or will be. Sets DATA_DIR, HBA_FILE, SERVICE
# (the systemd unit that runs it) and NEED_INIT (1 when there is no cluster yet).
locate_cluster() {
    case "$FAMILY" in
        rhel|arch)
            DATA_DIR=$(unit_data_dir)
            HBA_FILE="$DATA_DIR/pg_hba.conf"
            SERVICE=postgresql
            NEED_INIT=0; [[ -f "$DATA_DIR/PG_VERSION" ]] || NEED_INIT=1 ;;
        debian)
            locate_debian_cluster
            HBA_FILE="/etc/postgresql/${PG_VER:-<version>}/$PG_CLUSTER/pg_hba.conf"
            SERVICE="postgresql@${PG_VER:-<version>}-$PG_CLUSTER" ;;
    esac
}

pick_locale() {
    if locale -a 2>/dev/null | grep -Eqix 'en_US\.utf-?8'; then
        echo "$PREFERRED_LOCALE"
    else
        warn "locale $PREFERRED_LOCALE is not generated on this machine; using C.UTF-8.
         To use en_US.UTF-8 instead (as on hypatia), stop now and run:
           sudo sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && sudo locale-gen  (Arch/Manjaro, Debian)
           sudo locale-gen en_US.UTF-8                                                     (Ubuntu)
           sudo dnf install -y glibc-langpack-en                                           (RHEL family)"
        echo C.UTF-8
    fi
}

init_cluster() {
    case "$FAMILY" in
        rhel)
            # postgresql-setup takes the data dir from the unit and passes these to initdb.
            PGSETUP_INITDB_OPTIONS="-E UTF8 --locale=$LOCALE" postgresql-setup --initdb ;;
        debian)
            # Only reached when the package did not create a cluster (e.g.
            # create_main_cluster = false in /etc/postgresql-common/createcluster.conf).
            [[ -n "$PG_VER" ]] || die "no PostgreSQL server found under $DEBIAN_PG_LIB after installing"
            pg_createcluster --locale "$LOCALE" -e UTF8 -p "$DB_PORT" "$PG_VER" "$PG_CLUSTER" ;;
        arch)
            install -d -o postgres -g postgres -m 700 "$DATA_DIR"
            runuser -u postgres -- initdb -D "$DATA_DIR" -E UTF8 --locale="$LOCALE" ;;
    esac
}

# Start the cluster's unit now and at boot. On Debian/Ubuntu postgresql.service is
# only an umbrella (active even with nothing running); the cluster is the instance
# postgresql@<ver>-<cluster>, started at boot by the umbrella for start.conf=auto.
enable_and_start() {
    if [[ "$FAMILY" == debian ]]; then
        systemctl enable --quiet postgresql
        systemctl start "$SERVICE"
    else
        systemctl enable --now "$SERVICE"
    fi
}

# Replace pg_hba.conf with the VO rules, keeping a backup of anything different.
# Prints "changed" or "unchanged" on stdout (messages go to stderr), so it can run
# under set -e without being called from an && list, where errexit is suspended.
write_pg_hba() {
    local hba="$HBA_FILE" tmp mode=600
    tmp=$(mktemp)
    cat > "$tmp" <<'EOF'
# Written by VO_software deploy/setup_postgres.sh.
#
# Trust for local connections only, as on the original hand-built control-room
# machine: the GUI connects to localhost:5432 as vo_admin. listen_addresses is
# localhost, and there is no rule for any other address, so nothing off this
# machine can connect. Edits here are replaced when the script is re-run (the
# previous file is kept as pg_hba.conf.vo-bak-<timestamp>).
#
# TYPE  DATABASE  USER  ADDRESS        METHOD
local   all       all                  trust
host    all       all   127.0.0.1/32   trust
host    all       all   ::1/128        trust
EOF
    if [[ -f "$hba" ]] && cmp -s "$tmp" "$hba"; then
        info "pg_hba.conf already has the VO rules" >&2
        rm -f "$tmp"
        echo unchanged
        return
    fi
    if [[ -f "$hba" ]]; then
        local backup
        backup="$hba.vo-bak-$(date +%Y%m%d-%H%M%S)"
        cp -p "$hba" "$backup"
        info "backed up the previous pg_hba.conf to $backup" >&2
        mode=$(stat -c %a "$hba")   # 600 on RHEL/Arch, 640 on Debian/Ubuntu
    fi
    install -o postgres -g postgres -m "$mode" "$tmp" "$hba"
    rm -f "$tmp"
    info "wrote $hba" >&2
    echo changed
}

# A data-only dump, minus the lines an older server rejects when the dump was made
# by a newer pg_dump: \restrict / \unrestrict (pg_dump 17.6+, unknown to older psql)
# and SET transaction_timeout (PostgreSQL 17+). The rows themselves are unaffected.
filtered_import() {
    sed -E -e '/^\\(un)?restrict /d' -e '/^SET transaction_timeout = /d' "$IMPORT_FILE"
}

wait_until_ready() {
    local _
    for _ in $(seq 1 30); do
        if pg_isready -q -h localhost -p "$DB_PORT"; then
            return 0
        fi
        sleep 1
    done
    die "PostgreSQL is not accepting connections on localhost:$DB_PORT after 30 s.
       Look at: systemctl status $SERVICE; journalctl -u $SERVICE -n 50"
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    [[ -t 0 ]] || die "not a terminal; re-run with --yes to proceed without asking"
    local answer
    read -r -p "Proceed? [y/N] " answer
    [[ "$answer" =~ ^[Yy] ]] || die "aborted, nothing changed"
}

# Debian/Ubuntu: refuse to guess when clusters exist but none is on the GUI's port.
check_debian_clusters() {
    if [[ "$FAMILY" == debian && $NEED_INIT -eq 1 && -n "$OTHER_CLUSTERS" ]]; then
        die "no PostgreSQL cluster is on port $DB_PORT, but these exist:
${OTHER_CLUSTERS}       The GUI connects to port $DB_PORT. Either set port = $DB_PORT in that cluster's
       /etc/postgresql/<ver>/<cluster>/postgresql.conf and run
       systemctl restart postgresql@<ver>-<cluster>, or remove an unused one with
       pg_dropcluster. Then re-run this script."
    fi
}

# Sourced (by a test) rather than run: stop here, with the functions defined.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return 0; fi

if [[ $PROVISION_ONLY -eq 0 ]]; then
    [[ $EUID -eq 0 ]] || die "run as root: sudo $0 $ORIG_ARGS"
    cd /   # runuser postgres cannot chdir into a private home directory

    FAMILY=$(detect_family)
    LOCALE=$(pick_locale)

    NEED_INSTALL=0; package_installed || NEED_INSTALL=1
    # Before installing, the unit or cluster may not exist yet; recomputed after.
    locate_cluster
    check_debian_clusters

    # Port 5432 must be free, unless it is this machine's cluster already running.
    OURS_RUNNING=0
    if [[ $NEED_INIT -eq 0 ]] && systemctl is-active --quiet "$SERVICE"; then OURS_RUNNING=1; fi
    if [[ $OURS_RUNNING -eq 0 ]] && command -v ss >/dev/null \
            && [[ -n "$(ss -Hltn "sport = :$DB_PORT")" ]]; then
        die "something other than $SERVICE is listening on port $DB_PORT:
$(ss -ltnp "sport = :$DB_PORT" 2>/dev/null)"
    fi

    echo "VO PostgreSQL setup on $(hostname) ($FAMILY family)"
    echo "  install packages:  $([[ $NEED_INSTALL -eq 1 ]] && echo yes || echo 'no, already installed')"
    echo "  data directory:    $DATA_DIR ($([[ $NEED_INIT -eq 1 ]] && echo "will be initialised, $LOCALE" || echo 'exists, kept as is'))"
    echo "  pg_hba.conf:       $HBA_FILE"
    echo "                     trust for local socket, 127.0.0.1 and ::1 (previous file backed up)"
    echo "  service:           $SERVICE, started now and at boot"
    echo "  database:          $DB_NAME, role $DB_ROLE, schema from deploy/telescope_db_schema.sql"
    [[ -n "$IMPORT_FILE" ]] && echo "  import:            $IMPORT_FILE"
    [[ -n "$START_RUN_ID" ]] && echo "  next run ID:       at least $START_RUN_ID"
    confirm

    if [[ $NEED_INSTALL -eq 1 ]]; then
        info "installing PostgreSQL"
        install_packages
        locate_cluster
        check_debian_clusters
        if [[ "$FAMILY" == debian && $NEED_INIT -eq 0 ]]; then
            info "the package created cluster $PG_VER/$PG_CLUSTER in $DATA_DIR"
        fi
    elif [[ $NEED_INIT -eq 0 ]]; then
        info "cluster in $DATA_DIR already initialised (PostgreSQL $(cat "$DATA_DIR/PG_VERSION")), keeping it"
    fi

    if [[ $NEED_INIT -eq 1 ]]; then
        info "initialising the cluster in $DATA_DIR"
        init_cluster
        locate_cluster
        [[ $NEED_INIT -eq 0 ]] || die "initialisation finished but no cluster was found in $DATA_DIR"
    fi

    hba_result=$(write_pg_hba)

    if [[ "$hba_result" == changed ]] && systemctl is-active --quiet "$SERVICE"; then
        info "reloading $SERVICE for the new pg_hba.conf"
        systemctl reload "$SERVICE"
    fi
    info "enabling and starting $SERVICE"
    enable_and_start
    wait_until_ready

    listen=$(run_psql -d postgres -Atc 'SHOW listen_addresses')
    [[ "$listen" == localhost ]] || warn "listen_addresses is '$listen', not 'localhost'.
         pg_hba.conf still only admits local connections, so this is not an opening,
         but the original machine used localhost."
fi

# --- step 5: provision -----------------------------------------------------------

info "provisioning role $DB_ROLE and database $DB_NAME"

# CREATE ROLE has no IF NOT EXISTS; the password is set outside the DO block
# because psql does not substitute :'variables' inside dollar quotes.
run_psql -d postgres -v role="$DB_ROLE" -v pw="$VO_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'role')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role') \gexec
ALTER ROLE :"role" LOGIN PASSWORD :'pw';
SQL

# CREATE DATABASE cannot run inside a function or transaction, hence \gexec.
run_psql -d postgres -v db="$DB_NAME" -v role="$DB_ROLE" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER postgres ENCODING %L TEMPLATE template0', :'db', 'UTF8')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE :"db" TO :"role";
SQL

run_psql -d "$DB_NAME" -f - < "$SCHEMA_SQL"

# --- step 6: run history -----------------------------------------------------------

rows=$(run_psql -d "$DB_NAME" -Atc 'SELECT count(*) FROM public.tblrun_info')

if [[ -n "$IMPORT_FILE" || -n "$START_RUN_ID" ]]; then
    if [[ "$rows" -gt 0 ]]; then
        die "tblrun_info already has $rows rows; --import and --start-run-id only apply to an
       empty table, so the run history was left unchanged. (The rest of the setup is done.)"
    fi
    if [[ -n "$IMPORT_FILE" ]]; then
        info "importing $IMPORT_FILE"
        filtered_import | run_psql -d "$DB_NAME" -1 -f -
        rows=$(run_psql -d "$DB_NAME" -Atc 'SELECT count(*) FROM public.tblrun_info')
        [[ "$rows" -gt 0 ]] || die "the import finished but tblrun_info is still empty; is '$IMPORT_FILE' a data dump?"
        info "imported $rows rows"
    fi
    # setval(..., false): the next nextval returns exactly this value.
    run_psql -d "$DB_NAME" -v start="${START_RUN_ID:-1}" -v seq="$SEQUENCE" <<'SQL' >/dev/null
SELECT setval(:'seq', GREATEST(COALESCE(MAX(run_id), 0) + 1, :start), false) FROM public.tblrun_info;
SQL
fi

# --- step 7: report ----------------------------------------------------------------

# The same rule as read_last_run_id in gui/ui_run_metadata.py.
next_run=$(run_psql -d "$DB_NAME" -At <<SQL
SELECT GREATEST(CASE WHEN is_called THEN last_value + 1 ELSE last_value END,
                (SELECT COALESCE(MAX(run_id), 0) + 1 FROM public.tblrun_info))
  FROM $SEQUENCE;
SQL
)
version=$(run_psql -d "$DB_NAME" -Atc 'SHOW server_version')

echo
echo "Done. PostgreSQL $version, database $DB_NAME, $rows run rows, next run ID $next_run."
if [[ $PROVISION_ONLY -eq 0 ]]; then
    echo "Data directory: $DATA_DIR"
    echo "pg_hba.conf:    $HBA_FILE"
    echo "Service:        $SERVICE"
fi
echo "Check it with: python3 deploy/check_deploy.py --role control"
