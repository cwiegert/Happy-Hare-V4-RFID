#!/usr/bin/env python3
"""
tests/lookup_uid.py
====================
Live Spoolman UID lookup — queries a real Spoolman instance.

Usage (from project root):
    python3 tests/lookup_uid.py <uid> [spoolman_url] [rfid_field_name]

Examples:
    python3 tests/lookup_uid.py A3F200CC
    python3 tests/lookup_uid.py A3F200CC http://192.168.1.50:7912
    python3 tests/lookup_uid.py A3F200CC http://192.168.1.50:7912 RFID_tag

If spoolman_url is omitted it defaults to http://mainsailos.local:7912.
If rfid_field_name is omitted it defaults to 'rfid_tag'.
The UID is normalised automatically — colons, hyphens, spaces, and
lowercase are all accepted (e.g. "a3:f2:00:cc" works fine).
"""

import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG, format='  %(message)s')

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                '..', 'klippy', 'extras', 'nfc_gates'))

from spoolman_client import SpoolmanClient

DEFAULT_URL      = 'http://192.168.0.73:7912'
DEFAULT_RFID_KEY = 'rfid_tag'

uid      = sys.argv[1] if len(sys.argv) > 1 else input('UID: ').strip()
url      = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_URL
rfid_key = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_RFID_KEY

print(f'\nQuerying {url} for UID {uid!r} (field: {rfid_key!r}) ...\n')

client = SpoolmanClient(url, rfid_key=rfid_key, debug=2)
spool_id = client.lookup_spool_by_uid(uid)

print()
if spool_id is not None:
    print(f'spool_id: {spool_id}')
else:
    print(f"NOT FOUND — check that the {rfid_key!r} extra field on the spool "
          f"record is set to: {SpoolmanClient._normalise_uid(uid)}")
