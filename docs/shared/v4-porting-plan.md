# Happy Hare V4 Porting Plan

[← Back to README](../../Readme.md)

---

This document lays out what changes and what's reusable if this add-on targets Happy Hare V4's native architecture instead of the current compatibility-shim approach against the pre-V4 monolith. It's based on a direct read of `upstream/v4` and `upstream/rfid` in the `moggieuk/Happy-Hare` repo (local checkout: `/Users/cory/Documents/GitHub/Happy-Hare`), cross-referenced against this repo's current implementation. Every API reference below (method signature, attribute name, file, line number) was checked directly against that source tree — not inferred — as of this pass.

**Status: discovery draft, second pass.** Nothing here is committed to; it's a map of the terrain before deciding a route.

---

## 0. The headline finding

Happy Hare's `upstream/rfid` branch (maintainer: moggieuk, based on `v4`) already contains a native NFC integration — and its three reader driver files (`pn532_driver.py`, `pn7160_driver.py`, `rc522_driver.py`, under `extras/mmu/unit/nfc/`) were extracted from this project's hardware layer. Those upstream drivers and the factory have now been brought back into this V4 branch and verified for the APIs this add-on needs (§2.1).

Worth raising with upstream directly: given the shared authorship, a conversation with moggieuk about co-developing `rfid` further (rather than diverging) may be more valuable than a purely unilateral port.

---

## 1. Target architecture (V4 core, verified)

| Concern | V4 mechanism |
|---|---|
| MMU state machine | `MmuController` (`extras/mmu/mmu_controller.py`), registered as printer object `'mmu'`. |
| Motion | `MmuFilamentMovement.move_filament(...)` (mixed into `MmuController`) → `MmuDrive.move()` → `MmuStepper` rail homing. |
| Persistent variables | `SaveVariableManager` (`extras/mmu/mmu_utils.py`), wraps `[save_variables]` with per-unit `namespace=`. |
| Gate map | `MmuGateMaps` (`extras/mmu/mmu_gate_maps.py`): `assign_spool_id(gate, spool_id)`, `persist_gate_map(...)`, `set_gate_status(gate, state)`. |
| Hardware plugin pattern | `MmuUnit` (`extras/mmu/mmu_unit.py`) owns a `subcomponents` list, each `(config, mmu_unit, params)`. |
| RFID pre-announce hook | `mmu.pending_spool_id` + `MMU_GATE_MAP NEXT_SPOOLID=<id>`, timeout-armed (`pending_spool_id_timeout: 20`). |

---

## 2. Component-by-component plan

### 2.1 Reader drivers and factory — ⚠️ local integration complete; Happy Hare cutover open

The PN532, PN7160, and RC522 drivers plus `reader_factory.py` have now been
brought in from the upstream RFID work. The integrated driver signatures retain
`use_key_b` end-to-end, including `mifare_read_authenticated_blocks(...)`, so
Creality's UID-derived Key-B path is preserved on all three readers.

`reader_factory.py` remains in this add-on's `nfc_gates` package, where
`from .. import bus as bus_module` correctly resolves Klipper's
`klippy/extras/bus.py`; the earlier missing-`unit/bus.py` concern applied to a
different upstream package location and is not a problem in the integrated
layout. This repo also deliberately retains its full `log.py` implementation
and dedicated `nfc_reader.log`/level-3/4 diagnostics rather than adopting a
reduced logging shim.

Card-driver and factory internals are now treated as upstream-owned. Future
driver changes should be refreshed from Happy Hare/RFID upstream rather than
independently redesigned during the V4 port. `mmu_nfc_endstop.py` and the NFC
gate/Spoolman/scan-jog orchestration remain local integration code.

