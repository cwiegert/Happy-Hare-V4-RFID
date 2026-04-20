# Design: Configuration Architecture

> Engineering reference — not end-user documentation.

---

## File Structure

Three config files, included in this order from `printer.cfg`:

```
[include NFC/nfc_vars.cfg]    → NFCGateDefaults  — base [nfc_gate] section
[include NFC/nfc_macros.cfg]  → GCode macros only (no Python objects)
[include NFC/pn532_i2C.cfg]   → NFCGate × N     — one [nfc_gate laneN] per lane
```

Klipper processes `[include]` directives in order. By the time `pn532_i2C.cfg` is parsed, the `NFCGateDefaults` object for `[nfc_gate]` already exists and is retrievable via `printer.lookup_object('nfc_gate')`.

---

## Klipper Entry Point

The Klipper extras loader maps config section names to filenames in `klippy/extras/`. Section `[nfc_gate]` requires `klippy/extras/nfc_gate.py`. That file is the entry point; all implementation lives in `klippy/extras/nfc_gates/` (a package).

`nfc_gate.py` provides two functions Klipper calls during config load:

```python
def load_config(config):
    # Handles [nfc_gate] — the base defaults section
    del _lane_instances[:]          # clear stale entries on Klipper RESTART
    return NFCGateDefaults(config)

def load_config_prefix(config):
    # Handles [nfc_gate lane0], [nfc_gate lane1], etc.
    defaults = printer.lookup_object('nfc_gate', None)
    gate     = NFCGate(config, defaults)
    _lane_instances.append(gate)    # register for NFC_GATE_STATUS cross-lane view
    return gate
```

`load_config` fires for exactly the bare `[nfc_gate]` section. `load_config_prefix` fires for every `[nfc_gate <anything>]` section — the prefix is `nfc_gate`. `_lane_instances` is a module-level list that all lanes share; it powers `NFC_GATE_STATUS`.

The `load_config_prefix` function also guards against Klipper calling it more than once per section (can happen on RESTART): if a lane with the same name already exists in `_lane_instances`, the list entry is replaced rather than appended.

---

## Inheritance Model

Klipper config sections are independent key-value namespaces. There is no native Klipper inheritance. The three-tier lookup is implemented manually in Python.

**Tier 1 — lane config key**: if the key appears in the `[nfc_gate laneN]` section, that value wins.
**Tier 2 — defaults attribute**: if absent from the lane, the value read by `NFCGateDefaults` from the base `[nfc_gate]` section is used.
**Tier 3 — Python hardcoded fallback**: if `defaults` is None (no base section at all), the hardcoded default in `NFCGate.__init__` is used.

```python
# NFCGate.__init__ reads every parameter with this pattern:
self._poll_interval = config.getfloat(
    'poll_interval',
    d.poll_interval if d else 30.,   # d = defaults object, or None
    minval=1., maxval=3600.
)
```

This pattern means a bare `[nfc_gate laneN]` section with no base `[nfc_gate]` section is valid — all parameters fall back to hardcoded Python defaults.

---

## Parameter Reference

All parameters are defined in `NFCGateDefaults` (from `[nfc_gate]`) and overridable per `[nfc_gate laneN]`.

### Spoolman

| Parameter | Python fallback | Shipped `nfc_vars.cfg` | Type | Bounds |
|---|---|---|---|---|
| `spoolman_url` | `''` | `auto` | str | — |
| `moonraker_url` | `http://127.0.0.1:7125` | _(not set)_ | str | — |
| `spoolman_rfid_key` | `rfid` | `rfid_tag` | str | — |
| `spoolman_timeout` | `5.0` | `5.0` | float | 0.5–30.0 |
| `spoolman_cache_ttl` | `300.0` | `300` | float | 0–3600 |

`spoolman_rfid_key`: The Python fallback is `'rfid'` but the shipped `nfc_vars.cfg` explicitly sets `rfid_tag`. The field name in Spoolman **must match exactly** — case-sensitive.

`spoolman_url: auto` causes `SpoolmanClient` to query Moonraker's `/server/config` endpoint the first time a tag lookup is needed. The discovery URL is cached after the first successful query. If Moonraker doesn't have a `[spoolman]` section, the discovery fails and a warning is logged.

If `spoolman_url` is left empty, `self._spoolman = None`. Tags are still read and UIDs are detected, but every tag read fires `EVENT_UID_ONLY` → `_NFC_TAG_NO_SPOOL`, which logs the UID and prompts the user to register it. HH is not updated with a spool assignment.

