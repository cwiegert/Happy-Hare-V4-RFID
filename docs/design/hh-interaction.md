# Design: Happy Hare ↔ NFC_Manager Interaction

> Engineering reference — not end-user documentation.

---

## Interaction Model: Unidirectional Push + Pull Status

NFC does not have a direct Python API to Happy Hare. HH is a separate Klipper extra with its own object namespace. NFC interacts with HH in two ways:

```
NFC → HH:   GCode macro dispatch  (_NFC_SPOOL_CHANGED, _NFC_SPOOL_REMOVED, _NFC_TAG_NO_SPOOL)
HH → NFC:   none — NFC polls HH status directly via mmu.get_status()
```

There is no callback registration, no event subscription, no shared queue. NFC pushes to HH by running GCode; NFC reads from HH by calling `mmu.get_status()` at the start of each poll cycle. HH never calls into NFC.

---

## NFC → HH: GCode Macro Dispatch

`KlipperInterface.dispatch()` schedules a GCode script via `reactor.register_callback()`, which defers execution to the next reactor iteration:

```
EVENT_CHANGED   → "_NFC_SPOOL_CHANGED GATE={gate} SPOOL_ID={spool_id} UID={uid}"
EVENT_UID_ONLY  → "_NFC_TAG_NO_SPOOL GATE={gate} UID={uid}"
EVENT_REMOVED   → "_NFC_SPOOL_REMOVED GATE={gate}"
```

These macros are defined in `nfc_macros.cfg` and are the only user-editable integration point. If a HH version uses different command syntax, only the macro bodies need updating — the NFC Python layer is unaffected.

### `_NFC_SPOOL_CHANGED`

```gcode
MMU_GATE_MAP GATE={gate} SPOOLID={spool_id} AVAILABLE=1 SYNC=1 QUIET=1
MMU_GATE_MAP GATE={gate} APPLY=1
```

`SYNC=1` tells HH to synchronize the assignment to Spoolman. `AVAILABLE=1` marks the gate as having filament loaded. `APPLY=1` pushes the updated map into the active print state. NFC also calls `_spoolman.update_spool_location(spool_id, gate)` directly before dispatching, setting the Spoolman `location` field to `MMU_GATE_<n>`.

### `_NFC_SPOOL_REMOVED`

```gcode
{% set mmu_action = printer.mmu.action | default("") | lower %}
{% if "load" in mmu_action or "unload" in mmu_action or "homing" in mmu_action %}
    { action_respond_info("... ignoring removal.") }
{% else %}
    MMU_GATE_MAP GATE={gate} SPOOLID=-1 AVAILABLE=0 SYNC=1 QUIET=1
    MMU_GATE_MAP GATE={gate} APPLY=1
{% endif %}
```

**MMU action guard:** before clearing the gate, the macro reads `printer.mmu.action`. If the MMU is currently loading, unloading, or homing, the removal event is silently ignored and logged. This prevents a tag momentarily leaving the antenna's read range during filament movement from triggering a spurious gate clear mid-operation. The removal will be retried on the next poll cycle if the tag is still absent.

NFC also calls `_spoolman.clear_spool_location(spool_id)` to clear the `location` field in Spoolman.

### `_NFC_TAG_NO_SPOOL`

```gcode
{ action_respond_info("NFC gate %d: tag UID %s is not registered in Spoolman.\n..."
    % (gate, uid, uid)) }
```

Logs the UID to the console and prompts the user to register it. Does not call `MMU_GATE_MAP`. No HH state changes.

---

## HH → NFC: Status Polling

NFC reads HH state by calling `mmu.get_status()` directly on the HH Python object. This is a synchronous in-process call — no GCode queue, no I2C:

```python
mmu = self.printer.lookup_object('mmu', None)
if mmu is None:
    return False
status         = mmu.get_status(self.reactor.monotonic())
gate_spool_ids = status.get('gate_spool_id', [])
spool_id       = int(gate_spool_ids[self._gate] or -1)
```

Used in two places:

**`_hh_gate_is_loaded()`** — returns `True` when `gate_spool_id[gate] > 0`. Called at the top of every `_poll()` to decide whether to suspend scanning.

**`_check_hh_cleared()`** — compares NFC's cached spool against HH's current value. Detects two divergence cases:
- HH cleared the gate: `gate_spool_id[gate] < 0`
- HH has a different spool: `gate_spool_id[gate] != current_spool`

If `mmu` is not registered (HH not installed), `lookup_object` returns `None` and both functions return safe defaults — `_hh_gate_is_loaded()` returns `False` (polling never suspends), `_check_hh_cleared()` returns without action.

---

## Startup Seeding

On `klippy:connect`, `_delayed_init` runs 2 seconds later and calls `_seed_cache_from_hh()` — directly in Python, not via a macro. This reads HH's current gate map and pre-populates the lane cache before the first poll fires.