The local files are **not yet removable**. Happy Hare cutover requires all six
subsections below. Their checkbox status is summarized in the
[Implementation Log](v4-implementation-log.md#happy-hare-driverfactory-cutover-challenges--open).

#### 2.1.1 — Restore and verify `use_key_b` in Happy Hare

Happy Hare's PN532, PN7160, and RC522
`mifare_read_authenticated_blocks(...)` implementations must accept and
propagate `use_key_b` through authentication. This is required for Creality
CFS/K1/K2's UID-derived Key-B path; losing it produces a silent rich-read
fallback or authentication failure rather than an obvious import error.

#### 2.1.2 — Correct Happy Hare's factory bus import

`extras/mmu/unit/nfc/reader_factory.py` must resolve Klipper's real
`extras/bus.py` from its installed package location. The expected relative
import is:

```python
from .... import bus as bus_module
```

Confirm this with an actual Klipper import test rather than relying only on
package-depth inspection.

#### 2.1.3 — Switch this extension to Happy Hare's NFC imports

Once §§2.1.1-2.1.2 are available in the required Happy Hare revision, replace
the local imports with:

```python
from ..mmu.unit.nfc import reader_factory
from ..mmu.unit.nfc import pn532_driver
from ..mmu.unit.nfc import rc522_driver
```

`pn7160_driver` needs no direct `nfc_manager.py` import because
`reader_factory.create_reader(...)` constructs it internally. Preserve the
factory API used for reader type parsing, bus defaults, address validation,
and reader construction, plus the PN532/RC522 low-level-debug helper calls.

#### 2.1.4 — Validate the installed V4 integration

Run import/compile checks and initialize PN532, PN7160, and RC522 readers in a
real Happy Hare V4 Klipper environment. Exercise UID reads, rich reads,
low-level debug commands, target release, and Creality Key-B authentication.
Do not infer runtime compatibility solely from matching class names or method
signatures.

#### 2.1.5 — Delete the local hardware layer

Only after §2.1.4 passes, remove these extension-local files:

- `nfc_gates/reader_factory.py`
- `nfc_gates/pn532_driver.py`
- `nfc_gates/pn7160_driver.py`
- `nfc_gates/rc522_driver.py`

Then check for stale Python imports, installer/symlink assumptions,
documentation references, and packaging behavior.

#### 2.1.6 — Update ownership, requirements, and logging documentation

Document that Happy Hare V4's RFID package supplies the reader drivers and
factory, including the minimum compatible Happy Hare revision. Decide whether
to accept Happy Hare's reduced `nfc/log.py` behavior or add a supported bridge
back to this extension's dedicated `nfc_reader.log`; the ownership cutover
must not silently change diagnostic expectations.

**Cutover rule:** the four local files remain authoritative until
§§2.1.1-2.1.6 are all complete.

### 2.2 NFC-as-endstop binding — ✅ complete

The existing V4 code path in this repo was **verified correct against real V4 source**, not a guess — the biggest confirmation from the first pass of this plan.

**What's already right**, confirmed line-for-line:

| This repo's code (`happy_hare_compat.register_nfc_endstop`, V4 branch) | Real V4 source | Verified at |
|---|---|---|
| `mmu.drive(gate_number)` | `MmuController.drive(self, gate=None)` → `self.mmu_unit(gate).drive_obj(gate)` | `extras/mmu/mmu_controller.py:558` |
| `drive.mmu_gear_stepper` | `MmuDrive.__init__` stores `self.mmu_gear_stepper = mmu_gear_stepper` | `extras/mmu/unit/mmu_drive.py:34` |
| `gear_stepper.rail.add_extra_endstop(None, name, mcu_endstop=endstop)` | `MmuStepper.add_extra_endstop(self, pin, name, register=True, bind_steppers=True, mcu_endstop=None)` | `extras/mmu_stepper.py:283` |
| Same `pin=None` + `mcu_endstop=` idiom | Real V4 core code does the *identical* thing for its own virtual sensors: `s.rail.add_extra_endstop(None, sensor_name, mcu_endstop=sensor)` | `extras/mmu/mmu_unit.py:508` |
| `create_mmu_runout_helper`'s V4 branch (no `switch_pin` kwarg) | `MmuRunoutHelper.__init__(self, printer, name, event_delay=0, gcodes=None, insert_remove_in_print=False, button_handler=None, register=True)` — no `switch_pin` param | `extras/mmu/mmu_sensor_utils.py:100` |

**What was done:**
- ✅ `mmu_nfc_endstop.py`'s V4 registration path kept as proven-correct code. The V3 branch and the dual-detection (`callable(getattr(mmu, 'drive', None))`) are gone — deleted along with `happy_hare_compat.py` (§2.3), inlined directly into `mmu_nfc_endstop.py`.
- ✅ Confirmed as already correct, no change needed: this add-on does **not** route through native `[mmu_nfc_reader]` (`extras/mmu/unit/mmu_nfc_reader.py`) as the underlying reader owner because that component has no gate-mapping/scan-jog config surface. This add-on's own `[nfc_gate <name>]` stays the config/lifecycle owner; `mmu_nfc_endstop.py` wraps *that* reader. Revisit only if/when native `[mmu_nfc_reader]` grows the orchestration hooks this add-on needs.

#### 2.2.1 — Extension ownership cleanup — ✅ complete 2026-07-12

The duplicate-binding registry now lives on `NFCGate._nfc_endstops_by_gate`.
The previous V4 draft injected `_nfc_endstops_by_gate` onto Happy Hare's
`MmuController`, even though Happy Hare never read it; it existed solely for
this extension's duplicate-gate validation.

`mmu_nfc_endstop.py` intentionally keeps its local Klipper endstop protocol.
It is not being moved into Happy Hare or converted into a Happy Hare-owned NFC
sensor. The only Happy Hare interaction is attaching this extension-owned
endstop object to `mmu.drive(gate).mmu_gear_stepper.rail`, which is required so
Happy Hare/Klipper can perform the homing move against it.

#### Ownership boundary: `mmu_nfc_endstop.py` stays local

Unlike the upstream-owned hardware drivers in §2.1, `mmu_nfc_endstop.py` is wired specifically to *this add-on's own* `[nfc_gate <name>]` reader objects and scan-jog state (`_scan_mode`, the cache-seeding logic) — not to Happy Hare's native `[mmu_nfc_reader]`. There's no version of it that's "generic NFC endstop code" independent of this add-on's own design, because native `[mmu_nfc_reader]` still has none of the surrounding gate-mapping/scan-jog machinery this file exists to bridge into. The instance wrapping *this add-on's* reader stays here; no Happy Hare sensor implementation or upstream endstop contribution is planned.

### 2.3 `happy_hare_compat.py` — ✅ deleted 2026-07-12

No reason to keep checking for backports — this add-on targets V4 only, full stop, so there's no version branch left to maintain here at all, not even a lightweight one keyed off Happy Hare's version number. Both functions' V4-only bodies moved directly into their sole caller, `mmu_nfc_endstop.py`; the module is gone. Full detail in the [Implementation Log](v4-implementation-log.md).

- `create_mmu_runout_helper()` → inlined as a direct `MmuRunoutHelper(...)` construction (`from .mmu.mmu_sensor_utils import MmuRunoutHelper`) in `__init__`. The `try/except ImportError` V3 probe is gone — there's nothing to fall back to.
- `register_nfc_endstop()` → inlined directly into `_handle_connect()`. The `callable(getattr(mmu, 'drive', None))` duck-type check is gone too — `mmu.drive(gate_number)` is called unconditionally, since a V3 `mmu` object was the only reason that check existed.
- `RuntimeError`-then-wrap became direct `self.config.error(...)` at each failure point — more idiomatic for a Klipper config-time error, and one less layer of exception translation now that there's only one caller.
- **Not carried over in that change:** the `mmu._nfc_endstops_by_gate` bookkeeping was initially left on the foreign `mmu` object because it was outside the compatibility-module deletion. It was subsequently moved to the extension-owned `NFCGate` registry in §2.2.1.

### 2.4 `gate_state.py` + status-polling — ✅ complete 2026-07-12

The debounce/edge-detection state machine (`GateState`, `CurrentTag`) is genuinely NFC-specific and needed no change. What this section actually set out to design — a hook-driven alternative to poll-based scan-jog triggering — turned out to already exist as working macros (`_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD`). The plan then went through one more real decision than originally expected: rather than leaving the poll loop's own trigger logic in place as a permanent parallel fallback, it was removed outright, on the reasoning that Happy Hare's hook now owns triggering and a second, independent trigger path is redundant complexity, not a safety net worth keeping. Full detail on both the removal and its consequence (below) in the [Implementation Log](v4-implementation-log.md#2026-07-12--24-remove-the-poll-loop-scan-jog-trigger-add-auto-request-queuing).

#### How the polling was actually handled

`_poll_timer_event`'s "Scan-jog gate-status edge detection" block did three distinct things bundled together: (1) decide *when* to start a scan-jog (the 0→1 gate-status edge → `_start_scan_mode()`), (2) suppress the I2C tag read while Happy Hare already has an opinion about the gate (loaded+matched, or assigned), (3) detect gate ejection to clear the NFC cache and resume polling. Only (1) was removed. (2) and (3) don't depend on edge comparison at all — both only need the *current* gate status, not a `prev`→`curr` transition — so they stay exactly as they were, just no longer wrapped in trigger-arming logic. Everything the trigger alone fed (`_scan_pending`, `_scan_idle_ready_time`, `_scan_deferred_notified`, `_prev_gate_status`, and the now-orphaned `_start_scan_mode()` delegator) was removed as a dead-code consequence, not a separate decision.

#### The gap this uncovered, and how queuing was implemented

The deleted trigger had its own built-in behavior for "another gate is already scanning": re-arm and retry every 3 seconds until the active scan finishes. `manual_jog_scan()` — the hook/manual entry point that now owns triggering — never had an equivalent; it just warns and gives up. Neither Happy Hare's hook (`_MMU_POST_PRELOAD` fires once, synchronously, fire-and-forget) nor Klipper's event system provide retry semantics on their own — this was entirely the poll loop's own behavior, and removing it without replacement would have silently broken any install where two gates get preloaded close together (a real, likely scenario for a multi-gate MMU, not an edge case).

**Fix:** a proper queue in `scan_jog.py`, not a resurrected poll-retry loop:
- `NFCGate._scan_queue`, a class-level list alongside the existing `_active_scan_gate` lock.
- When a **hook-triggered** (`SOURCE=AUTO`) request finds another gate scanning, its gate number is queued instead of failing. Manual console `JOG_SCAN=1` keeps the original immediate warn-and-return unchanged — matches original behavior, where only the automatic path ever retried itself.
- `_drain_scan_queue()`, called from both `finish()` and `rewind_and_exit()` right after `_active_scan_gate` is released: pops the next queued gate and re-issues the same `NFC GATE=<n> JOG_SCAN=1 SOURCE=AUTO` gcode the hook itself would send, deferred via a fresh reactor callback (not called inline, to avoid re-entering the gcode dispatcher from inside another command's tail).
- Re-issuing the full command means a queued gate re-runs the full validation on its way back in — if it was ejected while waiting, that's caught normally rather than assumed still valid.

This is event-driven (fires the instant the active scan actually finishes), not polling-based (the original's 3-second retry latency) — an improvement, not just a replacement.

#### A real behavior change worth stating plainly

Before this change, automatic scan-jog triggering worked with **zero** configuration — the poll loop was the trigger, on by default. After this change, **automatic triggering requires `variable_user_post_preload_extension` to be wired** to `_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD` in the user's `mmu_macro_vars.cfg` — there is no fallback anymore. This makes §2.4.1 item 4 below (this add-on's own installer/docs decision for that wiring) load-bearing for out-of-box behavior, not just a UX nicety. An install that skips it still works via manual `NFC GATE=<n> JOG_SCAN=1`, but won't auto-trigger at all.

#### The insight this design is built on

If Happy Hare already tells this add-on *when* it's safe to act — specifically, right after a gate finishes preloading — there's no need to independently re-derive "is Happy Hare idle," "is this gate settled," "is a print in progress" on every tick. The hook firing *is* the safety guarantee. Verified against source, not assumed:

```python
# extras/mmu/mmu_filament_movement.py:51-127, _preload_gate()
def run_post_preload_macro():
    with self._wrap_track_time('post_preload'):
        if self.p.post_preload_macro:
            self.reset_sync_gear_to_extruder(False, force_grip=True)
            self.wrap_gcode_command(self.p.post_preload_macro, exception=True, wait=True)
...
self.gate_maps.set_gate_status(gate, GATE_AVAILABLE)
self._check_pending_spool_id(gate)   # pending_spool_id already resolved into gate_spool_id...
self.log_always("Filament detected and loaded in gate %d" % gate)
run_post_preload_macro()             # ...BEFORE this fires
```

`post_preload_macro` defaults to `_MMU_POST_PRELOAD` (`config/base/mmu.cfg:383`, *"Called after successful preload of filament"*), which the standard sequence macros route through the user-extensible `variable_user_post_preload_extension` (`config/base/mmu_macro_vars.cfg:283`, wired via `config/macros/mmu_sequence.cfg:414-416`). **This add-on already has hook macros for both install patterns, today, working** — confirmed directly in `config/nfc_macros.cfg`: `_NFC_SCAN_JOG_PRELOAD` (per-lane, calls `NFC GATE={gate} JOG_SCAN=1 SOURCE=AUTO`) and `_NFC_SHARED_PRELOAD` (shared reader), both documented as wiring targets for `variable_user_post_preload_extension`. This isn't something to build — it already exists and already works. The `SOURCE=AUTO` flag on the per-lane call is itself confirmation this was built deliberately to be trusted: it's what lets a hook-triggered call bypass the same busy/idle re-testing a manual `JOG_SCAN=1` invocation goes through.

The "implicitly asserts not printing" framing in the original draft of this section was imprecise and has been corrected: Happy Hare doesn't merely *imply* not-printing at hook time — `MmuUnit.can_async_preload()` (`mmu_unit.py:759`) explicitly checks `self.mmu.is_printing()` and refuses to preload at all if true, in both V3 and V4. That's an existing, already-enforced precondition this add-on has always been able to rely on — not a new inference from hook timing.

#### Verified gap: the hook doesn't cover every preload path

Two independent preload implementations exist:

| Path | Fires `post_preload_macro`? |
|---|---|
| `MmuFilamentMovement._preload_gate()` (`mmu_filament_movement.py:51`) — preloads the *currently selected* gate | ✅ Yes |
| `MmuUnit.preload(gate)` (`mmu_unit.py:781`) — async/button-triggered *crossload* preload of a gate that is **not** the active one | ❌ No — calls `set_gate_status()`/`mmu._check_pending_spool_id()` but never calls the macro |

The crossload path is the more realistic trigger for a multi-gate install with independent per-gate readers — "insert a new spool into gate 3 while gate 1 is actively printing." **This gap is now more significant than when first found**: with the poll-loop trigger removed (above), a gate preloaded via `MmuUnit.preload()` has no automatic scan-jog trigger at all — not the hook (doesn't fire), not the poll loop (no longer exists). It falls through to manual `NFC GATE=<n> JOG_SCAN=1` only. Still narrow (one specific preload path), but no longer "secondary" — this is the one real functional gap left by this section's changes.

#### Not gated on Happy Hare's upstream installer — still true, but the stakes changed

NFC support itself is opt-in; the preload hook is a further opt-in layer within that, and nothing here requires Happy Hare's own installer to change — this add-on's own `install.sh` already has everything needed to offer the wiring itself. That part of the original correction still holds. What's changed is the consequence of *not* wiring it: this used to be "convenience vs. slightly-slower-default," with the poll loop covering anyone who skipped it. **Now it's the only automatic path.** See "A real behavior change worth stating plainly" above.

#### 2.4.1 — Documentation update — ✅ complete 2026-07-12

The consolidated documentation pass is complete. Its checklist and outcome:

1. **IG-dev-only caveat removed** — `post_preload_macro`/`variable_user_post_preload_extension` is present directly in mainline `moggieuk/Happy-Hare`'s V4 branch (`config/base/mmu.cfg:383`, `config/base/mmu_macro_vars.cfg:283`).
2. **New trigger model documented** — the guides now state that the hook decides when to scan, polling has no trigger fallback, and an install without the hook has manual-only scan-jog.
3. **Multi-gate queue behavior documented** — a second trusted hook request is queued and starts after the active scan finishes; manual requests are not queued.
4. **Document the `MmuUnit.preload()` crossload gap as a known limitation** — done in the configuration and install guides. A gate preloaded via the crossload path has *no* automatic scan-jog trigger (not hook, not poll), so manual `JOG_SCAN=1` is currently required.
5. **Installer automation remains a product decision** — the installer still does not write Happy Hare's hook setting. The install guide now treats manual hook wiring as required rather than implying polling is a fallback.

#### What's still useful from the original Mechanism A/B framing

- `mmu:printing`/`mmu:not_printing` (real Python events) remain a useful coarse safety net — e.g. immediately suspending an in-progress scan-jog if a print starts — complementing the preload hook.
- The generic `_MMU_EVENT`/`gate_map_changed` macro hook remains the right catch-all for gate-map changes that *don't* go through a preload at all — e.g. a user manually running `MMU_GATE_MAP SPOOLID=... GATE=...` from the console.
- `mmu:gate_selected` is still right for anything that only needs "what gate is currently active" in general — e.g. status displays.

**Current persistence behavior:** `mmu.gate_maps`'s arrays remain backed by
`SaveVariableManager`/`mmu_vars.cfg` as the sole persisted source of truth.
NFC-side UID/identity state is currently transient and is not a second store.
§2.12 intentionally extends the existing gate-map schema so those values join
the same source of truth instead of creating separate NFC persistence.

**Section complete 2026-07-12.** Code landed: the poll-loop trigger was removed,
poll-suppression/ejection-detection were kept, and multi-gate queuing was added
in `scan_jog.py` (full detail: [Implementation Log](v4-implementation-log.md#2026-07-12--24-remove-the-poll-loop-scan-jog-trigger-add-auto-request-queuing)).
The consolidated documentation pass is also complete. Installer automation and
the crossload-path functional gap remain separate follow-up decisions.

### 2.5 `hh_status.py` — ✅ ported 2026-07-12

Verified against `extras/mmu/mmu_constants.py`, then ported directly — full detail and verification notes in the [Implementation Log](v4-implementation-log.md#2026-07-12--25-hh_statuspy--direct-reads-replace-the-dict-parsing-adapter).

| This repo hardcoded (before) | Real V4 value | Verdict | Port |
|---|---|---|---|
| `GATE_EMPTY = 0` | `GATE_EMPTY = 0` | exact match | Local declaration deleted; now `from ..mmu.mmu_constants import GATE_EMPTY` |
| `GATE_AVAILABLE = 1` | `GATE_AVAILABLE = 1` | exact match | Same — imported directly |
| `GATE_INBUFFER = 2` | `GATE_AVAILABLE_FROM_BUFFER = 2` | same value, different name — cosmetic only, not a bug | Renamed to the real constant at its one call site (`nfc_manager.py:_all_lanes_parked_or_empty`) and imported directly, dropping the locally-invented name |
| `FILAMENT_POS_UNLOADED = 0` | `FILAMENT_POS_UNLOADED = 0` | exact match | Imported directly |
| `ACTION_IDLE = 'idle'` compared via `.lower()` | `_get_action_string()` returns `"Idle"` (capitalized) for `ACTION_IDLE = 0` | already safe, but string-typed — see below | Switched entirely off string comparison: `mmu.action` is now read as the real int and compared against imported `ACTION_IDLE`/`ACTION_CHECKING`. This caught a live bug — `_happy_hare_allows_scan_action()` still compared against `'idle'`/`'checking'` string literals, which would have silently always failed against a real int. Added `hh_status.action_label()` (small local map, `Idle`/`Checking`, falls back to the raw int) so the ~4 log/console messages that used to interpolate the display string stay human-readable. |

**How it was ported:** `hh_status.py`'s `read()`/`read_full()` (parsed `mmu.get_status(eventtime)`, a dict built for external template/webhook consumers) were replaced with `gate_snapshot()`/`full_snapshot()`, which read `mmu.gate_maps.gate_status[gate]`, `mmu.gate_maps.gate_spool_id[gate]`, `mmu.action`, `mmu.filament_pos`, and `mmu.gate_selected` directly off the live `MmuController`. The `GateSnapshot`/`FullSnapshot` wrapper classes were kept (not fully inlined at all ~15 call sites) since `scan_jog.py` can't import `nfc_manager.py` (circular) and the `.assigned`/`.available`/`.idle`/`.label()` derived properties were worth preserving given the call-site count — the change is that they're now built from live attributes, not a parsed dict snapshot. Dead code (`all_lanes_parked_or_empty()`, a module-level function with zero callers) was deleted rather than ported.

### 2.6 `nfc_manager.py` — verified method-by-method mapping — partially ✅ complete 2026-07-12

**`nfc_manager.py` is not a port target for `extras/mmu/unit/mmu_nfc_reader.py` — stated explicitly here, not left to be inferred from §2.2.** They aren't two versions of the same thing. `mmu_nfc_reader.py` is a bare hardware wrapper: confirmed against source, it exposes only `last_uid`/`present`/`read_tag()`/`read_target()` — raw hardware facts, nothing else. `nfc_manager.py` owns the entire orchestration stack on top of that kind of layer — polling lifecycle, tag debounce, Spoolman resolution, scan-jog coordination, LED delegation, shared-reader staging — for *this add-on's own* `[nfc_gate <name>]` reader objects, not Happy Hare's `[mmu_nfc_reader]` ones. Happy Hare's own driver header already says as much (`"NFCGate owns the application state... dispatches MMU_GATE_MAP and MMU_SPOOLMAN"`) — describing exactly this add-on as the layer it doesn't provide. **There is no upstream equivalent for `nfc_manager.py` to converge toward.** The method-mapping table below is about which `mmu.*` calls it makes, not about `nfc_manager.py` itself having a native counterpart to port onto.

**Scope note on the table below:** a full-file scan of every `mmu.<attr>` pattern in `nfc_manager.py` (not just the table's original entries) found that `move_filament`, `wrap_accel`, `mmu_toolhead`, `gear_rail`, `gear_short_move_speed`, and `_restore_gear_current` **don't actually appear in this file at all** — they live in `scan_jog.py` (§2.7's territory, the motion layer). What `nfc_manager.py` itself needed porting turned out to be different: two spots still parsing `mmu.get_status()` dicts instead of reading real attributes directly, and the entire V3/V4 version-detection apparatus. Both are done — see below.

#### ✅ Ported: two more `get_status()` dict-parsing spots collapsed to direct reads

Found via the same whole-file `mmu.<attr>` scan, same pattern already fixed once for `hh_status.py` (§2.5) — these two had been missed because they're shared-reader-specific, off the main status-read path:

- **`_shared_led_target()`** — tried `getattr(mmu, 'num_gates', None)` first, then fell back to parsing `mmu.get_status()['gate_spool_id']`'s length if that came back `None`. Confirmed `mmu.num_gates` is a real, always-present V4 attribute (`mmu_controller.py:49`) — the fallback could never actually trigger on V4, so it was dead defensive weight. Simplified to `mmu.num_gates` directly, no fallback, using the cached `self._get_mmu()` accessor instead of a fresh `printer.lookup_object('mmu', None)` lookup.
- **`_shared_bypass_selected()`** — parsed `mmu.get_status()['tool']`, comparing against a hardcoded `-2`. Replaced with `mmu.tool_selected == TOOL_GATE_BYPASS`, both confirmed directly against source (`mmu_controller.py:145/2556`, `mmu_constants.py:72` — `TOOL_GATE_BYPASS = -2`, confirming the old hardcoded value was correct, just sourced the wrong way).

#### ✅ Removed: the entire V3/V4 version-detection apparatus

`_detect_happy_hare_version()`/`_happy_hare_major_from_version()` (free functions) plus `_refresh_happy_hare_version()`/`_happy_hare_version()`/`_happy_hare_major_version()` (instance methods, plus the `_HAPPY_HARE_VERSION` cache attribute) existed for one purpose: letting `_happy_hare_allows_scan_action()` gate whether `action=checking` counts as scan-safe behind a "is this actually V4" check — a V3-vs-V4 behavioral difference that no longer needs checking on a V4-only repo. `_happy_hare_allows_scan_action()` collapsed to `return action == ACTION_IDLE or action == ACTION_CHECKING`, unconditionally. Once that was gone, `_happy_hare_major_from_version()` had zero remaining callers and was deleted too. `_detect_happy_hare_version()` (the version-*string* lookup) was kept — it still has one legitimate caller, `NFC_DOCTOR`'s diagnostic output, which was simplified from a three-way "does this version support checking" branch to just reporting the detected version string (still useful for support/debugging, no longer gating behavior).

| v3 call (current) | V4 status | Recommended replacement |
|---|---|---|
| `mmu.select_gate(gate)` | **unchanged**, `mmu_controller.py:2508` | keep as-is |
| `mmu.move_filament(...)` | **unchanged signature**, `mmu_filament_movement.py:2343` (`trace_str, dist, speed=, accel=, motor=, homing_move=, endstop_name=, track=, wait=, encoder_dwell=, speed_override=, suppress_grip_change=`) | keep as-is — current call sites already match |
| `mmu.wrap_sync_gear_to_extruder()` | **unchanged**, `mmu_filament_movement.py:3001` | keep as-is |
| `mmu.wrap_suppress_visual_log()` | **unchanged**, `mmu_controller.py:1925` | keep as-is |
| `mmu.wrap_accel(accel)` | **removed/obsolete** — no such method in V4 | delete the wrapper call entirely; pass `accel=` directly into `move_filament()`/`MmuDrive.move()`, which already accept it inline |
| `mmu._restore_gear_current()` | still exists (`mmu_filament_movement.py:3092`, `(self, gate=None, percent=100)`) but is private | switch to the public equivalent: `mmu.wrap_gear_current(percent=100, reason="...")` context manager, `mmu_filament_movement.py:3031` — this is the pattern V4's own code uses internally |
| `mmu.mmu_toolhead` (`.sync()`, `.get_position()`, `.move()`, manual lookahead-queue draining) | **gone — no equivalent object.** See §2.7 deep dive. | rebuild on `mmu.drive(gate).mmu_gear_stepper` (`do_move`, `do_homing_move`, `get_position` — confirmed on `MmuStepper`, `extras/mmu_stepper.py:864/873/1011`) |
| `mmu.gate_selected` | **unchanged** attribute | keep as-is |
| `mmu.gate_speed_override` | **unchanged** externally — now backed by an `@property` (`mmu_controller.py:1477`) over `gate_maps`, same list-like shape | keep as-is |
| `mmu.gear_short_move_speed` | **✅ Ported 2026-07-12** — no flat controller attribute; now a per-unit config param | `mmu.drive(gate).mmu_unit.p.gear_short_move_speed` (`MmuDrive.mmu_unit` back-reference confirmed, `unit/mmu_drive.py:31`; param confirmed at `config/base/mmu_parameters.cfg:160`) |
| `mmu.num_gates` | **unchanged** | keep as-is |
| `mmu.gear_rail` | **✅ Ported 2026-07-12** behind unit architecture | Position reads now use `mmu.drive(gate).mmu_gear_stepper.get_position()`; the NFC endstop binding uses the drive's stepper rail |
| `mmu._initialize_filament_position` / `mmu.initialize_filament_position` | **✅ Ported 2026-07-12.** V4 name confirmed: `initialize_filament_position`, no leading underscore (`mmu_controller.py:2008`) | V3 dual-try removed; call the V4 method directly |

**Bowden length lookup — concrete fix, not just "use an API instead of text-parsing":**

`_resolve_mmu_vars_path()`/`_load_bowden_lengths()` (`nfc_manager.py:2784-2822`) hand-parses `mmu_vars.cfg` looking for a line starting with `mmu_calibration_bowden_lengths` (the V3 name). Verified: the real V4 variable is `VARS_MMU_BOWDEN_LENGTHS = "mmu_bowden_lengths"` (`mmu_constants.py:240`) — different name, and namespaced per-unit by `SaveVariableManager.namespace()` in multi-unit installs, which text-parsing could never have handled correctly anyway.

**Recommended approach:** delete the text-parsing pair entirely; replace with `mmu.var_manager.get(VARS_MMU_BOWDEN_LENGTHS, default, namespace=<unit_name>)`. This also removes the dependency on knowing `mmu_vars.cfg`'s on-disk path/format at all.

**Gate lookup:** `nfc_gate_for_gate_number()`'s linear search over `_lane_instances` should stay a locally-owned registry (there's no canonical "gate → NFC hardware" lookup in V4 core, since NFC isn't a first-class `MmuUnit` subcomponent — see §3) — but fold the endstop registry from §2.2 into this same structure rather than keeping two parallel per-gate maps.

### 2.7 `scan_jog.py` — deep dive: the "motion rail" question

This is the module you specifically flagged. Two techniques exist in the current code; they are **not equally portable**.

**Technique A — homing-move + virtual endstop (`run_homing_jog`/`run_direct_homing_jog`).** This is the "motion rail" approach: register the NFC reader as a software endstop on the gear rail (`mmu_nfc_endstop.py`), then issue a homing move that stops the instant a tag is seen. **Fully verified against real V4, confirmed in §2.2.** The existing call site:

```python
mmu.move_filament(
    "NFC scan homing move", mm,
    speed=move_speed, accel=move_accel, motor="gear",
    homing_move=(1 if mm >= 0.0 else -1),
    endstop_name=nfc_endstop_name(gate),
    wait=True)
```
(`scan_jog.py:2357`) matches the real `move_filament()` signature parameter-for-parameter. Nothing structural needs to change here beyond what §2.6's table already covers (the surrounding `wrap_sync_gear_to_extruder()`/`suppress_hh_visual_log()` calls are both confirmed real V4 methods too).

Why this already satisfies the "needs to be non-blocking" requirement that originally motivated Technique B: Klipper's homing-move machinery runs the actual stepper motion at the trapq/MCU level, not in a Python loop — the only Python-side polling is `mmu_nfc_endstop.py`'s own `_poll_event` reactor timer checking the reader while `_homing` is true. That's the same non-blocking shape as any other Klipper endstop-triggered homing move. `home_wait()` → `_last_home_elapsed` also already feeds directly into the existing trapezoid position-correction math (`corrected_homing_actual`, `homing_distance_from_elapsed`) unchanged — that math has no Happy-Hare-version dependency at all, it's pure kinematics.

**Technique B — direct continuous jog (`run_direct_continuous_jog`) — removed 2026-07-12.** This directly manipulated `mmu.mmu_toolhead`: `.sync()`, `.get_position()`, `.move()`, plus manual lookahead-queue-drain bookkeeping to know when a queued move finished without blocking the reactor. The obsolete implementation and its V3-only timing state have now been deleted; the V4 NFC homing-move path remains authoritative.

**Verified: there is no equivalent object in V4.** `mmu.mmu_toolhead` doesn't exist. A class named confusingly similarly, `MmuToolheadWrapper`, does exist (`extras/mmu/unit/mmu_toolhead_wrapper.py:58`) — but it is a completely different thing: an extruder/toolhead-entry **sensor bundle** (hall filament-width sensor, entry/toolhead switch sensors), with no `.move()`, `.get_position()`, or lookahead-queue concept at all. There is nothing to port Technique B onto; the abstraction it depended on was decomposed away in the V4 rewrite.

What *does* survive at the primitive level: `MmuStepper` (backing `mmu.drive(gate).mmu_gear_stepper`) still exposes, directly:
```python
do_move(self, movepos, speed, accel, sync=True)          # mmu_stepper.py:864
do_homing_move(self, movepos, speed, accel, probe_pos,
               triggered, check_trigger, endstop_name=None)  # mmu_stepper.py:873
get_position(self)                                         # mmu_stepper.py:1011
```

**Recommended approach:**
1. **Ship Technique A (homing-move) as the primary and, initially, only mechanism for V4.** It's proven-correct against real source, requires the least new code, and already produces the position/elapsed-time data the rest of scan_jog's math consumes.
2. **Do not attempt to port Technique B's implementation.** If true "glide past without stopping, note position, keep going" behavior is still wanted later (to avoid a stop/re-home cycle per candidate position on a long continuous sweep), build it fresh directly on `do_move()` + `get_position()` polled from a reactor timer — the same polling shape `mmu_nfc_endstop.py` already uses for Technique A, just polling `get_position()` during an in-flight `do_move()` instead of polling the reader during a homing move. Do not resurrect `_continuous_timing_snapshot`/`refresh_continuous_move_complete` — that bookkeeping existed specifically to compensate for the old toolhead's async lookahead-queue semantics, which no longer exist in this form; a fresh design against `do_move(sync=True)` should be simpler than what it's replacing, not just a translation of it.
3. **Sequencing:** treat the true continuous-glide primitive as a stretch goal, pursued only if real-world testing shows the homing-move approach's discrete stop/re-home cadence is too slow for target scan-jog travel distances. Don't let it block the rest of the port.

**Unchanged from first pass, still fully portable as pure functions** (no HH coupling beyond speed/accel inputs and a gear-position readout): trapezoid-motion position correction, continuous-UID position tracking/decode-retry ladder, left-neighbor interference detection, rewind/parking math.

**Also unchanged and low-risk:** `select_gate_quiet` → `mmu.select_gate(gate)` (confirmed real name, `mmu_controller.py:2508`); worth checking whether V4's console-banner-on-select behavior (the thing this was working around) still needs suppressing, since V4 may have already fixed it independently — a one-line manual test, not a design question.

### 2.8 `tag_handler.py`, `spoolman_client.py`, `shared_preload.py` — ✅ V4 integration complete

`spoolman_client.py` and `shared_preload.py` remain unchanged and version-neutral;
`shared_preload.py` has no direct `mmu` attribute access. The RFID refresh
through `9c7fb0f` substantially changed `tag_handler.py`'s resolution ladder
and introduced a left-neighbor Happy Hare status check. During integration,
the imported `hh_status.read(...)` call was retargeted to
`NFCGate._read_hh_status_for_gate(...)`, preserving the new RFID behavior
without restoring the deleted V3-era status module. Its imported LED call site
was likewise retained behind the renamed V4-only `NFCLEDManager`.

### 2.9 `NFC_LEDManager.py` (was `LED_effect_mgr.py`) — ✅ complete 2026-07-12

**Why it's not retired, unlike `hh_status.py`:** verified directly against `extras/mmu/mmu_led_manager.py` — the code that actually runs LED effects (`_set_led()`) is a **private** method with no public "run this named effect for N seconds, then hand back" equivalent. `MmuLedManager`'s only public surface is `action_changed`/`print_state_changed`/`gate_map_changed` (Happy Hare's own internal reactive hooks, not meant for external callers) and `effect_name(unit, operation)` (answers "what steady-state effect is configured," a different question than "compute the generated per-gate transient-effect name"). `MMU_SET_LED`/`_MMU_SET_LED_EFFECT` (gcode) genuinely are the sanctioned external API for this concern — the same tier as `MMU_GATE_MAP`/`MMU_SPOOLMAN` — so unlike `hh_status.py` there's no direct-Python shortcut being missed here. This class is a legitimate client of that API, not a duplicate implementation: Happy Hare has no way to know on its own when a tag was just scanned or a rewind is happening, so something has to translate those NFC-domain events into the right gcode calls at the right time.

**Renamed** (file: `LED_effect_mgr.py` → `NFC_LEDManager.py`; class: `LEDEffectManager` → `NFCLEDManager`) because the old names collided conceptually with Happy Hare's real `MmuLedManager` despite doing a genuinely different job — HH's manager owns steady-state output and the actual effect patterns; this one only requests short-lived overrides and hands control back (its own docstring already said as much). All references updated across `tag_handler.py`, `nfc_manager.py` (1 import + 4 instantiations), and `scan_jog.py` (1 import + 2 instantiations); confirmed no stale references remain and all four files compile. No installer changes needed — `install.sh`/`uninstall.sh` don't enumerate individual files in `nfc_gates/`. `CHANGELOG.md`'s two historical entries (lines 547-548) still say `LED_effect_mgr.py` — left as-is, since they're a record of what the file was called *at the time* of that change, not a live reference.

**V3 support removed 2026-07-12** (same session, second change to this file): `is_happy_hare_v4()` deleted outright, along with every branch it gated. `hh_led_script()` collapsed to a single unconditional `_MMU_SET_LED_EFFECT EFFECT=%s REPLACE=1` builder — the `MMU_SET_LED ... EXIT_EFFECT=` V3 command format, and the `duration`/`gate`/`unit`/`direct_effect` parameters that only existed to build it, are gone. `release()`'s `if is_happy_hare_v4(...): ... else: ...` collapsed to the V4 body unconditionally. `led_unit_index()` — a helper that existed solely to compute the V3 command's `UNIT=` value — deleted as dead code once its only call site (inside `play_shared()`) was removed along with the rest.

**Still open, unaffected by either change:**
- `self.printer._nfc_v4_led_effects` (a foreign attribute injected onto the `printer` object) should become a normal instance attribute on `NFCLEDManager` itself instead. Naming residue from the same era (`_v4_effect_registry`/`_remember_v4_effect`/`_release_v4_effect_after` all still carry a `_v4_` qualifier that's now redundant, since there's nothing else to compare against) — left as-is, cosmetic only, not part of this change's scope.
- `lane_effect_name()`/`shared_effect_name()` hardcode a guess at Happy Hare's generated effect-naming convention (`{base}_exit_{gate}`) — confirmed no public API exists to ask HH for that name directly instead, so this remains a real "breaks silently if HH changes its naming scheme" risk, not something either change resolves.

### 2.10 `nfc_macros.cfg` and friends — ✅ complete, these macros should not change

`MMU_GATE_MAP`/`MMU_SPOOLMAN` gcode and `printer.mmu.*` status vars remain the most stable surface; `MmuGateMaps`' API (§1) confirms compatibility at the Python level, which backs the macro-level surface these macros already use. `_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD` (§2.4) are unaffected by the poll-trigger removal — they call the same `NFC GATE=<n> JOG_SCAN=1 SOURCE=AUTO` gcode they always did; the queuing fix (§2.4, implementation log) lives entirely in `scan_jog.py`'s Python, not in these macros.

### 2.11 GCode command registration — adopt V4's `BaseCommand` pattern — ❓ open question for moggieuk / upstream, not yet actionable

Not covered in earlier passes of this plan — a real gap, not a byproduct of §2.6's method mapping. **This section is intentionally not sequenced for implementation yet.** Everything below is verified against source, but one thing isn't verifiable from source alone: whether `register_command()`'s out-of-tree path is actually intended for a fully separate Klipper extras *package* like this add-on, or just for in-tree-adjacent modules (selectors etc.) that already share import context with `extras/mmu/`. That's a question only moggieuk can answer, not something this plan can resolve by reading more code. Raised formally in §6; this section stays a design writeup, not a to-do, until that's answered.

**What exists today:** this add-on registers its commands ad hoc, scattered across `NFCGateDefaults.__init__`/`NFCGate._handle_connect` in `nfc_manager.py` — plain `self._gcode.register_command('NFC_STATUS', ...)`, `register_command('NFC_HELP', ...)`, `register_command('NFC_DOCTOR', ...)`, `register_command('NFC_REGISTER', ...)`, `register_command('NFC_LED_TEST', ...)`, `register_command('NFC_SHARED', ...)`, and `register_mux_command('NFC', 'GATE', ...)`. No shared base class, no built-in `HELP=1` handling (this add-on hand-rolls its own separate `NFC_HELP` command instead of getting it for free), no consistent logging, no per-unit dispatch.

**What V4's own commands look like:** `extras/mmu/commands/` — one `.py` file per command (or logical group), each defining `BaseCommand` subclasses. `extras/mmu/commands/__init__.py`'s `COMMAND_REGISTRY` auto-discovers every `BaseCommand` subclass in that package via `pkgutil.iter_modules`; `MmuController.__init__` instantiates every registered class once:

```python
# mmu_controller.py:82
for name, cls in sorted(COMMAND_REGISTRY.items()):
    cls(self)
```

`BaseCommand.register(name, handler, help_brief, help_params, help_supplement=None, category=CATEGORY_OTHER, per_unit=False, log=True)` (`extras/mmu/commands/mmu_base_command.py`) wraps the handler with automatic `HELP=1` support (`format_help()`), optional per-unit `UNIT=` dispatch (`get_unit()`), and self-logging (`mmu.log_to_file(gcmd.get_commandline())`) before registering against `self.mmu.gcode.register_command()`. It also ships a set of reusable precondition guards — `check_if_disabled`, `check_if_printing`, `check_if_not_printing`, `check_if_bypass`, `check_if_not_homed`, `check_if_loaded`, `check_if_not_loaded`, `check_if_invalid_gate`, `check_if_spoolman_enabled`, `check_if_not_calibrated`, etc. — several of which this add-on currently reimplements ad hoc (its own printing-state checks scattered through `nfc_manager.py`/`scan_jog.py`).

**The out-of-tree path is real and intentional**, not something to work around: `register_command(cls)` (module-level function/decorator in `extras/mmu/commands/__init__.py`) is explicitly for commands defined outside that package — *"This is for commands that are defined outside of this module."* Confirmed in active use: `PhysicalSelector.__init__` (a selector class, not in `commands/`) calls it to register `MmuSoaktestSelectorCommand`.

**Verified, critical timing constraint:** `COMMAND_REGISTRY` is read exactly once, synchronously, inside `MmuController.__init__` (`mmu_controller.py:82`, shown above). Any `register_command()` call made *after* that point has already run is silently inert — the class lands in the dict, but nothing will ever instantiate it; no error, just a command that quietly never registers. This means:

- Registration must happen at **Python import time or config-parse time** — e.g. a `@register_command` decorator on the class definition (runs when this add-on's module is first imported), or inside one of this add-on's own `load_config`/`load_config_prefix` functions — **not** inside a `klippy:connect` handler, which fires only after every config section has already been parsed and `MmuController` already constructed.
- This creates a genuine **`printer.cfg` include-order requirement**: this add-on's `[include nfc/...]` lines must appear *before* wherever `[mmu_machine]` is included, or registration silently never takes effect. This needs to be an explicit, documented installer/config requirement if this pattern is adopted — not an implicit assumption discovered later via a support ticket.

**Recommended approach:** adopt the `BaseCommand` shape and the `register_command()` out-of-tree hook, but keep this add-on's command classes living in `klippy/extras/nfc_gates/` (a new `commands/` subpackage), not physically inside Happy Hare's own `extras/mmu/commands/` tree — the same "call the real API directly, stay a separate package" pattern already used elsewhere in this plan (§2.2's endstop binding, §2.6's method mapping) rather than merging into Happy Hare's source tree. One file per command (or logical group) under `nfc_gates/commands/`, each a `BaseCommand` subclass, `@register_command`-decorated, replacing the current ad-hoc `register_command`/`register_mux_command` calls. This add-on's hand-rolled `NFC_HELP` command becomes unnecessary — `HELP=1` on any individual NFC command works automatically once it goes through `BaseCommand.register()`.

**Scope note:** touches every command entry point this add-on exposes (`NFC`, `NFC_SHARED`, `NFC_STATUS`, `NFC_HELP`, `NFC_DOCTOR`, `NFC_REGISTER`, `NFC_LED_TEST`). A real, distinct reformatting pass, and a consistency/ergonomics upgrade rather than a blocker for anything else in this plan — but sequencing is secondary to the open question above. **Don't start implementation before moggieuk confirms the out-of-tree usage pattern is actually intended for a separate package** — building against a guessed answer risks committing to the `printer.cfg` include-order requirement (§4 checklist) for nothing, if the real answer turns out to be "no, that path is only for in-tree modules."

### 2.12 Gate-map state-ownership migration — 🔴 high risk, design approval required

> [!CAUTION]
> This is a cross-project state-model migration, not a cache cleanup. It must
> not be implemented as one large edit or bundled casually with the remaining
> V4 motion work. No existing NFC state, seeding, command, or recovery path
> should be removed until the replacement has passed compatibility and live
> hardware validation and has a tested rollback path.

Happy Hare's gate map should become the sole source of truth for the spool and
tag identity currently occupying each gate, alongside status, filament
metadata, color, temperature, and speed override. Once UID and
`spool_identity` are persisted there, there is no reason for
`GateState.current_uid` or `GateState.current_spool` to remain a second
authoritative copy. The entire startup-seeding and NFC-cache reconciliation
design should be replaced with direct gate-map reads and writes.

Add two per-gate persisted values to Happy Hare's `_gate_map_vars` definition,
with final constant names agreed upstream, for example:

```python
(VARS_MMU_GATE_RFID_UID, 'gate_rfid_uid')
(VARS_MMU_GATE_SPOOL_IDENTITY, 'gate_spool_identity')
```

Implementation requirements:

1. Define the new save-variable constants and initialize both arrays to one
   empty value per configured gate. Normalize older `mmu_vars.cfg` data so an
   upgrade safely fills missing or short arrays without losing the existing
   gate map.
2. Expose UID, `spool_identity`, and the existing `spool_id` through
   `MmuGateMaps` using the same persistence and
   per-unit namespace rules as the existing gate-map fields. Provide an
   explicit setter/update API rather than having this extension mutate arrays
   and call private persistence helpers itself.
3. Replace `GateState.current_uid` and `GateState.current_spool` as stable lane
   state. `GateState` should retain only transient read/debounce concerns such
   as the current in-progress `CurrentTag`, miss count, and absence threshold.
   Once a read is accepted, stable UID, identity, and spool lookups must come
   from `mmu.gate_maps`, not from the NFC state manager.
4. Rewrite all consumers that currently read the NFC cache. This includes
   normal change detection, polling suppression, `_hh_gate_matches_current_spool`,
   `NFC_STATUS`, scan-jog's previous/current/left-neighbor UID, spool and
   identity helpers, tag-handler left-neighbor checks, post-rewind restore, and
   any macro dispatch that needs the accepted gate assignment.
5. Delete the one-shot Happy Hare seeding layer: `_hh_seed_spool_id`,
   `_hh_seed_available`, `_seed_cache_from_hh()`, `HH_SYNC`,
   `NFC_HH_SYNC_CACHE`, `_NFC_HH_SYNC_ONE`, and seed-match dispatch
   suppression should no longer be needed. Startup should read the persisted
   gate map directly. The first physical read compares against that state; a
   mismatch follows the normal changed-spool path.
6. Write UID, `spool_identity`, and spool ID together after an accepted tag
   resolution so observers never see a newly updated spool with stale tag
   identity. A UID-only/Spoolman result may have an empty identity; rich Bambu,
   TigerTag, and Creality reads populate all available fields. Prefer one
   atomic public gate-map update operation with one persistence/event cycle.
7. Clear UID and `spool_identity` whenever the physical gate is
   cleared/ejected, the NFC spool is removed, or a gate-map reset replaces
   that gate's assignment. Changing only `spool_id` must have an explicitly
   defined policy so stale tag identity cannot silently remain attached to a
   different spool.
8. Retire or redefine cache-oriented user commands. `CLEAR_CACHE=1` and
   `APPLY=1` currently operate on `GateState`; after the rewrite they must
   either operate explicitly on the gate map or be removed. Spoolman's HTTP
   response cache and `spoolman_cache_ttl` remain valid and are not part of
   this removal.
9. Add the fields to status/diagnostic output and test restart persistence,
   multi-unit namespaces, gate-count migration, removal clearing, manual gate
   remapping, atomic updates, offline tag swaps, and same-spool left-neighbor
   checks after restart.

Spoolman's UID extra field remains the durable **UID → spool record** mapping.
The new gate-map values answer a different question: **which physical tag and
same-spool identity currently occupy this gate**. Persisting them in
`MmuGateMaps` provides consistent ownership and removes the duplicated NFC lane
cache rather than merely adding another persistence store.

#### Required delivery phases and gates

**Phase A — design contract, no behavior change**

- Agree with Happy Hare maintainers on field names, types, public API, event
  behavior, persistence frequency, per-unit namespace rules, and ownership of
  clear/reassignment semantics.
- Document invariants for the `(spool_id, uid, spool_identity)` tuple, including
  valid partial states and exactly which operations may change each field.
- Inventory every current `GateState.current_uid/current_spool`, seed, cache,
  scan-jog, shared-reader, macro, status, and recovery caller before coding.

**Gate A:** maintainer review and explicit approval of the schema/API contract.

**Phase B — additive Happy Hare support**

- Add persisted fields, migration normalization, public read/update/clear APIs,
  status exposure, and tests without changing this extension's behavior.
- Prove existing V4 installations load old `mmu_vars.cfg` safely and that
  persistence does not create excessive save-variable writes.

**Gate B:** Happy Hare tests pass and an exact minimum compatible revision is
available for installation and rollback.

**Phase C — dual-read/dual-write migration mode**

- Keep the existing NFC state and commands operational while mirroring accepted
  state into `MmuGateMaps`.
- Compare both stores continuously and log mismatches with enough context to
  diagnose ordering, restart, removal, and manual gate-map-edit problems.
- Prefer the legacy state for behavior during this phase so a gate-map defect
  can be disabled without losing the known-working path.

**Gate C:** source tests plus live PN532/PN7160/RC522, scan-jog, shared-reader,
multi-gate, restart, offline swap, removal, manual remap, and multi-unit testing
show no unexplained divergence.

**Phase D — gate map becomes authoritative**

- Switch stable lookups to `MmuGateMaps`, but retain a temporary compatibility
  fallback and a diagnostic comparison path for one release cycle.
- Update commands and status output before deleting any old fields so operators
  retain recovery and observability.

**Gate D:** field soak period completed with documented upgrade and downgrade
procedures and no unresolved data-loss or stale-identity reports.

**Phase E — remove legacy NFC state/seeding**

- Only now remove `GateState`'s stable UID/spool copies, Happy Hare seed/sync
  machinery, obsolete command behavior, and compatibility fallback.
- Keep migration tests permanently to protect upgrades from older releases.

**Rollback requirement:** every phase must be reversible without hand-editing
`mmu_vars.cfg`. Unknown/new fields must be safely ignored by the previous
extension version, and disabling the new path must leave existing spool IDs and
gate assignments intact.

---

## 3. New V4-core gaps this add-on would be filling

Re-assessed after the deeper pass:

1. **Current gate tag identity persistence — open (§2.12).** Spoolman's UID
   extra field remains the durable UID → spool-record mapping, but it does not
   persist which tag currently occupies a Happy Hare gate. Add per-gate UID and
   `spool_identity` fields to `MmuGateMaps` so gate state survives restart and
   follows the same lifecycle/persistence rules as spool ID and filament data.
2. **NFC-as-endstop binding into the homing graph — extension-owned, not a V4-core gap.** This repo already has the required implementation (§2.2). It attaches the extension's virtual endstop to Happy Hare's gear rail but does not require or propose an NFC endstop implementation inside Happy Hare.
3. **A non-blocking continuous-motion primitive equivalent to `mmu_toolhead` manipulation — narrowed, not solved.** Technique A (§2.7) removes the urgency: it's proven, non-blocking, and covers the primary scan-jog use case. Only the true "never stop moving" variant remains genuinely open, and it now has a concrete, small implementation path (`do_move`/`get_position` polling) rather than being an unknown unknown.

---

## 4. Correctness/regression checklist before cutover

- [x] ~~Confirm `MmuGateMaps` gate-status/filament-pos sentinel values match `hh_status.py`~~ — **verified matching** (§2.5); `ACTION_IDLE` string comparison already safe due to existing `.lower()` normalization.
- [x] **Reader drivers/factory integrated from upstream (§2.1).** Verified `use_key_b` remains present on PN532, PN7160, and RC522; the factory's relative bus import is correct in this repo's package location; full local logging was retained. QIDI's published sector-1 Key A retry remains an optional RFID enhancement, not a V4-port blocker.
- [x] ~~Verify `mmu.move_filament(...)` V4 signature~~ — **verified exact match** (§2.6/§2.7), current call sites already compatible.
- [x] ~~Apply the §2.6 method-mapping table to `nfc_manager.py`~~ — **done 2026-07-12**: the table's entries (`move_filament`, `wrap_accel`, `mmu_toolhead`, `gear_rail`, etc.) turned out to live in `scan_jog.py`, not this file; what `nfc_manager.py` actually needed (two `get_status()` dict-parsing spots, the version-detection apparatus) is ported. **Still open for `scan_jog.py` itself** — that's §2.7's remaining scope, not yet started.
- [ ] Confirm at runtime (once V4 + hardware are available) that `_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD` actually fire and carry the expected gate on real hardware (§2.4) — this is a live-system check, source reading alone can't confirm event-timing behavior.
- [ ] Confirm at runtime the multi-gate queue behavior (§2.4): preload gate 1, then gate 3 while gate 1 is still scanning — gate 3 should queue and start automatically the instant gate 1's scan finishes. Source-verified only so far.
- [ ] Confirm at runtime the shared-reader path end-to-end (§7): tap a tag against the shared reader, verify `_NFC_SHARED_PRELOAD` stages and commits correctly, and specifically exercise `_shared_led_target()`/`_shared_bypass_selected()` (the two spots just ported off `get_status()` dict-parsing) against a real `mmu.num_gates`/`mmu.tool_selected`.
- [ ] §2.4.1: decide this add-on's own installer/docs approach for the preload-hook opt-in (leave manual, or have `install.sh` offer to write `variable_user_post_preload_extension`) — now higher priority than originally scoped, since the poll-loop trigger is gone and the hook is the *only* automatic path (§2.4).
- [x] **User-facing V4 documentation pass completed 2026-07-12.** Removed the stale IG-dev-only and V3/version-gating guidance; documented hook-only automatic triggering, AUTO request queuing, direct V4 state/endstop integration, shared-reader status, transitional driver ownership, and the still-open §2.7 motion/runtime limitation.
- [ ] Verify the `printer.cfg` include-order requirement from §2.11 (`[include nfc/...]` before `[mmu_machine]`) actually holds for real installs before shipping any `BaseCommand`/`register_command()` adoption — a live-system check, not something source reading alone can guarantee across every user's config layout.
- [ ] **§2.12 high-risk migration:** obtain design approval, deliver additive Happy Hare support, validate dual-write comparison on live hardware, complete an authority-cutover soak with rollback, and only then remove `GateState`'s duplicate stable values and the HH seed/cache-sync layer.
- [ ] Note upstream's own known bugs that would otherwise silently affect a port if inherited: `MmuUnit.get_status()`'s `self.nfcs_readers` typo (dead per-gate-reader status field), and the `mmu_rfid_reader`/`mmu_nfc_reader` naming inconsistency between config prefix and gcode command names/logger.

---

## 5. Suggested sequencing

1. **Low-risk mechanical pass** (§2.5 verify-only, §2.6 table, §2.8, §2.9, §2.10): all fully specified now, no remaining unknowns — this is now the bulk of the work and none of it requires design decisions.
2. **§2.2/§2.3**: retarget `mmu_nfc_endstop.py`/`happy_hare_compat.py` to V4-only, dropping the V3 branch — proven code, mechanical edit.
3. **§2.7 Technique A**: port the homing-move scan path — proven signature match, the main remaining work is wiring + real-hardware validation, not design.
4. **Complete §2.1's Happy Hare cutover**: resolve all six driver/factory challenges in the implementation log, including installed-package imports and real-reader validation, before deleting the local files.
5. **§2.7 Technique B replacement** (if needed at all): only after (3) is validated and shown insufficient in practice.
6. Consider upstreaming the `MmuUnit.preload()` crossload hook gap and, optionally, the endstop-binding pattern from §2.2 into `moggieuk/Happy-Hare` directly.
7. **§2.4 is complete in code; §2.4.1's documentation items are a standalone decision, not a sequencing gate for the rest of this plan** — but the installer/docs decision within §2.4.1 is no longer low-priority: with the poll-loop trigger gone, wiring `variable_user_post_preload_extension` is the only automatic scan-jog path left, so this is worth prioritizing within §2.4.1 itself even though nothing *else* in this plan waits on it.
8. **§2.11 (command registration)**: **not sequenced — open question for moggieuk, not just a "do it later" item.** A reformatting/consistency pass with no functional dependents elsewhere in this plan, but implementation shouldn't start until it's confirmed the out-of-tree `register_command()` path is actually meant for a fully separate package (§6). If confirmed, it's a "once the rest has stabilized" item as originally scoped; if not, this section needs a different approach entirely.
9. **User-facing documentation (`install-uninstall.md`, `configuration.md`, `how-it-works.md`, etc.): one consolidated pass at the end**, not incremental edits alongside each code change — too much will shift as (1)-(8) land to make piecemeal doc fixes worthwhile.
10. Keep driver/factory refreshes aligned with upstream ownership; do not reopen their internals as V4-port work unless an integration regression is found.
11. **§2.12 gate-map state ownership**: execute only through its five explicit
    phases and gates. Do not overlap legacy removal with schema introduction,
    and do not schedule the authority cutover until live dual-write evidence and
    a tested rollback procedure exist.

---

## 6. Open questions for a maintainer decision

- Does moggieuk intend `rfid` to eventually carry the full orchestration layer (gate state, scan-jog, Spoolman, shared-reader preload), or is the intent for that to stay a separate/community add-on that just consumes the native driver + `pending_spool_id` hook? This determines whether §2.2/§2.6/§2.7 target an upstream PR or a standalone V4-native package.
- Is the endstop-binding pattern (§2.2, already implemented and verified correct in this repo) worth contributing back into `MmuUnit` directly, so any future hardware unit gets it for free rather than each add-on re-implementing it?
- Should this add-on's own `install.sh` offer to auto-wire `variable_user_post_preload_extension` into the user's `mmu_macro_vars.cfg` (§2.4.1), or stay fully manual/documented as it is today? A self-contained decision for this repo either way — not something requiring Happy Hare's own installer to change.
- For §2.11: is `register_command()` (the out-of-tree hook) actually intended/supported for a fully separate Klipper extras *package* like this add-on, or mainly for in-tree-adjacent modules (selectors, etc.) that already share import context with `extras/mmu/`? Worth confirming with moggieuk before committing to the include-order requirement it implies.

---

## 7. Shared Reader Migration Status

Called out explicitly, not left implicit — this plan has spent most of its recent passes on per-lane scan-jog (§2.4, §2.7), and shared-reader support is a critical, separately-verified path, not a byproduct of that work.

**Architecturally isolated from every scan-jog-focused change made this session — verified, not assumed:**

- `_scan_enabled` is forced `False` for shared-reader instances (`nfc_manager.py`, in the shared-config branch) — confirmed via source read, meaning `_poll_timer_event`'s poll-suppression/trigger logic (§2.4, before *and* after this session's trigger-removal work) never executed for shared readers in the first place. The poll-loop trigger removal and the new multi-gate queue are both no-ops for shared reader.
- `_active_scan_gate`, `_scan_queue`, `manual_jog_scan()`, `_drain_scan_queue()` (§2.4's queue mechanism) — confirmed zero references anywhere in `shared_preload.py`, and none of the ~30 `_shared_*` methods in `nfc_manager.py` touch them either (grepped directly, not inferred). Scan-jog and shared-reader preload are genuinely separate mechanisms: scan-jog physically jogs a specific gate's spool to find a tag; the shared reader is a single in-body reader tags get tapped against, staged via `_NFC_SHARED_PRELOAD` → `PRELOAD_CHECK`/`PRELOAD_COMMIT` → `shared_preload.py`'s `SharedPreloadCoordinator`. Nothing about §2.4's changes touches that flow.
- `_happy_hare_allows_scan_action()`/the version-detection removal (§2.6) — confirmed zero references in `shared_preload.py`; only `scan_jog.py`'s per-lane `manual_jog_scan()` calls it.

**What *did* need porting, and is now done (§2.6, §2.8):**

- `shared_preload.py` itself: a full-file `mmu.<attr>` grep found **zero** direct Happy Hare API surface at all — it only ever dispatches gcode (`MMU_GATE_MAP NEXT_SPOOLID=...`), already fully version-agnostic by construction. Nothing to port.
- `nfc_manager.py`'s shared-reader-specific methods: two genuine V3-pattern spots found and fixed — `_shared_led_target()` and `_shared_bypass_selected()`, both previously parsing `mmu.get_status()` dicts, now reading `mmu.num_gates`/`mmu.tool_selected` directly (§2.6 for full detail).

**Current status: shared reader is source-verified complete**, on the same footing as the rest of this plan — no known remaining V3 patterns, no known coupling to anything removed or changed this session. Like everything else here, it has not been exercised against a live V4 Klipper instance with real hardware yet; that's the one open item, tracked in §4's checklist alongside the per-lane runtime-verification items.