### Polling

| Parameter | Python fallback | Shipped default | Type | Bounds |
|---|---|---|---|---|
| `startup_polling` | `-1` | `-1` | int | -1, 0, 1 |
| `startup_poll_delay` | `0.0` | `0.0` | float | 0–3600 |
| `poll_interval` | `30.0` | `30` | float | 1–3600 |
| `absent_threshold` | `3` | `3` | int | 1–255 |

`startup_polling = -1`: polling only starts when `NFC_GATE GATE=n READ=1` is issued manually.
`startup_polling = 1`: `_delayed_init` arms the poll timer after PN532 init succeeds, delayed by `startup_poll_delay`.
`startup_poll_delay`: stagger per-lane startup. With 4 lanes and delays of 0, 2, 4, 6 seconds, init and first polls spread across 6 seconds rather than all firing simultaneously.

`absent_threshold` × `poll_interval` = seconds before `EVENT_REMOVED` fires. Default: 3 × 30 = 90 seconds.

### Hardware Timing

| Parameter | Python fallback | Shipped default | Type | Bounds |
|---|---|---|---|---|
| `i2c_address` | `0x24` (36) | `36` | int | 0–127 |
| `transceive_delay` | `0.250` | `0.250` | float | 0.05–2.0 |
| `crc_delay` | `0.050` | `0.050` | float | 0.005–1.0 |

`transceive_delay`: passed as the timeout to `_transceive()` for `InListPassiveTarget`. The PN532 scans the RF field until a tag is found or this timeout expires. 250 ms covers the PN532's internal no-tag timeout safely. Values below 100 ms may drop tags that are slightly off-axis from the antenna.

`crc_delay`: used as the minimum timeout for the `InRelease` `_transceive()` call (clamped to ≥ 200 ms inside `_release_current_target`). In practice the PN532 responds to InRelease in a few milliseconds — 50 ms is conservative.

### Logging

| Parameter | Python fallback | Shipped default | Type | Bounds |
|---|---|---|---|---|
| `debug` | `2` | `2` | int | 0–4 |
| `log_file` | `''` | `nfc_reader.log` | str | — |
| `console_output` | `False` | `False` | bool | — |
| `console_log_level` | `warning` | `2` | str or int | error/warning/info/debug or 1–4 |
| `low_level_debug` | `False` | `False` | bool | — |

Both integer and string spellings are accepted for `debug` and `console_log_level` (e.g. `debug: 3` and `debug: info` are equivalent). See error-logging.md for the full level mapping.

---

## Per-Lane Override Example

Any key from `nfc_vars.cfg` can be overridden in a lane section:

```ini
[nfc_gate lane2]
mmu_gate:           2
i2c_mcu:            lane2
i2c_bus:            i2c3_PB3_PB4
debug:              3             ; verbose logging on this lane only
startup_polling:    1             ; auto-start
startup_poll_delay: 4.0           ; 4 s after lane0's 0 s, lane1's 2 s
poll_interval:      10            ; faster for bench testing
```

Only keys explicitly listed in the lane section take effect. All others inherit from `[nfc_gate]`.

---

## SpoolmanClient Lifecycle

`SpoolmanClient` is constructed inside `NFCGate.__init__` when `spoolman_url` is non-empty:

```python
if spoolman_url:
    self._spoolman = SpoolmanClient(
        spoolman_url, rfid_key=spoolman_rfid_key,
        timeout=spoolman_timeout, cache_ttl=spoolman_cache_ttl,
        debug=self._debug, moonraker_url=moonraker_url)
else:
    self._spoolman = None
```

The `SpoolmanClient` instance is **per-lane, not shared**. Each lane has its own:
- URL resolution state (`_base_url`)
- TTL cache (`_cache` dict, keyed by normalized UID)
- Circuit breaker state (`_cb_failures`, `_cb_backoff_until`)

When `_spoolman is None`: tags are still read and `process_read(uid_hex, None)` is called, returning `EVENT_UID_ONLY` for every tag. `_NFC_TAG_NO_SPOOL` fires and logs the UID. HH `MMU_GATE_MAP` is not called.

When `_spoolman` is set but Spoolman is unreachable: the circuit breaker opens after 3 consecutive failures and backs off for 60 seconds. During the backoff, `lookup_spool_by_uid()` returns `None` immediately. The behavior is the same as `_spoolman is None` — `EVENT_UID_ONLY` fires, HH is not updated.