```python
# Simplified from _seed_cache_from_hh()
status   = mmu.get_status(eventtime)
hh_spool = int(status['gate_spool_id'][self._gate])
hh_avail = status['gate_status'][self._gate]

if hh_spool > 0:
    self._hh_seed_spool_id  = hh_spool
    self._hh_seed_available = bool(hh_avail)

    if self._spoolman is not None:
        uid = self._spoolman.get_uid_for_spool(hh_spool)  # Spoolman reverse-lookup
        if uid:
            # Full cache population — polling suspends immediately
            self._state.current_uid   = uid
            self._state.current_spool = hh_spool
            self._hh_confirmed_spool  = hh_spool
```

When the Spoolman reverse-lookup succeeds: the gate goes directly to the "suspended" state on the first `_poll()` cycle (both conditions met: `_hh_gate_is_loaded()` True and `current_spool` set). `NFC_GATE_STATUS` shows the correct UID immediately, before any physical scan.

When the Spoolman lookup fails (no UID in Spoolman, or Spoolman not configured): only `_hh_seed_spool_id` is set. Polling proceeds normally. On the first physical scan that resolves to the seeded spool, the dispatch is suppressed (HH already knows).

**`NFC_HH_SYNC_CACHE` macro** is a separate user-callable path — it calls `NFC_GATE GATE=n HH_SYNC=1 SPOOL_ID=<n>` for each lane, which sets `_hh_seed_spool_id` only. No Spoolman reverse-lookup, no state pre-population. Its comment says: "startup seeding happens automatically in Python (`_delayed_init`). This macro exists for user-triggered re-sync and for cases where the Python seed failed (e.g. HH was not yet initialised at PN532 init time)."

---

## Suspend/Resume Cycle: Full Trace

```
1. Gate 0 is empty. Polling runs every 30 s. read_tag() fires each cycle.
   GateState: uid=None spool=None misses=0

2. User loads a spool. On next poll, NFC reads the tag.
   read_tag() → uid_hex = "A3F200CC"

3. SpoolmanClient.lookup_spool_by_uid("A3F200CC") → spool_id = 42
   (HTTP request if cache cold, cache hit if warm)

4. GateState.process_read("A3F200CC", 42) → EVENT_CHANGED
   GateState: uid="A3F200CC" spool=42 misses=0

5. Not suppressed (no seed match, no CLEAR_CACHE pending).
   _spoolman.update_spool_location(42, gate=0)   → Spoolman: location = "MMU_GATE_0"
   KlipperInterface.dispatch(EVENT_CHANGED, 0, "A3F200CC", 42)
   _hh_confirmed_spool = 42   (set immediately — optimistic)

6. reactor.register_callback fires → gcode.run_script:
       _NFC_SPOOL_CHANGED GATE=0 SPOOL_ID=42 UID=A3F200CC
   Macro executes:
       MMU_GATE_MAP GATE=0 SPOOLID=42 AVAILABLE=1 SYNC=1 QUIET=1
       MMU_GATE_MAP GATE=0 APPLY=1
   HH now has gate_spool_id[0] = 42.

7. Next poll cycle (30 s later):
   _hh_gate_is_loaded() checks mmu.get_status() → gate_spool_id[0] = 42 > 0 → True
   current_spool = 42, not None → both suspend conditions met
   _hh_load_paused = True
   miss_count zeroed, return early. PN532 not pulsed.

   Note: Step 5 and 6 have a timing gap. _hh_confirmed_spool is set in step 5
   when the callback is *scheduled*, before HH actually processes the macro.
   If a poll fires in the narrow window between scheduling and HH execution,
   gate_spool_id may still show -1. In that window, _hh_gate_is_loaded() returns
   False and the poll reads the tag again — process_read() sees same uid+spool
   → None (quiet). No harm done.

8. Timer keeps firing every 30 s. Each cycle:
   _hh_gate_is_loaded() → True, current_spool set
   → miss_count zeroed, return. No I2C traffic.
   _hh_load_paused stays True for the duration the spool is loaded.

9. User ejects spool. HH clears gate:
   gate_spool_id[0] = -1

10. Next poll cycle: _hh_gate_is_loaded() → False.
    _hh_load_paused was True → resume path fires:
      _hh_load_paused    = False
      current_uid        = None
      current_spool      = None
      miss_count         = 0
      _hh_confirmed_spool = None
    
    _check_hh_cleared() runs — current_spool is now None, so it returns early.
    read_tag() fires. Gate is empty → uid_hex = None.
    GateState.process_read(None, None) → miss_count = 1 → None (still counting)

11. After absent_threshold polls with no tag:
    GateState.process_read(None, None) → EVENT_REMOVED (miss_count = absent_threshold)
    _NFC_SPOOL_REMOVED GATE=0 dispatched.
    Macro checks printer.mmu.action — if idle, clears HH gate map.
```

