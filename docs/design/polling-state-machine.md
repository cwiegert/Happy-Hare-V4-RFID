# Design: Polling State Machine

> Engineering reference — not end-user documentation.

---

## Overview

Each NFC gate runs an independent timer-driven polling loop on the Klipper reactor thread. The loop reads a physical tag, resolves a spool ID, feeds the result through a debounce state machine, and fires GCode macros only when state actually changes. The loop self-suspends when Happy Hare already has the spool assigned, then resumes when the gate is cleared.

---

## Timer Heartbeat

```python
self._poll_timer = self.reactor.register_timer(self._poll_timer_event)
```

`register_timer` parks the timer at `reactor.NEVER` — it fires only after an explicit `update_timer` call. Klipper reactor timers fire on the single reactor greenlet thread.

`_poll_timer_event` is the heartbeat:

```python
def _poll_timer_event(self, eventtime):
    if not self._polling:
        return self.reactor.NEVER     # timer parked — no more callbacks
    if self._failed:
        self._polling = False
        return self.reactor.NEVER     # hardware fault — park and stop
    try:
        self._poll()
    except Exception:
        logger.exception(...)         # log full traceback, do not propagate
    return self.reactor.monotonic() + self._poll_interval
```

Key invariants:
- Returns `reactor.NEVER` to park the timer until `update_timer` moves it again.
- Returns `reactor.monotonic() + poll_interval` to reschedule. The next firing is `poll_interval` seconds after the previous call **returns**, not a wall-clock cadence — the poll duration is paid before the next interval starts.
- The bare `except Exception` is intentional: an unhandled exception propagating out of a reactor timer callback kills Klipper. All errors are logged and swallowed so polling continues.
- Note: `_poll()` does not itself raise from I2C errors. `read_tag()` catches all I2C exceptions internally and returns `None`. The outer `except` here catches unexpected errors in the Spoolman or GateState paths.

Starting and stopping polling:

```python
# Start — fire immediately, then reschedule on each return value
self._polling = True
self.reactor.update_timer(self._poll_timer, self.reactor.NOW)

# Stop
self._polling = False
self.reactor.update_timer(self._poll_timer, self.reactor.NEVER)
```

---

## `_poll()` — Full Cycle Logic

```
_poll_timer_event
  └─ _poll()
       ├─ [A] suspend check  (_hh_gate_is_loaded AND current_spool set)
       │    └─ zero miss_count, return — PN532 antenna never pulsed
       ├─ [B] resume detection  (_hh_load_paused was True, now False)
       │    └─ clear GateState, clear _hh_confirmed_spool
       ├─ [C] _check_hh_cleared()  — detect external HH gate map changes
       ├─ [D] reader.read_tag()  — I2C → PN532 → UID hex string or None
       ├─ [E] spoolman.lookup_spool_by_uid()  — UID → spool_id (TTL cached)
       ├─ [F] GateState.process_read(uid_hex, spool_id)  — debounce → event or None
       └─ [G] suppress / dispatch logic  → KlipperInterface.dispatch() or skip
```

Steps [A] and [B] are the suspend/resume gate. Steps [D]–[G] only run when the gate is actively scanning.

### [A] Suspend Check

```python
if self._hh_gate_is_loaded() and self._state.current_spool is not None:
    if not self._hh_load_paused:
        self._hh_load_paused = True
        logger.info("... suspending scan until gate is cleared")
    self._state.miss_count = 0   # prevent spurious REMOVED during suspension
    return                       # ← PN532 never pulsed
```

Both conditions must be true to suspend:
1. `_hh_gate_is_loaded()` — HH's `gate_spool_id[gate] > 0`
2. `_state.current_spool is not None` — NFC has read the tag at least once

Requiring condition 2 ensures the UID is populated in the NFC status before scanning stops. If the gate was seeded from HH at startup with a full cache (see Startup Seeding below), condition 2 is already true before the first physical scan and the gate suspends immediately.

"Suspended" does not mean the timer stops. The timer fires every `poll_interval`. The reactor callback runs. `_poll()` is called. It checks HH status and returns early before `read_tag()`. The PN532 antenna is never pulsed; no I2C traffic occurs. `miss_count` is zeroed each cycle to prevent the debounce counter from accumulating while the tag is physically present but scanning is suppressed.

### [B] Resume Detection

