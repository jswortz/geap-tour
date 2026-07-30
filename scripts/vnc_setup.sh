#!/usr/bin/env bash
# vnc_setup.sh — headless VNC + X virtual framebuffer + window manager so an
# operator can drive a LIVE GCP Console in a real browser and photograph it for
# the GEAP agent-evaluation evidence.
#
# Idempotent: safe to re-run. NEVER uses sudo. Starts (only if not already
# running) Xvfb on display :1, a fluxbox window manager, and x11vnc bound to
# localhost:5901 with password auth.
#
# Typical flow:
#   bash scripts/vnc_setup.sh                       # start the stack (this file)
#   ssh -L 5901:localhost:5901 <this-host>          # tunnel from your laptop
#   # open a VNC viewer -> localhost:5901, sign in to the GCP Console ONCE
#   DISPLAY=:1 python3 scripts/capture_eval_console.py
#
# Nothing here requires elevated privileges; all state lives under $HOME.

set -uo pipefail

DISPLAY_NUM=":1"
VNC_PORT="5901"
GEOMETRY="1920x1080x24"
VNC_DIR="${HOME}/.vnc"
VNC_PASSWD="${VNC_DIR}/passwd"

log()     { printf '  %s\n' "$*"; }
section() { printf '\n=== %s ===\n' "$*"; }

section "GEAP eval — headless VNC setup (display ${DISPLAY_NUM}, port ${VNC_PORT})"

# --- 1. VNC password (generated once, stored hashed) ------------------------
mkdir -p "${VNC_DIR}"
chmod 700 "${VNC_DIR}" 2>/dev/null || true

GENERATED_PW=""
if [[ -f "${VNC_PASSWD}" ]]; then
    log "VNC password already present at ${VNC_PASSWD} (leaving it as-is)."
else
    if command -v openssl >/dev/null 2>&1; then
        GENERATED_PW="$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | cut -c1-8)"
    else
        GENERATED_PW="$(od -An -tx1 -N4 /dev/urandom | tr -d ' \n' | cut -c1-8)"
    fi
    [[ -z "${GENERATED_PW}" ]] && GENERATED_PW="geap$(date +%s | tail -c 5)"
    # x11vnc -storepasswd <password> <file> writes the obfuscated VNC passwd file.
    if x11vnc -storepasswd "${GENERATED_PW}" "${VNC_PASSWD}" >/dev/null 2>&1; then
        chmod 600 "${VNC_PASSWD}" 2>/dev/null || true
        log "Generated a new VNC password and stored it (hashed) at ${VNC_PASSWD}."
    else
        log "WARNING: could not store VNC password with x11vnc -storepasswd."
        GENERATED_PW=""
    fi
fi

# --- 2. Xvfb virtual framebuffer --------------------------------------------
if pgrep -f "Xvfb ${DISPLAY_NUM}" >/dev/null 2>&1; then
    log "Xvfb already running on ${DISPLAY_NUM} — skipping."
else
    Xvfb "${DISPLAY_NUM}" -screen 0 "${GEOMETRY}" >/tmp/geap-xvfb.log 2>&1 &
    sleep 1
    if pgrep -f "Xvfb ${DISPLAY_NUM}" >/dev/null 2>&1; then
        log "Started Xvfb on ${DISPLAY_NUM} (${GEOMETRY}). Log: /tmp/geap-xvfb.log"
    else
        log "WARNING: Xvfb did not start; see /tmp/geap-xvfb.log"
    fi
fi

# --- 3. fluxbox window manager ----------------------------------------------
if pgrep -x fluxbox >/dev/null 2>&1; then
    log "fluxbox window manager already running — skipping."
else
    DISPLAY="${DISPLAY_NUM}" fluxbox >/tmp/geap-fluxbox.log 2>&1 &
    sleep 1
    if pgrep -x fluxbox >/dev/null 2>&1; then
        log "Started fluxbox on ${DISPLAY_NUM}. Log: /tmp/geap-fluxbox.log"
    else
        log "WARNING: fluxbox did not start; see /tmp/geap-fluxbox.log"
    fi
fi

# --- 4. x11vnc server (localhost only) --------------------------------------
if pgrep -f "x11vnc.*-rfbport ${VNC_PORT}" >/dev/null 2>&1; then
    log "x11vnc already serving on localhost:${VNC_PORT} — skipping."
else
    if [[ -f "${VNC_PASSWD}" ]]; then
        # -bg daemonizes x11vnc itself, so no trailing & is needed.
        x11vnc -display "${DISPLAY_NUM}" -localhost -rfbport "${VNC_PORT}" \
            -rfbauth "${VNC_PASSWD}" -forever -shared -bg \
            -o /tmp/geap-x11vnc.log >/dev/null 2>&1
    else
        log "No password file; falling back to -nopw (still -localhost only)."
        x11vnc -display "${DISPLAY_NUM}" -localhost -rfbport "${VNC_PORT}" \
            -nopw -forever -shared -bg \
            -o /tmp/geap-x11vnc.log >/dev/null 2>&1
    fi
    sleep 1
    if pgrep -f "x11vnc.*-rfbport ${VNC_PORT}" >/dev/null 2>&1; then
        log "Started x11vnc on localhost:${VNC_PORT}. Log: /tmp/geap-x11vnc.log"
    else
        log "WARNING: x11vnc did not start; see /tmp/geap-x11vnc.log"
    fi
fi

# --- 5. Operator instructions -----------------------------------------------
section "Connect from your workstation"
cat <<EOF
  1. Open an SSH tunnel from your LOCAL machine (keep it running):
         ssh -L ${VNC_PORT}:localhost:${VNC_PORT} <this-host>
  2. Point a VNC viewer at:
         localhost:${VNC_PORT}
EOF
if [[ -n "${GENERATED_PW}" ]]; then
    printf '     VNC password (shown once — save it now): %s\n' "${GENERATED_PW}"
else
    printf '     Use the existing VNC password stored in %s\n' "${VNC_PASSWD}"
fi
cat <<EOF
  3. In the VNC desktop, sign in to the GCP Console ONCE. The capture script
     uses a persistent Chromium profile (~/.geap-eval-chrome), so your Google
     auth is cached and reused on later headed runs.

EOF

section "Capture screenshots"
cat <<EOF
  LIVE console capture (needs the VNC login above). Point DISPLAY at the
  virtual framebuffer:
         DISPLAY=${DISPLAY_NUM} python3 scripts/capture_eval_console.py
     (or:  export DISPLAY=${DISPLAY_NUM}   then run the script)
EOF

exit 0
