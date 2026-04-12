#!/usr/bin/env python3
# pn532_scan.py
#
# Standalone PN532 I2C scanner for Raspberry Pi.
# No Klipper, no MMU, no Spoolman — just the PN532.
#
# Wiring (Pi GPIO header):
#   PN532 VCC → Pin 1  (3.3V)
#   PN532 GND → Pin 6  (GND)
#   PN532 SDA → Pin 3  (GPIO2, I2C1 SDA)
#   PN532 SCL → Pin 5  (GPIO3, I2C1 SCL)
#
# PN532 must be in I2C mode (DIP switch / solder jumper).
#
# Prerequisites:
#   sudo apt install python3-smbus2
#   sudo raspi-config → Interface Options → I2C → Enable
#
# Usage:
#   python3 pn532_scan.py [--bus N] [--address 0x24] [--debug] [--scan-bus]

import argparse
import sys
import time

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:
    print("ERROR: smbus2 is not installed.")
    print("       Run:  sudo apt install python3-smbus2")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# PN532 constants
# ─────────────────────────────────────────────────────────────────────────────

_TFI_HOST  = 0xD4
_TFI_PN532 = 0xD5

_CMD_GETFIRMWAREVERSION  = 0x02
_CMD_SAMCONFIGURATION    = 0x14
_CMD_INLISTPASSIVETARGET = 0x4A
_CMD_INRELEASE           = 0x52

_MAX_RESPONSE = 32


# ─────────────────────────────────────────────────────────────────────────────
# I2C helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_frame(cmd_and_params):
    data   = [_TFI_HOST] + list(cmd_and_params)
    length = len(data)
    lcs    = (-length) & 0xFF
    dcs    = (-sum(data)) & 0xFF
    return [0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]


def _check_frame(raw, expected_cmd_resp):
    if len(raw) < 8:
        return None
    if raw[0] != 0x01:
        return None
    if raw[1] != 0x00 or raw[2] != 0x00 or raw[3] != 0xFF:
        return None
    if raw[6] != _TFI_PN532:
        return None
    if raw[7] != expected_cmd_resp:
        return None
    length  = raw[4]
    payload = list(raw[8: 8 + length - 2])
    return payload


def i2c_write(bus, address, data):
    msg = i2c_msg.write(address, data)
    bus.i2c_rdwr(msg)


def i2c_read(bus, address, read_len):
    msg = i2c_msg.read(address, read_len)
    bus.i2c_rdwr(msg)
    return bytes(msg)


# ─────────────────────────────────────────────────────────────────────────────
# PN532 protocol
# ─────────────────────────────────────────────────────────────────────────────

def pn532_send(bus, address, cmd_and_params, debug):
    frame = _build_frame(cmd_and_params)
    if debug:
        print(f"  TX  cmd=0x{cmd_and_params[0]:02X}  frame={' '.join('%02X' % b for b in frame)}")
    i2c_write(bus, address, frame)


def pn532_recv(bus, address, expected_cmd_resp, read_len=_MAX_RESPONSE,
               timeout=1.0, poll_interval=0.005, debug=False):
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw1 = i2c_read(bus, address, 1)
        status = raw1[0] if raw1 else 0xFF
        if debug:
            print(f"  poll  status=0x{status:02X}")
        if status == 0x01:
            raw = i2c_read(bus, address, read_len)
            payload = _check_frame(bytearray(raw), expected_cmd_resp)
            if debug:
                print(f"  RX    raw={' '.join('%02X' % b for b in raw)}")
                if payload is not None:
                    print(f"  payload={' '.join('%02X' % b for b in payload)}")
                else:
                    print(f"  frame parse failed (expected cmd=0x{expected_cmd_resp:02X})")
            return payload
        time.sleep(poll_interval)
    if debug:
        print(f"  timeout waiting for ready")
    return None


