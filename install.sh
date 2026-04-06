#!/bin/bash
# =============================================================================
# EMU NFC Gate Reader — Install Script
# =============================================================================
# 1. Symlinks the Python extras into Klipper's extras directory so that
#    `git pull` + Klipper restart is all that is needed to update the code.
#
# 2. Installs config files into ~/printer_data/config/NFC/:
#    - Read-only files (macros, hardware configs) are copied fresh every run.
#    - nfc_vars.cfg (user settings) is copied from the repo template ONLY on
#      first install.  On subsequent runs it is preserved from the previous NFC/
#      directory so your Spoolman URL and other settings are never overwritten.
#    - If an NFC/ directory already exists it is renamed to NFC_<timestamp>
#      before the new one is created, giving you a timestamped backup.
#
# Usage:
#   bash install.sh
#
# Run from the cloned repo directory, or from anywhere — the script resolves
# its own location automatically.
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLIPPER_EXTRAS="${HOME}/klipper/klippy/extras"
PRINTER_CONFIG="${HOME}/printer_data/config"
NFC_CONFIG_DIR="${PRINTER_CONFIG}/NFC"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ── Verify Klipper is present ─────────────────────────────────────────────────
if [ ! -d "${KLIPPER_EXTRAS}" ]; then
    echo "ERROR: Klipper extras directory not found at ${KLIPPER_EXTRAS}"
    echo "       Is Klipper installed? Expected: ~/klipper/klippy/extras/"
    exit 1
fi

# ── Verify printer config directory is present ────────────────────────────────
if [ ! -d "${PRINTER_CONFIG}" ]; then
    echo "ERROR: Klipper config directory not found at ${PRINTER_CONFIG}"
    echo "       Expected: ~/printer_data/config/"
    exit 1
fi

# ── Symlink Python extras into Klipper ───────────────────────────────────────
echo "Linking nfc_gates package..."
ln -sfn "${REPO_DIR}/klippy/extras/nfc_gates" "${KLIPPER_EXTRAS}/nfc_gates"

echo "Linking nfc_gate.py..."
ln -sfn "${REPO_DIR}/klippy/extras/nfc_gate.py" "${KLIPPER_EXTRAS}/nfc_gate.py"

# ── Back up existing NFC config directory ────────────────────────────────────
BACKUP_VARS=""
if [ -d "${NFC_CONFIG_DIR}" ]; then
    BACKUP_DIR="${PRINTER_CONFIG}/NFC_${TIMESTAMP}"
    echo "Backing up existing NFC config to $(basename "${BACKUP_DIR}")..."
    mv "${NFC_CONFIG_DIR}" "${BACKUP_DIR}"
    # Remember the old nfc_vars.cfg path so we can restore it below
    if [ -f "${BACKUP_DIR}/nfc_vars.cfg" ]; then
        BACKUP_VARS="${BACKUP_DIR}/nfc_vars.cfg"
    fi
fi

# ── Create fresh NFC config directory ────────────────────────────────────────
mkdir -p "${NFC_CONFIG_DIR}"

# ── Copy read-only config files (refreshed on every install / update) ─────────
echo "Copying config files to ${NFC_CONFIG_DIR}..."
cp "${REPO_DIR}/config/nfc_macros.cfg"               "${NFC_CONFIG_DIR}/nfc_macros.cfg"
cp "${REPO_DIR}/config/nfc_gates_spi_rc522.cfg"      "${NFC_CONFIG_DIR}/nfc_gates_spi_rc522.cfg"
cp "${REPO_DIR}/config/nfc_gates_i2c_pn532_pico.cfg" "${NFC_CONFIG_DIR}/nfc_gates_i2c_pn532_pico.cfg"
cp "${REPO_DIR}/config/nfc_gate_i2c_pn532.cfg"       "${NFC_CONFIG_DIR}/nfc_gate_i2c_pn532.cfg"

# ── nfc_vars.cfg — restore user's copy or install template ───────────────────
if [ -n "${BACKUP_VARS}" ]; then
    cp "${BACKUP_VARS}" "${NFC_CONFIG_DIR}/nfc_vars.cfg"
    echo "Restored your nfc_vars.cfg from backup."
else
    cp "${REPO_DIR}/config/nfc_vars.cfg" "${NFC_CONFIG_DIR}/nfc_vars.cfg"
    echo "Installed nfc_vars.cfg template — edit this file to set your Spoolman URL."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Install complete."
echo ""
echo "  Python extras (symlinked — auto-updates with git pull):"
echo "    ${KLIPPER_EXTRAS}/nfc_gates  ->  ${REPO_DIR}/klippy/extras/nfc_gates"
echo "    ${KLIPPER_EXTRAS}/nfc_gate.py  ->  ${REPO_DIR}/klippy/extras/nfc_gate.py"
echo ""
echo "  Config files copied to:"
echo "    ${NFC_CONFIG_DIR}/"
echo "      nfc_vars.cfg                   ← edit this: set spoolman_url"
echo "      nfc_macros.cfg                 ← do not edit"
echo "      nfc_gates_spi_rc522.cfg        ← Mode 1: SPI/RC522 on Pico"
echo "      nfc_gates_i2c_pn532_pico.cfg   ← Mode 2: I2C/PN532 on Pico"
echo "      nfc_gate_i2c_pn532.cfg         ← Mode 3: I2C/PN532 on EBB42"
echo ""

if [ -n "${BACKUP_VARS}" ]; then
    echo "  Previous config backed up to:"
    echo "    $(dirname "${BACKUP_VARS}")/"
    echo ""
fi

echo "Next steps (first install only):"
echo ""
echo "  1. Edit ~/printer_data/config/NFC/nfc_vars.cfg"
echo "     Set spoolman_url to your Spoolman instance."
echo ""
echo "  2. Add includes to printer.cfg — pick ONE hardware config:"
echo ""
echo "     [include NFC/nfc_vars.cfg]"
echo "     [include NFC/nfc_macros.cfg]"
echo "     [include NFC/nfc_gates_spi_rc522.cfg]        # Mode 1: SPI/RC522 on Pico"
echo "     — or —"
echo "     [include NFC/nfc_vars.cfg]"
echo "     [include NFC/nfc_macros.cfg]"
echo "     [include NFC/nfc_gates_i2c_pn532_pico.cfg]   # Mode 2: I2C/PN532 on Pico"
echo "     — or —"
echo "     [include NFC/nfc_vars.cfg]"
echo "     [include NFC/nfc_macros.cfg]"
echo "     [include NFC/nfc_gate_i2c_pn532.cfg]         # Mode 3: I2C/PN532 on EBB42"
echo ""
echo "  3. Restart Klipper:"
echo "     sudo systemctl restart klipper"
echo ""
echo "  4. Add the Moonraker update manager section to moonraker.conf:"
cat <<'EOF'

# ── paste into moonraker.conf ─────────────────────────────────────────────────
[update_manager emu_nfc_reader]
type: git_repo
path: ~/emu-nfc-reader
origin: YOUR_REPO_URL_HERE
primary_branch: main
managed_services: klipper
install_script: install.sh
# ─────────────────────────────────────────────────────────────────────────────
EOF
