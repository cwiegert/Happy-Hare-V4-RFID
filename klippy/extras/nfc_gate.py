# klippy/extras/nfc_gate.py
#
# Klipper entry point for [nfc_gate] and [nfc_gate laneN] config sections.
# Per-lane I2C/PN532 path — one PN532 per EBB42 lane board.
#
# All implementation lives in the nfc_gates/ package.
# This file exists only because Klipper maps config section names to filenames
# in klippy/extras/ — [nfc_gate] requires a file called nfc_gate.py here.
#
# Install
# ───────
# Run install.sh — it symlinks this file and the nfc_gates/ package into
# ~/klipper/klippy/extras/ automatically.

from nfc_gates.NFC_manager import NFCGate, NFCGateDefaults, _lane_instances


def load_config(config):
    # Handles the base [nfc_gate] section — shared defaults only, no hardware.
    return NFCGateDefaults(config)


def load_config_prefix(config):
    # Handles [nfc_gate lane0], [nfc_gate lane1], etc.
    printer  = config.get_printer()
    defaults = printer.lookup_object('nfc_gate', None)
    gate     = NFCGate(config, defaults)
    _lane_instances.append(gate)
    return gate