def pn532_init(bus, address, debug):
    """Wake the PN532 and send SAMConfiguration. Returns True on success."""
    for attempt in range(3):
        wait = 0.150 if attempt == 0 else 0.075
        if debug:
            print(f"Wake attempt {attempt+1}/3 (wait={wait*1000:.0f}ms)")
        try:
            pn532_send(bus, address, [_CMD_GETFIRMWAREVERSION], debug)
            time.sleep(wait)
            payload = pn532_recv(bus, address, 0x03, read_len=15,
                                 timeout=0.500, debug=debug)
            if payload and len(payload) >= 4:
                print(f"  PN532 OK — IC=0x{payload[0]:02X} Ver={payload[1]}.{payload[2]}")
                break
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}")
        time.sleep(0.050)
    else:
        return False

    # SAMConfiguration: Normal mode, no timeout, no IRQ
    pn532_send(bus, address, [_CMD_SAMCONFIGURATION, 0x01, 0x00, 0x00], debug)
    pn532_recv(bus, address, 0x15, read_len=12, timeout=0.200, debug=debug)
    return True


def pn532_read_tag(bus, address, scan_timeout=0.350, debug=False):
    """Return UID hex string if a tag is present, else None."""
    pn532_send(bus, address, [_CMD_INLISTPASSIVETARGET, 0x01, 0x00], debug)
    payload = pn532_recv(bus, address, 0x4B, read_len=_MAX_RESPONSE,
                         timeout=scan_timeout + 0.100, debug=debug)
    if not payload or payload[0] == 0:
        return None
    if len(payload) < 7:
        return None
    nfcid_len = payload[5]
    if nfcid_len == 0 or len(payload) < 6 + nfcid_len:
        return None
    uid = payload[6:6 + nfcid_len]
    uid_hex = ''.join('{:02X}'.format(b) for b in uid)

    # Release target
    pn532_send(bus, address, [_CMD_INRELEASE, 0x00], debug)
    pn532_recv(bus, address, 0x53, read_len=12, timeout=0.200, debug=debug)

    return uid_hex


# ─────────────────────────────────────────────────────────────────────────────
# Bus scan
# ─────────────────────────────────────────────────────────────────────────────

def scan_bus(bus_num):
    print(f"Scanning I2C bus {bus_num}...")
    found = []
    with SMBus(bus_num) as bus:
        for addr in range(0x03, 0x78):
            try:
                msg = i2c_msg.read(addr, 1)
                bus.i2c_rdwr(msg)
                found.append(addr)
                print(f"  0x{addr:02X}  ({addr})")
            except OSError:
                pass
    if not found:
        print("  No devices found.")
    else:
        print(f"\n{len(found)} device(s) found.")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='PN532 I2C scanner for Raspberry Pi')
    parser.add_argument('--bus',      type=int,   default=1,      help='I2C bus (default: 1)')
    parser.add_argument('--address',  default='0x24',             help='PN532 address (default: 0x24)')
    parser.add_argument('--poll',     type=float, default=2.0,    help='Poll interval seconds (default: 2.0)')
    parser.add_argument('--debug',    action='store_true',        help='Show full I2C trace')
    parser.add_argument('--scan-bus', action='store_true',        help='Scan bus for devices and exit')
    parser.add_argument('--once',     action='store_true',        help='Exit after first tag read')
    args = parser.parse_args()

    address = int(args.address, 16) if args.address.startswith('0x') else int(args.address)

    if args.scan_bus:
        scan_bus(args.bus)
        return

    print(f"PN532 scanner  bus={args.bus}  address=0x{address:02X}  poll={args.poll}s")
    print("Ctrl+C to stop\n")

    with SMBus(args.bus) as bus:
        print("Initialising PN532...")
        if not pn532_init(bus, address, args.debug):
            print("\nERROR: PN532 did not respond.")
            print(f"  Run with --scan-bus to check bus {args.bus}")
            print("  Check I2C mode jumper, wiring, and 3.3V power")
            sys.exit(1)
        print("Ready.\n")

        last_uid = None
        try:
            while True:
                uid = pn532_read_tag(bus, address, debug=args.debug)
                if uid and uid != last_uid:
                    print(f"TAG  {uid}")
                    last_uid = uid
                    if args.once:
                        break
                elif not uid and last_uid:
                    print("removed")
                    last_uid = None
                time.sleep(args.poll)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == '__main__':
    main()