```python
if self._hh_load_paused:
    self._hh_load_paused    = False
    self._state.current_uid   = None
    self._state.current_spool = None
    self._state.miss_count    = 0
    self._hh_confirmed_spool  = None
    logger.info("... filament unloaded; resuming NFC scan")
```

When `_hh_gate_is_loaded()` returns False after the gate was suspended, the full GateState is reset. The next physical tag read fires a fresh `EVENT_CHANGED` dispatch to HH.

---

## GateState — Debounce State Machine

`GateState` is the per-gate single source of truth for what the NFC reader currently sees. It receives every raw read result from `_poll()` and decides whether anything has changed.

```python
class GateState:
    gate              # lane gate number (read-only)
    current_uid       # last confirmed UID, or None if gate empty
    current_spool     # last resolved spool_id, or None
    miss_count        # consecutive missed reads since last tag
    absent_threshold  # misses required before REMOVED fires (from config)
```

### `process_read(uid_hex, spool_id) → event_tuple | None`

```
uid_hex present, same uid+spool as current  → None  (quiet — no GCode)
uid_hex present, uid or spool differs       → EVENT_CHANGED  (spool_id not None)
                                            → EVENT_UID_ONLY (spool_id is None)
uid_hex is None, miss_count < threshold     → None  (still counting)
uid_hex is None, miss_count >= threshold, current_uid was set → EVENT_REMOVED
uid_hex is None, current_uid was None       → None  (already empty, nothing to remove)
```

Event types returned as `(event_type, gate, uid_hex, spool_id)` tuples:

| Constant | uid/spool in tuple | Meaning |
|---|---|---|
| `EVENT_CHANGED` | uid=present, spool=int | Known spool confirmed on this gate |
| `EVENT_UID_ONLY` | uid=present, spool=None | Tag seen but UID not in Spoolman |
| `EVENT_REMOVED` | uid=None, spool=old_spool | Tag gone for `absent_threshold` polls |

`EVENT_UID_ONLY` fires when the Spoolman lookup returns no match — including when `_spoolman is None` (Spoolman not configured). In the no-Spoolman case, every tag read produces `EVENT_UID_ONLY` and calls `_NFC_TAG_NO_SPOOL`, which logs the UID. HH is not updated, but the dispatch still fires.

Removal debounce: a single RF miss (tag momentarily out of range, orientation-sensitive angle, RF noise) does not trigger removal. The tag must be absent for `absent_threshold` consecutive polls. At the default 30 s interval and threshold of 3, removal fires after ~90 s of confirmed absence.

---

## `_check_hh_cleared()`

Called at step [C], runs every active (non-suspended) poll cycle. Detects two cases where HH's gate map diverges from NFC's cached state:

1. **HH cleared the gate** — `gate_spool_id[gate] < 0` (spool ejected, endless-spool exhausted, manual `MMU_GATE_MAP SPOOLID=-1`)
2. **HH has a different spool** — `gate_spool_id[gate] != current_spool` (manual gate map change to a different spool)

Preconditions — both must be true before the check executes:
- `_state.current_spool is not None` — NFC has a spool cached
- `_hh_confirmed_spool == _state.current_spool` — HH previously acknowledged this exact spool

The `_hh_confirmed_spool` guard prevents a dispatch-clear-redispatch loop. When NFC dispatches `EVENT_CHANGED`, `_hh_confirmed_spool` is set immediately (optimistically). HH may not have processed the macro yet. Without the guard: `_check_hh_cleared()` would see HH still empty → clear the cache → `process_read()` fires `EVENT_CHANGED` again → loop. The guard ensures the check only acts after HH has confirmed this spool at least once in a prior dispatch cycle.

When either mismatch is detected, `current_uid`, `current_spool`, and `miss_count` are all cleared so the next tag read fires a fresh `EVENT_CHANGED`.

---

## Startup Seeding

On `klippy:connect`, `_handle_connect()` schedules a one-shot `_delayed_init` timer for 2 seconds later. `_delayed_init` runs PN532 init, then immediately calls `_seed_cache_from_hh()` — directly in Python, with no macro involved.

`_seed_cache_from_hh()` reads HH's current gate map via `mmu.get_status()` and seeds this gate's cache:

```python
# Simplified from _seed_cache_from_hh()
status        = mmu.get_status(eventtime)
hh_spool      = int(status['gate_spool_id'][self._gate])
hh_avail      = status['gate_status'][self._gate]

if hh_spool > 0:
    self._hh_seed_spool_id  = hh_spool
    self._hh_seed_available = bool(hh_avail)

    if self._spoolman is not None:
        uid = self._spoolman.get_uid_for_spool(hh_spool)   # reverse lookup
        if uid:
            self._state.current_uid   = uid         # cache fully populated
            self._state.current_spool = hh_spool    # polling suspends on first cycle
            self._hh_confirmed_spool  = hh_spool    # _check_hh_cleared armed
```

**Two paths depending on whether the Spoolman reverse-UID lookup succeeds:**

**Path 1: Spoolman configured and returns a UID for the spool** — `current_uid`, `current_spool`, and `_hh_confirmed_spool` are all pre-populated. On the first `_poll()`, both suspend conditions are met immediately: `_hh_gate_is_loaded()` is True and `current_spool` is set. The gate goes straight to suspended state without a physical scan. `_NFC_SPOOL_CHANGED` is never fired on restart. `NFC_GATE_STATUS` shows the correct UID immediately.

**Path 2: Spoolman returns no UID, or Spoolman not configured** — only `_hh_seed_spool_id` and `_hh_seed_available` are set. `current_uid`/`current_spool` remain None. Polling proceeds normally. On the first physical tag scan, if the resolved spool matches `_hh_seed_spool_id`:
- `_hh_seed_available == True` → suppress `EVENT_CHANGED` dispatch (HH already knows, cache seeded silently)
- `_hh_seed_available == False` → let dispatch through to set `AVAILABLE=1`

The seed (`_hh_seed_spool_id`) is always cleared after the first `EVENT_CHANGED` poll regardless of match. It fires at most once per Klipper session.

**`NFC_HH_SYNC_CACHE` macro** is a separate user-callable path for manual re-sync. It issues `NFC_GATE GATE=n HH_SYNC=1 SPOOL_ID=<n>` for each lane, which sets `_hh_seed_spool_id` only (no Spoolman reverse-lookup, no state pre-population). Useful when the automatic Python seed failed because HH wasn't initialized yet at `_delayed_init` time.

---

## CLEAR_CACHE Suppress

`NFC_GATE GATE=n CLEAR_CACHE=1` clears the Spoolman TTL cache to force a fresh API query on the next poll. To avoid a spurious `EVENT_CHANGED` when the re-query returns the same spool, two suppression variables are set:

```python
self._suppress_next_dispatch_uid   = self._state.current_uid
self._suppress_next_dispatch_spool = self._state.current_spool
```

On the next poll, after Spoolman resolves the UID:
- Same UID, same spool → suppress dispatch (cache refreshed, nothing changed)
- Same UID, different spool → dispatch `EVENT_CHANGED` (the re-query found a different spool — this is exactly the case CLEAR_CACHE is for)

The suppress pair is consumed on the first matching UID read, regardless of whether the spool matched.

---

## State Variable Reference

| Variable | Type | Meaning |
|---|---|---|
| `_polling` | bool | Timer is active; `_poll_timer_event` will reschedule |
| `_failed` | bool | Reader init failed; polling halted until `INIT=1` |
| `_hh_load_paused` | bool | Suspended: HH + NFC both have spool confirmed |
| `_hh_confirmed_spool` | int\|None | Last spool NFC dispatched and HH acknowledged; gates `_check_hh_cleared` |
| `_hh_seed_spool_id` | int\|None | Spool from HH map at startup; one-shot suppress on first matching scan |
| `_hh_seed_available` | bool | Whether HH had `gate_status=1` for the seeded spool |
| `_suppress_next_dispatch_uid` | str\|None | CLEAR_CACHE: UID to suppress on next matching read |
| `_suppress_next_dispatch_spool` | int\|None | CLEAR_CACHE: spool that must also match to suppress |
| `GateState.current_uid` | str\|None | Last UID confirmed by `process_read()` |
| `GateState.current_spool` | int\|None | Last resolved spool_id confirmed by `process_read()` |
| `GateState.miss_count` | int | Consecutive polls since last tag; resets on any read |
| `GateState.absent_threshold` | int | Misses before `EVENT_REMOVED` fires (from config) |