---

## Happy Hare Compatibility Contract

This section is the authoritative reference for the HH interface surface used by the NFC system. Any change to the HH plugin that removes or renames an item below will break NFC.

### `mmu.get_status()` — Required Keys

Called as `mmu.get_status(eventtime)` on the HH Python object. Returns a dict. NFC accesses the following keys:

| Key | Type | Used in | Purpose |
|---|---|---|---|
| `gate_spool_id` | `list[int]` | `_seed_cache_from_hh`, `_check_hh_cleared`, `_hh_gate_is_loaded`, `_hh_filament_label` | Spool ID assigned to each gate; `-1` = empty/unknown |
| `gate_status` | `list[int]` | `_seed_cache_from_hh`, `_hh_filament_label` | Availability flag per gate; `0` = unavailable, `1` = available |
| `gate` | `int` | `_hh_filament_label` | Index of the currently active gate; `-1` = none |
| `filament_pos` | `int` | `_hh_filament_label` | Current filament position in the loading sequence; `0` = at/before gate |

All four keys are accessed with `.get(key, default)` so a missing key degrades gracefully rather than raising an exception. `gate_spool_id` and `gate_status` are indexed by `self._gate`; some call sites pre-check lengths (`_seed_cache_from_hh()`), while others rely on `IndexError` handling around the access (`_check_hh_cleared()`, `_hh_gate_is_loaded()`, `_hh_filament_label()`).

### `printer.mmu.*` — Jinja2 Template Variables

Accessed in `nfc_macros.cfg` via the Klipper template engine (`printer.mmu.<key>`):

| Variable | Type | Used in | Purpose |
|---|---|---|---|
| `printer.mmu.action` | `str` | `_NFC_SPOOL_REMOVED` | MMU action string (e.g. `"Loading"`, `"Unloading"`, `"Homing"`, `"Idle"`). Removal is suppressed when this contains `"load"`, `"unload"`, or `"homing"` (case-insensitive). |
| `printer.mmu.num_gates` | `int` | `NFC_HH_SYNC_CACHE` | Total number of configured MMU gates; used to iterate the gate map. |
| `printer.mmu.gate_spool_id` | `list[int]` | `NFC_HH_SYNC_CACHE` | Same as `gate_spool_id` above; accessed as a list from Jinja2. |
| `printer.mmu.gate_status` | `list[int]` | `NFC_HH_SYNC_CACHE` | Same as `gate_status` above. |

### GCode Commands Issued

All GCode is dispatched from `nfc_macros.cfg`. The NFC Python layer never calls HH commands directly.

| Command | Parameters | Issued from | Purpose |
|---|---|---|---|
| `MMU_GATE_MAP` | `GATE=N SPOOLID=N AVAILABLE=1 SYNC=1 QUIET=1` | `_NFC_SPOOL_CHANGED` | Assign spool to gate and mark available |
| `MMU_GATE_MAP` | `GATE=N APPLY=1` | `_NFC_SPOOL_CHANGED`, `_NFC_SPOOL_REMOVED` | Push updated map into active print state |
| `MMU_GATE_MAP` | `GATE=N SPOOLID=-1 AVAILABLE=0 SYNC=1 QUIET=1` | `_NFC_SPOOL_REMOVED` | Clear gate assignment |

`SYNC=1` tells HH to synchronise the assignment to Spoolman. `QUIET=1` suppresses console output from the HH command itself (NFC's own console messaging handles user feedback). `APPLY=1` is required to make the map change visible to an active print immediately.

### Version Requirements

These parameters (`SYNC`, `QUIET`, `APPLY`) were introduced in **Happy Hare v2.x**. The NFC macros are not compatible with Happy Hare v1.x. No minimum patch version within v2 has been formally validated; the contract has been tested against the v2 branch as of April 2026.

If a future HH version changes the `action` string values or removes `SYNC`/`QUIET`/`APPLY` from `MMU_GATE_MAP`, only the macro bodies in `nfc_macros.cfg` need updating — the Python layer is unaffected.

---



- NFC does not read or write HH's internal Python objects directly — only via GCode macros.
- NFC does not listen for HH events (`printer.register_event_handler('mmu:...')` is not used).
- NFC does not call `MMU_GATE_MAP` directly — only the user-editable macros in `nfc_macros.cfg` do. This keeps HH command syntax isolated from the NFC Python layer.
- NFC does not disable itself when HH is absent. With no `mmu` object: `_hh_gate_is_loaded()` returns False (polling never suspends), `_check_hh_cleared()` is a no-op, and GCode dispatches still fire — but HH macros will fail with "Unknown command" if HH isn't installed.
