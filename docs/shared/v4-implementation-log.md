# V4 Implementation Log

[← Back to README](../../Readme.md) · [V4 Porting Plan](v4-porting-plan.md)

---

This log tracks actual code changes made while executing the [V4 Porting Plan](v4-porting-plan.md) — one entry per change, cross-referenced to the plan section it implements. The plan is the map; this is the record of ground actually covered. Format follows the same convention as the top-level `CHANGELOG.md`.

**Legend:** ✨ Added · 🐛 Fixed · ♻️ Changed · 🗑️ Removed · 📝 Docs · ✅ Verified · 💡 Note

---

## Where we are (as of 2026-07-12)

**Implemented in code — 8 changes, all landed:**

1. **§2.5** — `hh_status.py` rewritten to read Happy Hare's live state directly (`mmu.gate_maps.gate_status[gate]`, `mmu.action`, etc.) instead of parsing `mmu.get_status()`.
2. **§2.4, item 1** — `mmu` bound once on `NFCGate` (cached at `klippy:connect`) instead of looked up on every status read, isolated to the `hh_status.py` call path specifically.
3. **§2.9** — `LED_effect_mgr.py` → `NFC_LEDManager.py`, class `LEDEffectManager` → `NFCLEDManager`. A pure rename (logic untouched) to remove the naming collision with Happy Hare's own `MmuLedManager`. All references across `tag_handler.py`, `nfc_manager.py`, `scan_jog.py` updated.
4. **§2.3** — `happy_hare_compat.py` deleted outright. Both of its functions' V4-only bodies inlined directly into their sole caller, `mmu_nfc_endstop.py` — no version check of any kind survives.
5. **§2.5, continued** — `hh_status.py` deleted entirely, not just rewritten. Its content (`GateSnapshot`/`FullSnapshot`, `gate_snapshot()`/`full_snapshot()`, `action_label()`, the constant imports) moved into `nfc_manager.py` as private module-level helpers; `scan_jog.py`'s three remaining touchpoints replaced with methods reachable through the `NFCGate` object it already receives (`_read_hh_status_for_gate()`, `.empty` property, `.action_label()` method) — no import needed.
6. **§2.9, continued** — all V3 support removed from `NFC_LEDManager.py`: `is_happy_hare_v4()` deleted, `hh_led_script()` collapsed to a single unconditional V4 command builder, `release()`'s V3 branch removed, `led_unit_index()` deleted as dead code once its only call site went with it.
7. **§2.4, continued** — the poll-loop's scan-jog *trigger* removed from `_poll_timer_event` (Happy Hare's post-preload hook owns triggering now), poll-*suppression* and ejection-detection kept, and — after a real gap was caught mid-change — a proper queue added in `scan_jog.py` so a second gate preloaded while another is scanning gets serviced automatically once the first finishes, instead of just failing.
8. **§2.6** — two more `mmu.get_status()` dict-parsing spots collapsed to direct reads (`_shared_led_target()` → `mmu.num_gates`, `_shared_bypass_selected()` → `mmu.tool_selected == TOOL_GATE_BYPASS`, both shared-reader-specific and found via a whole-file `mmu.<attr>` scan), and the entire V3/V4 version-detection apparatus removed (`_detect_happy_hare_version`'s string-lookup kept for `NFC_DOCTOR` diagnostics only; `_happy_hare_major_from_version`/`_refresh_happy_hare_version`/`_happy_hare_version`/`_happy_hare_major_version` all deleted; `_happy_hare_allows_scan_action()` collapsed to an unconditional `action == ACTION_IDLE or action == ACTION_CHECKING`).

None have run against a live V4 Klipper instance yet — all pass `py_compile`/`ast.parse` and are checked against the real V4 source tree line-by-line, but runtime confirmation is still open (tracked in the plan's §4 checklist).

**Remaining work and decisions:**

- **§2.2/§2.2.1 are closed** — the endstop binds to V4's gear rail but remains extension-owned. Its duplicate-binding registry was moved off the foreign `mmu` object onto `NFCGate`; no Happy Hare-owned NFC sensor or `MmuVirtualEndstopSensor` conversion is planned.
- **§2.6** also gained an explicit note (not just an inference from §2.2): `nfc_manager.py` is not a port target for Happy Hare's `extras/mmu/unit/mmu_nfc_reader.py` — no upstream equivalent to converge toward. `scan_jog.py`'s share of the original mapping table (`move_filament`, `wrap_accel`, `mmu_toolhead`, `gear_rail`, etc. — confirmed to live there, not in `nfc_manager.py`) is still fully open — §2.7's scope, not started.
- **§2.8 is closed** — `shared_preload.py` has zero direct `mmu` API surface and `spoolman_client.py` remains version-neutral. The refreshed `tag_handler.py` needed one small V4 adaptation: its imported left-neighbor status read now goes through `NFCGate._read_hh_status_for_gate()` rather than restoring the deleted `hh_status` module.
- **§2.10 is closed** — macro behavior did not change; comments were refreshed during the documentation pass. `_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD` still call the same gcode they did before.
- **§2.11 marked ❓ open question for moggieuk/upstream, not just "not started"** — command-registration reformatting (adopt V4's `BaseCommand`/`COMMAND_REGISTRY` pattern) was identified and fully written up this session, including a verified load-order constraint, but whether `register_command()`'s out-of-tree path is actually meant for a fully separate package (vs. only in-tree-adjacent modules) isn't answerable from source alone. Implementation is deliberately not sequenced until moggieuk confirms — building against a guessed answer risks committing to the include-order requirement for nothing.
- **§2.12 is a high-risk, approval-gated migration** — making `MmuGateMaps` authoritative affects two projects and every stable NFC lifecycle. It must proceed additively through schema approval, dual-write comparison, live soak, authority cutover, and only then legacy removal; no cache/seeding code should be deleted early.
- **New §7, Shared Reader Migration Status** added to the porting plan — called out explicitly per direct request, not left implicit under the scan-jog-heavy §2.4/§2.6/§2.7 work. Confirms (via source, not assumption) that shared-reader is architecturally isolated from every scan-jog change made this session, and that its own two V3 patterns (item 8 above) are now fixed. Status: source-verified complete, same as everything else — real-hardware runtime testing is the one remaining gap.
- **§2.1 local integration is complete, but Happy Hare cutover is blocked** — this repo's reader drivers/factory are current and retain `use_key_b`, but they cannot be deleted until Happy Hare's copies and import path satisfy the six cutover requirements below. **§2.7** also remains open.

**RFID upstream baseline refreshed — 2026-07-12:** `upstream/CW-Development`
was fast-forwarded from `d6fe395` to `9c7fb0f` (12 commits). The imported work
adds the Creality same-spool identity, corrected QIDI material mapping,
Spoolman/rich-read resolution fixes, and a clean restart after left-neighbor
clearance. These are RFID-domain changes, not completion of §2.7's V4 motion
port. The one merge conflict in `tag_handler.py` was resolved by retaining the
new resolution logic while keeping the V4 `NFCLEDManager` import and replacing
the reintroduced `hh_status.read(...)` call with
`NFCGate._read_hh_status_for_gate(...)`.

## Progress against the porting plan

| Plan section | Component | Status |
|---|---|---|
| §2.1 | Reader drivers and `reader_factory.py` | **⚠️ Local integration complete; Happy Hare cutover blocked.** Local copies are current, but six removal/cutover challenges remain before these files become unnecessary |
| §2.1.1 | Happy Hare `use_key_b` support | **⚠️ Open.** Restore and verify Key-B authentication across PN532, PN7160, and RC522 |
| §2.1.2 | Happy Hare factory bus import | **⚠️ Open.** Correct and runtime-test the import of Klipper `extras/bus.py` |
| §2.1.3 | Extension import cutover | **⚠️ Open.** Switch factory and debug-helper imports to `..mmu.unit.nfc` |
| §2.1.4 | Installed V4 reader validation | **⚠️ Open.** Exercise all three readers, rich reads, debug helpers, and Creality Key B on real Klipper |
| §2.1.5 | Remove local hardware files | **⚠️ Blocked by §2.1.4.** Delete the local factory and three drivers only after validation |
| §2.1.6 | Ownership/requirements/logging docs | **⚠️ Open.** Document minimum Happy Hare revision and decide the driver logging contract |
| §2.2 | NFC-as-endstop binding (`mmu_nfc_endstop.py`) | **✅ Complete — 2026-07-12.** Verified correct against real V4 source; V3 branch/dual-detection removed via §2.3 |
| §2.2.1 | NFC endstop ownership cleanup | **✅ Complete — 2026-07-12.** Registry moved to `NFCGate`; extension keeps its own endstop protocol rather than creating a Happy Hare-owned sensor |
| §2.3 | `happy_hare_compat.py` | ✅ Deleted — 2026-07-12. Both functions inlined into `mmu_nfc_endstop.py`, the only caller; no version check survives |
| §2.4 | Preload-hook trigger design (was: `gate_state.py` event-driven vs. polling) | **✅ Complete — 2026-07-12.** Bind-`mmu`-once landed; the poll-loop's own scan-jog trigger removed from `_poll_timer_event` (Happy Hare's hook owns triggering now), poll-suppression/ejection-detection kept; a queue added in `scan_jog.py` so multiple gates preloaded in succession are serviced one at a time automatically |
| §2.4.1 | V4 user-facing documentation | **✅ Complete — 2026-07-12.** Hook-only triggering, AUTO queue behavior, direct V4 state/endstop integration, shared-reader status, driver ownership, and open §2.7 limitations documented |
| **§2.5** | **`hh_status.py` (direct reads)** | **✅ Complete — 2026-07-12.** File deleted entirely; content moved into `nfc_manager.py` as private helpers, reachable from `scan_jog.py` through the `NFCGate` object with zero import |
| §2.6 | `nfc_manager.py` v3→v4 method mapping | **✅ Complete for `nfc_manager.py` — 2026-07-12.** `action` int/string fix (§2.5), two `get_status()` dict-parsing spots ported to direct reads, entire version-detection apparatus removed. The original table's motion-layer entries (`move_filament`, `wrap_accel`, `mmu_toolhead`, `gear_rail`, `gear_short_move_speed`) live in `scan_jog.py`, not this file — that's §2.7's still-open scope |
| §2.7 | `scan_jog.py` motion (homing-move vs. continuous jog) | **✅ Source port complete — 2026-07-12; critically reviewed and fixed across two passes 2026-07-13; hardware validation open.** Obsolete V3 continuous motion, compatibility probes, controller-level speed/rail access, private initializer fallback, and motion G-code fallbacks removed. Motion now uses direct V4 controller and per-gate drive APIs. 2026-07-13 pass 1: fixed two reactor-timer crash bugs (dangling `homing_jog_command()` call, unguarded `get_speed()` division by zero) and removed the now-dead continuous hit-window/trapezoid machinery, which also fixed a latent bug silently disabling the continuous decode-retry backtrack path. 2026-07-13 pass 2: added a top-level exception guard at `step_event()` (the shared reactor-timer entry point for both scan modes) with a safe no-further-motion abort path, fixed an unguarded `mmu` lookup in `start()`, fixed a cross-gate motion hazard in `shift_left_neighbor()`'s partial-failure path, and collapsed a ~40-line duplicated retry-move block in `retry_incomplete_decode()`. 2026-07-13 pass 3 (per direction): reordered the continuous decode-retry chain so the stationary re-read (`retry_continuous_overshoot_position()`) is tried before the directional backtrack jog (`queue_continuous_homing_backtrack_retry()`), and deleted the confirmed-unreachable `queue_continuous_post_backup_retry()` |
| §2.8 | `tag_handler.py`, `spoolman_client.py`, `shared_preload.py` | **✅ Complete — refreshed 2026-07-12.** New RFID resolution logic retained; its left-neighbor HH read and LED import were adapted to the V4 `NFCGate`/`NFCLEDManager` boundaries |
| §2.9 | `NFC_LEDManager.py` (was `LED_effect_mgr.py`) | **✅ Complete — 2026-07-12.** Renamed (file + class) and all V3 support removed (`is_happy_hare_v4()`, the V3 command format, `led_unit_index()`). The `printer`-attribute injection and effect-naming-convention risk remain, cosmetic/residual only |
| §2.10 | `nfc_macros.cfg` and friends | **✅ Complete — 2026-07-12.** These macros should not change and don't; confirmed unaffected by the §2.4 trigger-removal/queue work |
| §2.11 | GCode command registration (adopt `BaseCommand` pattern) | **❓ Open question for moggieuk/upstream — 2026-07-12.** Fully written up, including a verified `printer.cfg` include-order constraint, but not sequenced for implementation: whether `register_command()`'s out-of-tree path suits a fully separate package isn't verifiable from source, only from moggieuk |
| §2.12 | Gate-map-backed spool/UID/`spool_identity` state | **🔴 High risk — design approval required.** Five gated phases: contract, additive HH support, dual-write validation, authority cutover/soak, then legacy removal |

---

## 2026-07-12 — §2.7: remove obsolete direct continuous-jog implementation

Removed `run_direct_continuous_jog()` and all supporting code tied to the V3
`mmu.mmu_toolhead` abstraction: manual lookahead flushing, MCU queue snapshots,
direct-move completion accounting, `wrap_accel()`, and private gear-current
restoration. That direct path had no V4 object to run against and was already
unreachable from `run_continuous_jog()`.

The user-facing `scan_motion_mode: continuous` behavior remains. Its forward
search uses the verified V4 NFC homing move and virtual endstop; only the
obsolete alternative implementation was removed.

### Complete the V4-only motion cleanup

Removed the remaining V3 compatibility functions and fallback branches from
`scan_jog.py`. Short-move speed now comes from
`mmu.drive(gate).mmu_unit.p.gear_short_move_speed`; gear position comes from
the drive's `mmu_gear_stepper`; filament-position reset calls
`initialize_filament_position()` directly; selection, homing, rewind, and jog
motion call V4 methods without `hasattr()` probes or legacy G-code fallbacks.

This completes §2.7 at the source-verification level. Real-hardware scan,
decode-retry, left-neighbor clearance, and rewind testing remains required.

---

## 2026-07-13 — §2.7: critical review of the motion port found and fixed two crash bugs, plus a latent retry bug

A critical read-through of the 2026-07-12 §2.7 motion cleanup (`scan_jog.py`)
found two defects that were guaranteed or plausible reactor-timer crashes,
and a chunking/trapezoid design question that led to a further, larger
cleanup with one behavioral fix.

**🐛 Fixed — `stopped_step_event()` called `homing_jog_command()`, a function
the 2026-07-12 cleanup deleted.** Any stopped-mode scan-jog run with
`debug: 4` hit a guaranteed `NameError` inside the scan reactor timer
(confirmed via `ast`-based undefined-name static analysis, not just
inspection). The dead debug-logging block was removed; the `[SCAN]` message
already logged just above it covers the same information.

**🐛 Fixed — `get_speed()` dropped its `speed > 0.0` validation.** The V3
version guarded against a zero/negative `gear_short_move_speed` and fell back
to 80 mm/s; the V4 rewrite returned
`mmu.drive(gate).mmu_unit.p.gear_short_move_speed` unguarded, so a
misconfigured or unset per-unit speed would raise `ZeroDivisionError` out of
`chunk_interval()` — reachable from `resume_poll_after_rewind()`, inside the
same reactor-timer call stack. Restored the same `80.0` floor, scoped to the
invalid-value case only (not a "missing mmu" fallback — that hard dependency
from the 2026-07-12 cleanup is intentional and unchanged).

**♻️ Removed — the continuous-scan "hit window" / trapezoid position-estimate
machinery**, after confirming by tracing every caller that it no longer does
anything: `estimate_continuous_probe_position()`,
`record_continuous_uid_hit()`, `continuous_uid_hit_window()`,
`continuous_overshoot_backup_mm()`, `should_backup_before_rich_read()`,
`queue_continuous_overshoot_backup()`, `log_continuous_uid_hit_window()`,
`continuous_chunk_interval()`, and the dead non-homing branch of
`run_continuous_jog()`/`continuous_move_source()`. This machinery existed to
reconstruct where mid-flight a UID was detected during a *queued,
non-blocking* move (V3's "Direct Move" technique, already removed
2026-07-12) and then back up to the center of the observed detection window
before a rich tag read. V4 continuous scanning uses `mmu.move_filament(...,
wait=True, homing_move=...)` — a **blocking** NFC homing move that stops
exactly where the endstop triggers. There is no non-blocking in-flight window
left to estimate, and a homing-move stop can't overshoot by construction, so
every hit-window computation had collapsed to a single degenerate point
(`backup_mm` always ≈ 0).

**🐛 Found and fixed in the same pass — `should_backup_before_rich_read()`
was silently disabling the real backtrack retry.** In
`continuous_step_event()`'s `if/elif` resolution chain, the degenerate
hit-window check above returned `True` on essentially every continuous-scan
UID whose rich-tag decode failed, won the `if` branch, performed a
zero-length "backup" as a no-op, and — because it was an `if/elif` chain, not
sequential `if`s — prevented `queue_continuous_homing_backtrack_retry()`
(the real, still-relevant one-way backtrack retry) from ever running. The
practical effect: a tag found via a continuous homing stop whose decode
failed on the first read would silently continue scanning forward instead of
retrying, losing that tag. Removing the dead branch restores the backtrack
retry path. The equivalent dead branch in `retry_incomplete_decode()` (same
`continuous_overshoot_backup_mm()` call, always-zero backup) was collapsed
the same way, calling `queue_decode_retry_move()` directly.

**Kept, deliberately:** `distance_from_trapezoid_time()` /
`homing_distance_from_elapsed()` / `corrected_homing_actual()`. This solves a
different problem — cross-checking `move_filament()`'s reported `actual`
distance against an independent elapsed-time estimate, not mid-flight
position — and whether V4's `move_filament()` has the same actual-distance
reporting quirk HH v3 had is exactly the kind of thing that needs
hardware validation, not a source-level judgment call.

Verification for this pass: `py_compile`, an `ast`-based undefined-name sweep
(clean), and `pyflakes` (clean except two pre-existing, unrelated warnings:
an unused `info_both` import and an unused `gcode` local in `run_rewind()`,
both present before this session's changes). None of this has run against
real Klipper/hardware — see the critical-test list below.

**Critical hardware tests before this lands as validated:**

1. **Continuous-mode decode-retry backtrack** (highest priority — this is the
   behavioral fix, not just cleanup). Force a rich-tag decode failure on the
   first read after a continuous NFC homing stop (e.g. a tag positioned so
   the first read is marginal) and confirm `queue_continuous_homing_backtrack_retry()`
   actually fires: `_scan_decode_retry_mode` becomes `'homing_backtrack'`,
   the gate jogs backward in `_scan_decode_retry_mm` steps, and the tag
   either resolves within `_scan_decode_retry_rounds` attempts or the scan
   cleanly rewinds and exits via `fail_continuous_uid_resolution_after_retries()`
   rather than silently continuing the forward scan past the tag.
2. **Stopped-mode scan-jog with `debug: 4`** — confirm the homing-move debug
   path no longer throws (regression check for the `homing_jog_command()`
   fix).
3. **Continuous-mode scan-jog, full path** — normal rich-tag and UID-only
   spools, end to end, confirming timing/console output still reads sensibly
   with the trapezoid/hit-window logging gone.
4. **Left-neighbor interference and rewind** — not touched directly by this
   pass, but shares decode-retry state (`_scan_continuous_overshoot_backed_up`
   and friends) with the paths above, so a light regression pass is
   warranted.

---

## 2026-07-13, continued — fixed the two crash-risk findings still open, plus a critical-path review of the shared homing move and the decode-retry jog state machine

Follow-up to the same-day pass above: fixed the two previously-reported
findings that were left open (#2 and #4), then did a targeted critical
review of `run_homing_jog()` (the "home to sensor" motion primitive shared
by both `stopped_step_event()` and `continuous_step_event()`) and the
unresolved-rich-read decode-retry jogging state machine, since both are
reachable from either scan mode and both drive real gear motion.

**🐛 Fixed — no exception guard anywhere between `select_gate_quiet()` /
`run_homing_jog()` / `run_mmu_move()` and the Klipper reactor.** These call
V4 mmu methods directly with no fallback and no guard of their own (by
design, from the earlier V4-only cleanup) — but nothing wrapped their call
sites in `stopped_step_event()`/`continuous_step_event()` either, so any
transient failure (servo timeout, gate-table race) would propagate out of
the reactor timer callback, which typically forces a full klippy shutdown.
Added one `try/except` at `step_event()` — the single shared entry point for
both motion modes — instead of chasing every jog call site individually.
On failure it now logs loudly, consoles an `[ERROR]` telling the operator to
verify the gate's physical position, and runs a new `abort_scan_on_error()`
that tears down scan state (LEDs, the single-scan-at-a-time lock, queued
gates, normal polling) **without** attempting further motion — a failed
`select_gate`/`move_filament` means the physical position is unknown, so a
recovery attempt could make it worse. `abort_scan_on_error()` deliberately
does not reuse `resume_poll_after_rewind()` (that computes its delay via
`chunk_interval()`/`get_speed()`, which touches `mmu` again right after
`mmu` just failed) — it restarts polling after a fixed delay instead.

**🐛 Fixed — `start()` looked up `'mmu'` outside its own try/except.** Per
`NFCGate._get_mmu()`'s own docstring, `'mmu'` can legitimately be
unregistered this early if config include order put this extension ahead of
it. Moved the lookup inside the existing try/except so that race is handled
the same way a failed `initialize_filament_position()` already was, instead
of raising past it.

**🐛 Found and fixed — `shift_left_neighbor()` could leave the wrong gate
selected on partial failure, and a later rewind would silently drive it.**
`select_gate_quiet(left_gate)` → clearance move → `select_gate_quiet(own
gate)` all lived in one `try`, so if the clearance move failed *after*
selecting the neighbor, the `except` returned `False` without ever
reselecting `gate._gate`. The mmu was then left pointed at the **left
neighbor's** gate while scan-jog's own bookkeeping still assumed its own
gate was active. `run_rewind()`'s `run_mmu_move()` does not itself select a
gate (it trusts whatever is already selected), so the next rewind would jog
the *neighbor's* filament by `fast_rewind` mm — a genuine cross-gate motion
hazard, not merely a wrong-log-message bug. Restructured so the reselect of
`gate._gate` runs in a `finally`, unconditionally; if that reselect *itself*
fails, it now raises (rather than being silently skipped), which
`step_event()`'s new guard catches and aborts safely rather than continuing
while the active gate is unknown. This bug predates this session — it is
not something the 2026-07-12/13 V4 motion changes introduced — but it sits
directly in the same motion-safety critical path.

**♻️ Simplified — `retry_incomplete_decode()`'s stopped-mode fallback was a
~40-line inline copy of `next_decode_retry_move()` + `queue_decode_retry_move()`**,
duplicated instead of calling them (confirmed line-by-line equivalent:
identical oscillating-offset math, identical jog/LED/logging tail, identical
warning message text). Collapsed to a single call, matching the continuous-mode
branch immediately above it. This was a real future-drift risk: any fix to
the shared retry algorithm would have had to be made in two places to
actually apply to both scan modes.

**♻️ Resolved — the two retry-path findings above, per explicit direction:**

- **Reordered** `continuous_step_event()`'s `elif` chain so
  `retry_continuous_overshoot_position()` (stationary, no-motion re-read) is
  checked **before** `queue_continuous_homing_backtrack_retry()` (directional
  backtrack jog), matching the intent already stated in the former's own log
  message ("retrying rich tag parse attempt %d/%d **before recenter**"). Now
  every incomplete decode gets up to 3 free in-place re-reads (its own
  `max_attempts=3`, tracked by the separate `_scan_continuous_overshoot_position_attempts`
  counter, not `_scan_decode_retry_rounds`) before committing to a 5mm
  backtrack jog — cheaper, and avoids moving a marginal-but-recoverable read
  further out of the reader's range before even trying again in place. Pure
  reordering; neither function's internals changed.
- **Deleted** `queue_continuous_post_backup_retry()` and its dead call site
  in `continuous_step_event()` — confirmed unreachable by control-flow
  tracing (not just inspection), so removal changes no runtime behavior,
  only removes a function that looked like it was part of the live retry
  path when it never actually ran.

**Confirmed intentional, not a bug:** the forward/backward asymmetry where
positive decode-retry jogs go through `run_homing_jog()` (endstop-aware,
can stop early) and negative ones go through `run_mmu_move()` (always
travels the full requested distance) — the NFC virtual endstop is
directional, so an early stop is only meaningful moving toward the tag, not
away from it. Also confirmed dead, low-risk: `run_homing_jog()`'s
`homing_move=-1` branch (`mm < 0`) — every caller only ever passes `mm > 0`,
same as previously reported.

Verification: `py_compile`, `ast` undefined-name sweep (clean), `pyflakes`
(clean, same two pre-existing warnings as before). None of this has run
against real hardware.

---

## 2026-07-14 — shared-reader separation design work found `_has_per_lane_readers` is dead

While designing how to extract the shared reader out of `NFCGate` into its
own class (in support of Happy Hare eventually absorbing the state-engine
role), mapped the actual shared-reader ↔ Happy Hare interface concretely:
it's not just `MMU_GATE_MAP NEXT_SPOOLID`, it's a five-point stage → validate
→ commit protocol (`_shared_stage_next_spool_id()`'s async-deferred
`NEXT_SPOOLID` dispatch, `_shared_apply_bypass_spool()`'s bypass branch, and
`_NFC_SHARED_PRELOAD`'s `PRELOAD_CHECK`/`PRELOAD_COMMIT`/`PRELOAD_CLEAR_ASSIGNED`
handshake into `shared_preload.py`'s `SharedPreloadCoordinator`).

**⚠️ Found — `NFCGate._has_per_lane_readers` is initialized `False` in two
places in `nfc_manager.py` and never set `True` anywhere** (confirmed by
grep across the whole file, not inference — no code populates it from the
module-level `_lane_instances` registry). This matters because
`SharedPreloadCoordinator.clear_assigned()` reads it to decide whether a
Happy Hare gate-map assignment it's reconciling against was expected (a
per-lane reader claimed the spool first) or unexpected (logged as a
console warning). With the flag permanently `False`, every
`PRELOAD_CLEAR_ASSIGNED` reconciliation on a hybrid (per-lane + shared)
install takes the "unexpected assignment" warning branch even in the
normal, expected case — not a crash, but a false-positive warning on every
such reconciliation that would undermine trust in the message. Not fixed
yet — added as an explicit action item in the porting plan (§4, §7) rather
than fixed inline, since it sits directly on the interface boundary the
shared-reader extraction needs to design (§7's separation plan), so it's
worth resolving before that boundary is locked in rather than after.

Not fixed this pass; not verified against real hardware (this is dead-code
analysis, no code changed).

---

## 2026-07-14, continued — extracted `SharedNFCReader`; fixed `_has_per_lane_readers`

Executed the separation plan above, minus the poll-engine split (deliberately
deferred — see below). Scope was explicit: extract what's cleanly separable,
split construction, fix the dead flag, verify nothing else breaks. Did not
touch `_poll_timer_event()`/`_poll()`, `__init__`, or `_handle_connect()`'s
structure.

**✨ New `klippy/extras/nfc_gates/shared_reader.py`, `class SharedNFCReader(NFCGate):`.**
Subclassing rather than a standalone class was the key decision that made
this tractable within scope: since `SharedNFCReader` inherits `__init__` and
`_handle_connect()` unmodified, and those already correctly initialize every
shared-only attribute whenever `self._shared` is `True` (regardless of which
class the instance actually is), none of that constructor logic needed to
move or change. What moved: all ~38 `_shared_*`-named methods (identified
by AST, not regex, after an earlier crude regex pass produced false
positives on nested closures like `_run`/`mark`), plus `cmd_NFC_SHARED` and
`_read_mmu_pending_timeout` (shared-only despite not having the `_shared_`
prefix). `get_status()` was split rather than moved wholesale: the base
`NFCGate` version now returns lane-only fields with the shared-only keys
hardcoded to their empty defaults; `SharedNFCReader.get_status()` overrides
it, calling `super().get_status()` then filling in the real
`pending_spool_id`/`preload_spool_id`/`has_per_lane_readers`/etc. values —
the standard template-method shape, and it keeps the external dict shape
`printer['nfc_gate shared']` template code depends on identical.

Mechanically: extracted exact method source via `ast` (`FunctionDef.lineno`/
`end_lineno`), built a delete-mask over `nfc_manager.py`, removed all target
ranges plus `get_status()`'s old body in one pass (not 39 sequential `Edit`
calls — too fragile for this many non-contiguous, similarly-shaped
deletions), and verified with `py_compile` + an AST-based undefined-name
sweep before writing anything back. Found and fixed three import gaps this
way (`shared_preload`, `rc522_driver` needed by `_shared_help()`'s low-level
debug-command listing) that a naive text-based extraction would have missed
until runtime.

**Byproduct find:** the class body defined `shared_summary_line()` **twice**
— Python silently keeps only the last definition, so the first (different
output format) was dead code. Extraction naturally took the live version;
confirmed via `ast` that this is exactly what happened, not an accidental
drop.

**♻️ `klippy/extras/nfc_gate.py`'s `load_config_prefix()`** now reads
`config.getboolean('shared', False)` to choose `SharedNFCReader` vs
`NFCGate` *before* constructing, instead of one constructor branching
internally after the fact. No circular import: `nfc_gate.py` imports both
`nfc_manager.py` and `shared_reader.py`; `shared_reader.py` imports
`nfc_manager.py`; `nfc_manager.py` imports neither `shared_reader.py` nor
`nfc_gate.py` — confirmed one-directional by grep, not just reasoned about.

**🐛 Fixed — `_has_per_lane_readers`** (the finding above). Now computed in
`_handle_connect()`: `any(not shared and enabled for g in _lane_instances)`.
Timing works because `klippy:connect` fires only after every `[nfc_gate ...]`
config section has already run `load_config_prefix()` and appended itself to
`_lane_instances` — confirmed via Klipper's config-then-connect event
ordering, not assumed.

**Verified unaffected, not just assumed:** `shared_preload.py` needed zero
changes (`SharedPreloadCoordinator` already duck-types its `gate` argument).
The module-level registry (`_lane_instances`, `_shared_instance`) and
Klipper's `printer['nfc_gate shared']` resolution both key off config
section name / list membership, not Python class — grepped the whole
`klippy/extras/` tree for `isinstance(..., NFCGate)` and found none, so
there was nothing a subclass could silently break.

**Cleanup byproduct:** seven now-genuinely-unused imports removed from
`nfc_manager.py` (`shared_preload`, `EVENT_AUTO_CREATE`, `EVENT_RELEASE`,
`EVENT_SPOOL_READY`, `EVENT_TAG_READ`, `EVENT_UNRESOLVED`,
`shared_effect_name`, `CurrentTag`, `TOOL_GATE_BYPASS`) — all either moved
to `shared_reader.py` with the code that uses them, or (in `CurrentTag`'s
case) were already dead before this session and just happened to be in the
same import block being rewritten anyway.

**Deliberately not touched, per explicit direction — the poll engine.**
`_poll_timer_event()` and `_poll()` still live on `NFCGate`, still branching
on `self._shared` internally (six branch points, one implicit via
`_scan_enabled` being forced `False` at config time rather than checked
directly in the poll function itself — see the earlier "where does the poll
timer sit" discussion). `SharedNFCReader` inherits both unmodified. That
split is real design work — deciding whether it's a template-method split,
a duplicated-and-trimmed pair, or something else — not a mechanical move,
and is intentionally left for a separate pass.

Verification: `py_compile` and an `ast`-based undefined-name sweep on all
three touched files (clean), `pyflakes` (clean except two pre-existing,
unrelated warnings carried over unchanged by the extraction: an unused
`last_action` local in `_shared_next_action()`, an unused `name` local in
`load_config_prefix()`). `nfc_manager.py`: 3595 → 2795 lines.
`shared_reader.py`: 867 new lines. None of this has run against real
Klipper/hardware — this is a structural refactor with no behavior change
intended (`SharedNFCReader` inherits everything it doesn't override), but
that claim itself is only as good as the static verification above until
someone starts a printer with a `[nfc_gate shared]` section configured.

---

## 2026-07-14, continued — real Happy Hare compatibility harness (`test/hh_compat/`), and it immediately found a real bug

The claim at the end of the previous entry — "that claim is only as good as
the static verification above" — no longer has to be a claim. A real local
Happy Hare checkout exists on this machine
(`~/Documents/GitHub/Happy-Hare`, `origin` = `moggieuk/Happy-Hare`, on
branch `rfid`), so this pass builds a harness that checks the previous
session's work against real Happy Hare V4 source instead of trusted-but-
unverified porting notes.

**How the harness works, concretely** — see `test/hh_compat/README.md` for
the full writeup:
- `bootstrap.py` merges this repo's `klippy/extras` and the real Happy
  Hare checkout's `extras/` into one synthetic `klippy.extras` namespace
  package (`__path__ = [ours, theirs]`), so `from ..mmu.mmu_constants
  import ...` inside our code resolves against the *real* file — no
  copying or symlinks, purely `sys.modules` construction. This only works
  because Happy Hare's `extras/mmu` has no `__init__.py` (a namespace
  package) and `mmu_constants.py` has zero imports of its own, so
  importing it doesn't transitively pull in the rest of the
  Klipper-core-dependent MMU stack (kinematics, `mcu.py`, `toolhead.py`)
  that isn't checked out on this machine.
- `test_mmu_api_surface.py`: static, `ast`-based checks (not import) that
  every `mmu.*`/`mmu_constants.*` touchpoint `nfc_gates` depends on exists
  in the real source with a compatible shape — formalizes what was
  previously a one-off manual grep pass into something re-runnable any
  time the Happy Hare checkout updates. **All 11 checks pass against
  `rfid`**: `mmu_constants.py`'s 7 required constants, `MmuController`'s
  instance attrs (`action`, `num_gates`, `tool_selected`, `gate_selected`,
  `filament_pos`, `gate_maps`) and methods (`drive`, `select_gate`,
  `initialize_filament_position`, `wrap_suppress_visual_log`),
  `move_filament()`'s full keyword signature (`endstop_name`, `wait`
  included), `MmuGateMaps`/`MmuDrive`/`MmuUnit` attribute shapes, the
  `gear_short_move_speed` `ParamSpec`, and — the one that actually
  mattered most, since it's the one place `scan_jog.py` reasons about a
  raw stepper return value — `MmuStepper.get_position()` really does
  return a list with position first (`[commanded_pos, 0., 0., 0.]`),
  confirming the `pos[0]` indexing in `mmu_gear_position()`.
- `test_shared_reader_compat.py`: dynamic tests — actually construct
  `SharedNFCReader` and plain `NFCGate` against `FakeConfig`/`FakePrinter`
  (real value semantics, not bare `MagicMock`s, since our code branches on
  config values) and a `build_fake_mmu()` spec'd from the same verified
  attribute list (`MagicMock(spec=[...])`, not a bare `MagicMock()` that
  would silently swallow a typo'd attribute access). The I2C/SPI reader
  driver construction is patched out — real hardware plumbing, orthogonal
  to Happy Hare API compatibility.

**🐛 Found — and fixed — a real crash bug in the previous extraction pass,
not a Happy Hare compatibility gap.** `NFCGate.__init__` still did
`self.reactor.register_timer(self._shared_led_failsafe_event)`
**unconditionally**, but `_shared_led_failsafe_event` moved to
`SharedNFCReader` in the same-day extraction earlier. Every plain per-lane
`NFCGate` construction — i.e. every normal `[nfc_gate laneN]` section —
crashed with `AttributeError` at `__init__`. This wasn't caught by the
extraction's own `py_compile`/`pyflakes`/AST-undefined-name verification
at the time because `self.<name>` is a dynamic attribute lookup — none of
those tools can know whether `self` will actually have that attribute at
runtime without knowing its concrete class, and a bare-name check doesn't
even look at attribute expressions. This is exactly the kind of bug this
harness exists to catch by actually constructing the object. Before fixing,
every *other* now-moved-method reference remaining in `nfc_manager.py` (18
call sites across 11 method names) was individually checked against its
surrounding control flow — all 18 are properly guarded by `if self._shared:`
either directly or via a registration that's itself gated (e.g. the
`idle_timeout:printing`/`idle_timeout:ready` handler registration), so this
was the one genuine gap, not a symptom of a wider pattern. Fix: made the
timer registration itself conditional on `self._shared`, `None` otherwise
— matches the only two read sites, both already on `SharedNFCReader` and
already only ever invoked when `self._shared` is `True`.

All 20 tests (11 static + 9 dynamic) pass against the real `rfid` branch
after the fix. `nfc_manager.py` still compiles clean, `pyflakes` still
shows only the same two pre-existing, unrelated warnings.

**Scope note:** this harness validates the shared-reader dependency chain
(`SharedNFCReader`, `NFCGate` base, `GateState`, `tag_handler`,
`spoolman_client`, `KlipperInterface`, `NFC_LEDManager`) against Happy
Hare's mmu API surface. It does not attempt hardware I/O, does not exercise
`_poll_timer_event()`/`_poll()`'s full branching logic (deliberately
unrefactored, per the standing "hold off on poll resolution" direction),
and needs a full Klipper core checkout (not just Happy Hare's `extras/`) to
go any further toward true integration testing than it already does.
Embedding this code into the Happy Hare tree itself, and wiring it into
the `rfid` branch as a base module, remain separate, larger pieces of work
this harness was built to de-risk, not substitute for.

---

## Happy Hare gate-map state-ownership migration — 🔴 high risk

> [!CAUTION]
> Do not treat this as an implementation-ready cleanup. The current NFC state
> and seeding paths remain the recovery baseline until the phased §2.12 plan
> passes maintainer approval, dual-write comparison, live hardware testing,
> soak time, and rollback verification.

Add per-gate UID and `spool_identity` fields to Happy Hare's persisted
`MmuGateMaps` model (§2.12), then remove `GateState.current_uid` and
`GateState.current_spool` as duplicate stable lane state. There is no
maintenance benefit in copying spool/tag identity into the NFC state manager
when status, filament metadata, color, temperature, spool ID, and speed
override already share one persisted gate-map lifecycle.

This action requires coordinated changes on both sides:

- Happy Hare: constants, `_gate_map_vars`, default/migration normalization,
  public update API, persistence, status exposure, per-unit namespacing, and
  clear/reset behavior.
- This extension: rewrite stable lookups to use `mmu.gate_maps`; remove the
  one-shot Happy Hare seed/cache-sync system; keep only transaction-local tag
  observations and absence debounce state; write accepted UID/identity/spool
  atomically; and clear gate-map identity on physical removal.
- Verification: restart persistence, old-variable migration, gate-count
  changes, multi-unit behavior, manual gate-map edits, removal, offline swaps,
  atomic updates, and left-neighbor identity checks after restart.

The rewrite must cover normal polling, scan-jog snapshots and neighbor lookup,
status output, external gate-map changes, rewind/restore behavior, and the
existing `APPLY`/`CLEAR_CACHE`/`HH_SYNC` command surface. Spoolman's HTTP cache
is separate lookup optimization and remains in place.

Spoolman remains authoritative for UID → spool-record lookup. `MmuGateMaps`
becomes authoritative for the UID and same-spool identity currently associated
with each physical gate.

**Current authorization/status:** documentation and design inventory only. No
authority cutover or legacy cache removal is approved yet.

---

## Happy Hare driver/factory cutover challenges — ⚠️ open

The local PN532, PN7160, RC522, and `reader_factory.py` files are still
required. Bringing the RFID upstream versions into this repository completed
the local hardware-layer refresh; it did **not** make Happy Hare's installed
copies safe to import yet.

These six steps must be completed before deleting the local hardware layer:

- [ ] **1. Restore and verify `use_key_b` in Happy Hare's three drivers.**
  `mifare_read_authenticated_blocks(...)` must accept and propagate
  `use_key_b` through PN532, PN7160, and RC522 authentication. Without it,
  Creality CFS/K1/K2 rich reads silently fall back or fail.
- [ ] **2. Correct Happy Hare's factory bus import.** In
  `extras/mmu/unit/nfc/reader_factory.py`, ensure the import resolves the real
  Klipper `extras/bus.py` from its installed package location. The expected
  relative form is `from .... import bus as bus_module`, subject to an actual
  Klipper import test.
- [ ] **3. Switch this extension to Happy Hare's NFC package imports.** Replace
  local factory/debug-helper imports with `..mmu.unit.nfc.reader_factory`,
  `..mmu.unit.nfc.pn532_driver`, and `..mmu.unit.nfc.rc522_driver`. PN7160 is
  instantiated internally by the factory and needs no direct manager import.
- [ ] **4. Validate the installed integration.** Run import/compile checks and
  initialize PN532, PN7160, and RC522 readers in a real Happy Hare V4 Klipper
  environment, including UID, rich-read, low-level-debug, and Creality Key-B
  paths.
- [ ] **5. Delete the four local hardware-layer files only after step 4.**
  Remove `reader_factory.py`, `pn532_driver.py`, `pn7160_driver.py`, and
  `rc522_driver.py` from `nfc_gates/`, then verify no stale imports, installer
  links, or documentation references remain.
- [ ] **6. Update ownership and installation documentation.** State that the
  drivers/factory are provided by Happy Hare V4's RFID package and document
  the minimum compatible Happy Hare revision. Explicitly accept or replace
  Happy Hare's reduced `nfc/log.py` behavior, because changing ownership may
  move driver diagnostics from this extension's dedicated `nfc_reader.log`
  into Klipper logging.

**Cutover rule:** do not mark the local files obsolete or remove them until all
six boxes are complete. The current local implementations remain authoritative
for this extension in the meantime.

---

## 2026-07-12 — §2.2.1: keep NFC endstop ownership inside the extension

Confirmed the stashed and restored V4 implementations were identical. The
`mmu._nfc_endstops_by_gate` dictionary was used only for this extension's
duplicate-binding check; Happy Hare never consumed it, while scan-jog obtains
the endstop directly from `NFCGate._mmu_nfc_endstop`. Moved the dictionary to
`NFCGate._nfc_endstops_by_gate` and stopped injecting private state onto
Happy Hare's controller.

The virtual endstop itself remains in `mmu_nfc_endstop.py`. It still attaches
to the V4 gear rail because that is how Klipper homing reaches it, but there is
no plan to create an NFC endstop sensor inside Happy Hare or upstream this
extension-specific implementation.

---

## 2026-07-12 — §2.1: integrate upstream reader drivers and factory

Marked the hardware layer complete after bringing in the upstream PN532,
PN7160, and RC522 drivers plus `reader_factory.py`. Verified all three
authenticated-block APIs still accept and propagate `use_key_b`, preserving
Creality authentication. In this repo's `nfc_gates` package,
`from .. import bus as bus_module` resolves the real Klipper `extras/bus.py`,
so the earlier concern about a nonexistent `extras/mmu/unit/bus.py` does not
apply to the final layout. The full local logging implementation remains by
design. The refreshed local layer is complete; switching ownership to Happy
Hare remains blocked on the six cutover challenges above.

---

## 2026-07-12 — refresh from RFID `CW-Development` through `9c7fb0f`

Fast-forwarded the repository baseline by 12 RFID commits. The merged behavior
now preserves `spool_identity` through continuous-scan reuse, performs rich
parsing only when needed to distinguish a possible left-neighbor match, checks
manufacturer identity before metadata auto-create, and restarts the current
lane scan from clean state after moving an interfering left neighbor. Creality
now derives a UID-independent `creality_<numeric_hash>` identity from its
decoded payload; QIDI material codes were aligned with QIDI's published table.

V4 reconciliation was limited but necessary: upstream still referenced the
deleted `hh_status` module and pre-rename `LEDEffectManager` in
`tag_handler.py`. The conflict resolution kept all imported RFID logic while
routing Happy Hare state through the existing `NFCGate` V4 adapter and LEDs
through `NFCLEDManager`. The combined modules pass `py_compile`.

Documentation was reconciled at the same time: the command reference now lists
Creality identity, the QIDI-specific key is clearly marked as documented but
not implemented, and the new QIDI reference is linked from the README.

---

## 2026-07-12 — §2.4.1: consolidated V4 documentation pass

Updated the README, installer guide, configuration reference and template,
command reference, architecture decisions, and implementation overview to
match the landed V4 changes. Removed V3/version-gated behavior and the obsolete
polling-trigger fallback; documented the Happy Hare post-preload hook as the
sole automatic scan-jog trigger and explained trusted AUTO request queuing.

Also made the cutover state explicit: shared-reader code is source-verified,
the endstop binds directly through V4's drive/gear-rail API, card drivers and
their factory are transitional pending their move into Happy Hare, and §2.7's
per-lane motion port plus live-hardware verification remain open.

---

## 2026-07-12 — §2.6: port remaining V3 patterns in `nfc_manager.py`; §2.8 confirmed; shared-reader status called out

**Why:** direct instruction to finish §2.6 and mark §2.8 complete — "no reason for backport support, this is a V4 and later code repo." A whole-file `mmu.<attr>` scan of `nfc_manager.py` was run first (not just the pre-existing table's entries) to make sure nothing was missed.

#### 🔎 Scan found the table's entries live elsewhere

`move_filament`, `wrap_accel`, `mmu_toolhead`, `gear_rail`, `gear_short_move_speed`, `_restore_gear_current` — none of these appear anywhere in `nfc_manager.py`. They're all in `scan_jog.py` (the motion layer, §2.7's scope, not yet started). What `nfc_manager.py` actually had left were two `get_status()` dict-parsing spots and the version-detection apparatus.

#### ♻️ `_shared_led_target()` ported

Was: `getattr(mmu, 'num_gates', None)`, falling back to parsing `mmu.get_status()['gate_spool_id']`'s length if that came back `None`. Confirmed `mmu.num_gates` is a real, always-present V4 attribute (`mmu_controller.py:49`) — the fallback could never trigger on V4. Now: `mmu.num_gates` directly, via the cached `self._get_mmu()` accessor instead of a fresh `printer.lookup_object('mmu', None)` lookup, no fallback.

#### ♻️ `_shared_bypass_selected()` ported

Was: parsed `mmu.get_status()['tool']`, compared against a hardcoded `-2`. Now: `mmu.tool_selected == TOOL_GATE_BYPASS`, both confirmed directly against source (`mmu_controller.py:145/2556` for the attribute, `mmu_constants.py:72` for the constant — `TOOL_GATE_BYPASS = -2`, confirming the old hardcoded value was correct, just sourced the wrong way). `TOOL_GATE_BYPASS` added to the existing `mmu_constants` import block.

#### 🗑️ Entire V3/V4 version-detection apparatus removed

`_detect_happy_hare_version()`/`_happy_hare_major_from_version()` (free functions) and `_refresh_happy_hare_version()`/`_happy_hare_version()`/`_happy_hare_major_version()` (instance methods, plus the `_HAPPY_HARE_VERSION` cache attribute and its `__init__` seed) existed for exactly one purpose: gating whether `action=checking` counts as scan-safe behind an "is this actually V4" check. `_happy_hare_allows_scan_action()` collapsed to:
```python
def _happy_hare_allows_scan_action(self, action):
    return action == ACTION_IDLE or action == ACTION_CHECKING
```
`_happy_hare_major_from_version()` then had zero callers and was deleted. `_detect_happy_hare_version()` (the version-*string* lookup, distinct from the major-version-int parsing) was kept — `NFC_DOCTOR`'s diagnostic output still calls it directly, simplified from a three-way "does this version support checking" branch to reporting the plain detected version string.

#### ✅ Verified

`nfc_manager.py` and `scan_jog.py` (the one external caller of `_happy_hare_allows_scan_action`, signature unchanged) both pass `py_compile`. Grepped for stale references to every removed symbol — none remain outside the one intentionally-kept `_detect_happy_hare_version()`.

#### ✅ §2.8 confirmed complete

`shared_preload.py` scanned the same way: zero direct `mmu.<attr>` access found anywhere in the file — it operates entirely through the macro/gcode layer (`MMU_GATE_MAP NEXT_SPOOLID=...`), already fully version-agnostic. No code change needed for `tag_handler.py`/`spoolman_client.py`/`shared_preload.py`.

#### 📝 Shared Reader Migration Status — new §7 in the porting plan

Called out explicitly per direct request, not left implicit. Confirmed via source (not assumption) that shared-reader is architecturally isolated from every scan-jog-focused change made this session: `_scan_enabled` is forced `False` for shared instances (so §2.4's poll-trigger removal and new queue are no-ops for it), and neither `_active_scan_gate`/`_scan_queue`/`manual_jog_scan()` nor `_happy_hare_allows_scan_action()` are referenced anywhere in `shared_preload.py` or the ~30 `_shared_*` methods in `nfc_manager.py`. Combined with this entry's two ported fixes, shared-reader status is now: source-verified complete, real-hardware testing the one open item — same standing as the rest of this plan.

---

## 2026-07-12 — §2.4: remove the poll-loop scan-jog trigger; add AUTO-request queuing

**Why:** Happy Hare's post-preload hook (`_NFC_SCAN_JOG_PRELOAD`/`_NFC_SHARED_PRELOAD`, calling `NFC GATE=<n> JOG_SCAN=1 SOURCE=AUTO`) now owns deciding *when* to start a scan-jog. The poll loop's own independent 0→1 gate-status edge detection, which used to make that same decision on a completely separate path, became redundant logic worth removing rather than leaving as a second, silently-coexisting trigger.

#### 🗑️ Scan-jog trigger removed from `_poll_timer_event`

The `if prev == GATE_EMPTY and curr >= 1: ...` arm-block and the large "fire scan once Happy Hare is scan-safe" block (ending in `self._start_scan_mode(...)`) are gone from `nfc_manager.py`. **What was explicitly kept**, per a deliberate scoping decision before touching anything: poll suppression while Happy Hare already has an opinion about the gate (loaded+matched → skip the I2C read; assigned → skip; ejected → clear cache and resume). Neither of those depends on the trigger logic that was removed — both just needed `curr`, not the `prev`→`curr` edge comparison.

#### 🗑️ Dead-code cascade

Once the trigger was gone, several things it alone had fed became dead and were removed too: the `_scan_pending`/`_scan_deferred_notified`/`_scan_idle_ready_time` `__init__` state; the `_prev_gate_status` attribute and its two cold-start bootstrap setters in `_startup_check_unknown_gate_event()`/`_delayed_init()` (their sole purpose — "so a pre-loaded gate never triggers a scan on the first poll" — no longer applies); `NFCGate._start_scan_mode()`, a one-line delegator whose only caller was inside the removed block (confirmed via grep before deleting — `scan_jog.py`'s hook/manual path calls `scan_jog.start()` directly, never through this wrapper). `_happy_hare_allows_scan_action()` and `_prepare_scan_jog()` were **not** touched — both are still called from `scan_jog.py`'s `manual_jog_scan()`, the hook/manual entry point.

#### 📝 Module header updated

Added a "Scan-jog triggering" section to `nfc_manager.py`'s header docstring stating explicitly that triggering now comes from Happy Hare's hook, not from polling, and describing what the retained poll-suppression logic is actually for.

#### 🐛 Gap caught and fixed before it shipped: no queuing on the hook path

Caught mid-change, before verification was declared done: the removed poll-loop trigger had its own re-arm-and-retry-every-3-seconds behavior for "another gate is already scanning" — `manual_jog_scan()` (the hook/manual entry point) never had an equivalent. It just warns and gives up (`gate.__class__._active_scan_gate is not None` → log a warning, return). Neither Happy Hare's hook (`_MMU_POST_PRELOAD` fires once, synchronously, fire-and-forget) nor Klipper's event system provide retry semantics — that behavior was entirely this add-on's own, and deleting the poll loop without replacing it would have silently broken multi-gate installs (preload gate 1, then gate 3 while gate 1 is still scanning → gate 3 would just never scan automatically).

**Fix, in `scan_jog.py`:**
- `NFCGate._scan_queue = []` added as a class attribute alongside the existing `_active_scan_gate` lock (`nfc_manager.py`).
- `manual_jog_scan()`'s busy-check: when `trusted_auto` (i.e. the call came from Happy Hare's hook, not a manual console command) and another gate is scanning, the requesting gate number is appended to the queue (de-duplicated) instead of just failing. Manual console `JOG_SCAN=1` keeps the original immediate warn-and-return — a human can just retry themselves, matching the original code's behavior (only the poll loop's own automatic path ever re-armed itself; manual invocations never did).
- `_drain_scan_queue(gate)` added: pops the next queued gate and re-issues the exact same `NFC GATE=<n> JOG_SCAN=1 SOURCE=AUTO` gcode the hook would have sent, deferred via `reactor.register_async_callback` (matching the async-dispatch pattern already used elsewhere in this file for post-scan Happy Hare interactions — not called inline, to avoid re-entering the gcode dispatcher from deep inside another command's tail). Called from both `finish()` and `rewind_and_exit()`, right after each releases `_active_scan_gate`.
- Re-issuing the full command (rather than calling some lower-level "just start" function) means a queued gate that changed state while waiting — e.g. ejected — gets caught by `manual_jog_scan()`'s normal validation instead of assumed still valid.

#### ✅ Verified

`nfc_manager.py` and `scan_jog.py` both pass `py_compile`. Grepped for stale references to every removed symbol (`_scan_pending`, `_scan_deferred_notified`, `_scan_idle_ready_time`, `_prev_gate_status`, `_start_scan_mode`) across `klippy/` — none remain. Confirmed `cmd_NFC`'s `JOG_SCAN` dispatch and `manual_jog_scan()` were never touched by the trigger removal — the manual/hook entry point was intact throughout.

#### 💡 Not yet verified at runtime

Multi-gate queuing behavior (gate 3 preloaded while gate 1 is scanning → gate 3 starts automatically once gate 1 finishes) is source-verified only. This needs a real multi-gate test on live hardware before being trusted in the field — tracked alongside the rest of this plan's runtime-verification items in §4.

---

## 2026-07-12 — §2.9: remove all V3 support from `NFC_LEDManager.py`

**Why:** no reason to check for backports — this branch is a V4 repo, full stop. Same reasoning as the `happy_hare_compat.py` deletion (§2.3), applied to the one remaining file that still branched on Happy Hare version.

#### 🗑️ `is_happy_hare_v4()` deleted

The `callable(getattr(mmu, 'drive', None))` duck-type check — gone, along with every branch it gated.

#### ♻️ `hh_led_script()` collapsed to one unconditional builder

Was two branches: a V4 direct-effect command (`_MMU_SET_LED_EFFECT EFFECT=%s REPLACE=1`) and a V3 `MMU_SET_LED ... GATE=/UNIT=/EXIT_EFFECT=/DURATION=` command. Now only builds the V4 form. The `duration`/`gate`/`unit`/`direct_effect` parameters — which existed solely to build the deleted V3 command — are gone from the function signature.

#### ♻️ `play_named()` simplified

`v4_direct = is_happy_hare_v4(self.printer)` and the conditional effect-name selection it drove are gone; `hh_led_script(display_effect)` is called directly, and `_started()` always registers the auto-release timer unconditionally. `gate`/`unit` parameters removed from the signature — they were pass-through only, feeding the now-deleted V3 command builder.

#### 🗑️ Dead code cascade in `play_shared()`

Removing `play_named()`'s `gate`/`unit` parameters left `play_shared()`'s local `gate = mcu_index if segment == 'gate' else None` / `unit = None if segment == 'gate' else led_unit_index(led_unit)` computation with nothing to feed — deleted, along with the now-unreferenced call to `led_unit_index()`. `play_lane()`'s pass-through of `gate=gate` into `play_named()` removed the same way (its own `gate` parameter, used for `lane_effect_name()`/the target string, is untouched).

#### 🗑️ `led_unit_index()` deleted

A module-level helper whose only remaining caller was the `play_shared()` code just removed. Confirmed via grep it isn't imported anywhere else in the codebase before deleting.

#### ♻️ `release()` simplified

`if is_happy_hare_v4(self.printer): ... else: script = "MMU_GATE_MAP QUIET=1"` collapsed to the V4 body unconditionally.

#### ✅ Verified

No remaining `is_happy_hare_v4` references anywhere in `klippy/` (grepped). Call sites of `hh_led_script()`/`play_named()` checked against their new signatures. `NFC_LEDManager.py` passes `py_compile`.

#### 💡 Left alone on purpose

`_v4_effect_registry()`/`_remember_v4_effect()`/`_release_v4_effect_after()` and the `self.printer._nfc_v4_led_effects` storage key still carry a `_v4_` qualifier that's now redundant (there's nothing else to compare against) — cosmetic naming residue, not touched. The foreign-attribute injection onto `printer` (already flagged in porting-plan §2.9 before this change) is unaffected either way.

---

## 2026-07-12 — §2.5: delete `hh_status.py` entirely

**Why:** revisited after landing the direct-reads rewrite (below) — with the rewrite done, every remaining external touchpoint turned out to be reachable through the `NFCGate` object `scan_jog.py` already receives as an argument, removing the last reason for a separate shared module.

#### ♻️ Content moved into `nfc_manager.py`

`GateSnapshot` → `_GateSnapshot`, `FullSnapshot` → `_FullSnapshot`, `gate_snapshot()` → `_gate_snapshot()`, `full_snapshot()` → `_full_snapshot()`, `action_label()` folded into `.action_label()` methods on both snapshot classes, `_ACTION_LABELS` and the `mmu_constants` imports moved in as module-level private names. Leading underscores added since these are no longer a cross-file public surface.

#### ✨ Two additions to close the gap that made `scan_jog.py` need an import

- `.empty` property added to `_GateSnapshot` (`self.status == GATE_EMPTY`) — replaces `scan_jog.py`'s `hh.status == hh_status.GATE_EMPTY`.
- `NFCGate._read_hh_status_for_gate(self, target_gate, eventtime=None)` added, mirroring the existing `_read_hh_status()` but for an arbitrary gate — replaces `scan_jog.py`'s one direct `hh_status.gate_snapshot(gate._get_mmu(), target_gate)` call (used for the left-neighbor interference check).

`.action_label()` was already a natural fit as a method (called on a snapshot object already in hand at every site), so no separate accessor was needed for that one.

#### 🗑️ `scan_jog.py` drops the import

`from . import hh_status` removed. All three former touchpoints — `hh_status.action_label(hh.action)`, `hh.status == hh_status.GATE_EMPTY`, `hh_status.gate_snapshot(gate._get_mmu(), target_gate)` — now go through `hh.action_label()`, `hh.empty`, and `gate._read_hh_status_for_gate(target_gate)` respectively.

#### 🗑️ File deleted

`klippy/extras/nfc_gates/hh_status.py` removed via `git rm -f` (had uncommitted modifications from the earlier direct-reads rewrite this session, confirmed via `git diff` before forcing removal).

#### ✅ Verified

No remaining `hh_status` references anywhere in `klippy/` other than the intentionally-named `_read_hh_status()`/`_read_hh_status_for_gate()` methods and an explanatory code comment. `nfc_manager.py` and `scan_jog.py` both pass `py_compile`.

---

## 2026-07-12 — §2.3: delete `happy_hare_compat.py`

**Why:** no reason to keep checking for backports — this add-on targets Happy Hare V4 only. Both functions in this module existed purely to branch between a V3 code path and a V4 code path; with no V3 to support, there's no branch left, and a module holding only unconditional pass-through logic for a single caller isn't earning its place as a separate file. Per porting-plan §2.2, `mmu_nfc_endstop.py`'s V4 branch was already verified correct against real V4 source — this change just removes the detection layer sitting in front of it.

#### 🗑️ File deleted

`klippy/extras/nfc_gates/happy_hare_compat.py` removed via `git rm`. Confirmed it had exactly one caller (`mmu_nfc_endstop.py`) before deleting.

#### ♻️ `create_mmu_runout_helper()` inlined

The `try/except ImportError` probe (try `..mmu_sensors` first, fall back to `..mmu.mmu_sensor_utils`) is gone. `mmu_nfc_endstop.py` now imports `MmuRunoutHelper` directly (`from .mmu.mmu_sensor_utils import MmuRunoutHelper`) and constructs it inline in `__init__`, using the V4 kwargs only (no `switch_pin`).

#### ♻️ `register_nfc_endstop()` inlined

Moved directly into `_handle_connect()`. The `callable(getattr(mmu, 'drive', None))` duck-type check — the thing that decided "is this V3 or V4" — is gone; `mmu.drive(gate_number)` is called unconditionally now, since a V3 `mmu` object without `.drive()` was the only reason that check ever existed. The V3 `mmu.gear_rail` fallback branch is gone entirely, not just deprioritized.

#### ♻️ Error handling simplified

The old module raised `RuntimeError` and let `mmu_nfc_endstop.py` catch and rewrap it into `self.config.error(...)`. With everything in one place now, each failure point raises `self.config.error(...)` directly — one less layer of exception translation.

#### ✅ Verified

No remaining references to `happy_hare_compat`, `create_mmu_runout_helper`, or `register_nfc_endstop` anywhere in `klippy/` (grepped). `mmu_nfc_endstop.py` passes `py_compile`. `install.sh`/`uninstall.sh` have no hardcoded reference to the deleted file.

#### 💡 Left alone on purpose

The `mmu._nfc_endstops_by_gate` bookkeeping was deliberately not bundled into
this compatibility-module deletion. It was later moved off the foreign `mmu`
object and onto `NFCGate` in §2.2.1.

#### 💡 No version-number fallback added

Considered and rejected: gating on Happy Hare's version number (`mmu.version`/`mmu.mmu_machine.happy_hare_version`, already read elsewhere in `nfc_manager.py` for an unrelated purpose) instead of deleting the check outright. Not needed — there's nothing left to gate. If a genuinely incompatible Happy Hare version is ever installed, `mmu.drive()` will raise `AttributeError` naturally rather than silently falling back to dead V3 code.

---

## 2026-07-12 — §2.9: rename `LED_effect_mgr.py` → `NFC_LEDManager.py`

**Why:** the old file/class names (`LED_effect_mgr.py` / `LEDEffectManager`) collided conceptually with Happy Hare's own `MmuLedManager`, despite doing a genuinely different job — confirmed by reading `extras/mmu/mmu_led_manager.py` directly: HH's manager owns steady-state LED output and runs the actual effect patterns via a private `_set_led()` method with no public equivalent; this add-on's class only requests short-lived overrides via HH's public `MMU_SET_LED`/`_MMU_SET_LED_EFFECT` gcode commands and hands control back afterward. Not a duplicate to retire (unlike `hh_status.py`) — a legitimate client of HH's real API, just poorly named. Full reasoning in porting plan §2.9.

#### ♻️ File renamed via `git mv`

`klippy/extras/nfc_gates/LED_effect_mgr.py` → `klippy/extras/nfc_gates/NFC_LEDManager.py`.

#### ♻️ Class renamed

`LEDEffectManager` → `NFCLEDManager`. Header comment and class docstring updated to state explicitly that this is not a rival to `MmuLedManager`.

#### ♻️ Every reference updated

`tag_handler.py` (1 import, 1 instantiation), `nfc_manager.py` (1 import, 4 instantiations), `scan_jog.py` (1 import, 2 instantiations) — all switched from `from .LED_effect_mgr import (..., LEDEffectManager)` / `LEDEffectManager(...)` to the new names.

#### ✅ Verified

No remaining `LED_effect_mgr`/`LEDEffectManager` references anywhere in `klippy/` (grepped). All four touched files pass `py_compile`. `install.sh`/`uninstall.sh` don't enumerate individual files in `nfc_gates/`, so no installer change needed.

#### 💡 Left alone on purpose

`CHANGELOG.md`'s two historical entries (lines 547-548) still say `LED_effect_mgr.py` — not updated, since they're a record of what the file was called *at the time* of that change, not a live reference. Per earlier direction this session, `CHANGELOG.md` isn't touched for V4-port work regardless.

#### 💡 Explicitly deferred: everything else in §2.9

The dual v3/v4 detection in `is_happy_hare_v4()`, the `self.printer._nfc_v4_led_effects` foreign-attribute injection, and the hardcoded effect-naming-convention guess in `lane_effect_name()`/`shared_effect_name()` are all still open — this change was scoped to the rename only.

---

## 2026-07-12 — §2.4 (item 1 of 4): bind `mmu` once instead of per-read

**Why:** `hh_status.gate_snapshot()`/`full_snapshot()` (§2.5) each did their own `printer.lookup_object('mmu', None)` on every call — cheap individually, but wasteful given how often they're invoked from inside `nfc_manager.py`'s poll loop. §2.4 of the porting plan recommends binding the reference once, the same way every native V4 component resolves its dependencies once at `klippy:connect` rather than on every use. Scoped narrowly here to just the `hh_status.py` call path — deliberately **not** the other 16 `printer.lookup_object('mmu', None)` sites scattered through `scan_jog.py`'s free functions and elsewhere, which is a much larger, separate change.

#### ♻️ `NFCGate` caches `self.mmu`

`self.mmu = None` added to `NFCGate.__init__`; bound eagerly in the existing `_handle_connect()` handler (`self.mmu = self.printer.lookup_object('mmu', None)`, alongside the pre-existing `self._gcode` bind).

#### ✨ `_get_mmu()` accessor added

Returns the cached reference; falls back to a lazy lookup (and caches the result) only if the eager bind in `_handle_connect()` hadn't succeeded yet — guards against a config include-order edge case where `mmu` isn't loaded yet at `klippy:connect`, without permanently caching a `None`.

#### ♻️ `hh_status.py` signatures changed: `printer` → `mmu`

`gate_snapshot(printer, gate, eventtime)` → `gate_snapshot(mmu, gate, eventtime)`; `full_snapshot(printer, eventtime)` → `full_snapshot(mmu, eventtime)`. Neither function does its own `lookup_object()` call anymore — the caller is now required to hand in an already-resolved `mmu` reference.

#### ♻️ Call sites updated

3 sites, all passing the cached reference instead of `printer`: `nfc_manager.py:_read_hh_status()` → `hh_status.gate_snapshot(self._get_mmu(), ...)`, `nfc_manager.py:_all_lanes_parked_or_empty()` → `hh_status.full_snapshot(self._get_mmu(), ...)`, `scan_jog.py:spool_identity_for_gate()` → `hh_status.gate_snapshot(gate._get_mmu(), ...)` (works because `gate` there is an `NFCGate` instance too, just reading a different gate's index).

#### ✅ Verified

No naming collision with any prior `self.mmu` usage on `NFCGate` (confirmed via grep — the attribute didn't exist before this change). `hh_status.py`, `nfc_manager.py`, `scan_jog.py` all pass `py_compile`. No remaining `lookup_object('mmu'` calls inside `hh_status.py`.

#### 💡 Explicitly deferred: the other 16 lookup sites

`scan_jog.py` (13 sites), `nfc_manager.py` (2 more, outside the `hh_status.py` path), and `LED_effect_mgr.py` (1 site) still do their own per-call `printer.lookup_object('mmu', None)`. Left alone on purpose — folding those in would have meant threading a cached `mmu` reference through a much larger set of free functions, a materially bigger change than what was asked for this pass.

#### 💡 Explicitly deferred: items 2-4 of §2.4

The event-driven restructure (Mechanism A subscriptions for `mmu:gate_selected`/`mmu:printing`, Mechanism B's `_MMU_EVENT`/`gate_map_changed` macro bridge, and the resulting poll-loop simplification) is still fully open — this entry only covers item 1 (bind once).

---

## 2026-07-12 — §2.5: `hh_status.py` — direct reads replace the dict-parsing adapter

**Why:** `hh_status.py` existed to defend against Happy Hare being absent, being a different version, or exposing a differently-shaped `get_status()` dict — necessary when this add-on was an external plugin talking to a foreign object. Once this code is native to Happy Hare V4, `mmu` is a guaranteed live `MmuController` reference and those defenses are dead weight; internal V4 code already reads `mmu.gate_maps.gate_status`, `mmu.action`, etc. directly rather than through the external status API. See porting plan §2.5 for the verified V4 attribute inventory this change is built on.

#### ♻️ `hh_status.py` rewritten

`read()`/`read_full()` (which parsed `mmu.get_status(eventtime)`, a dict built for external template/webhook consumers) replaced with `gate_snapshot()`/`full_snapshot()`, which read `mmu.gate_maps.gate_status[gate]`, `mmu.gate_maps.gate_spool_id[gate]`, `mmu.action`, `mmu.filament_pos`, and `mmu.gate_selected` directly off the live controller object.

#### ♻️ Constants now imported, not hand-copied

`GATE_EMPTY`, `GATE_AVAILABLE`, `GATE_AVAILABLE_FROM_BUFFER`, `FILAMENT_POS_UNLOADED`, `ACTION_IDLE`, `ACTION_CHECKING` come from `extras/mmu/mmu_constants.py` (`from ..mmu.mmu_constants import ...`) instead of being locally redeclared. Removes the whole class of "does my hardcoded value match V4's real value" question the previous porting-plan pass had to spend a verification round confirming by hand.

#### ♻️ `GateSnapshot`/`FullSnapshot` kept as classes

Not fully inlined at each of the ~15 call sites across `nfc_manager.py`/`scan_jog.py` — `.assigned`/`.available`/`.idle`/`.label()` derived-property ergonomics were worth preserving given the number of call sites and the fact that `scan_jog.py` cannot import `nfc_manager.py` (circular — `nfc_manager` already imports `scan_jog`), so a shared module was still the least-duplication option. The distinction from before: these are now live-attribute snapshots, not parsed-dict snapshots.

#### 🗑️ Dead code removed

The module-level `all_lanes_parked_or_empty()` free function was never called (the real, in-use implementation is `NFCGate._all_lanes_parked_or_empty()` in `nfc_manager.py`, which duplicated the same logic independently). Removed rather than ported.

#### 🐛 `mmu.action` type mismatch

Direct reads expose `mmu.action` as its real int (`ACTION_IDLE = 0`, `ACTION_CHECKING = 7`, ...), not the display string (`'idle'`, `'checking'`) that `get_status()['action']` used to produce via `_get_action_string()`. `_happy_hare_allows_scan_action()` in `nfc_manager.py` compared against those string literals and would have silently always returned `False` under the new direct-read path (an int is never `== 'idle'`) — fixed to compare against `hh_status.ACTION_IDLE`/`ACTION_CHECKING` instead. Caught during this change, not inherited from a prior bug.

#### 🐛 Log/console readability preserved

Three messages that interpolated `hh.action`/`status.action` directly into `%s` format strings (`nfc_manager.py:2004`, `nfc_manager.py:2286`, `scan_jog.py:144`, plus the `_all_lanes_parked_or_empty` preflight-failure message) would otherwise have started printing raw ints (`action=0`) instead of words. Added `hh_status.action_label()` (a small local map mirroring `MmuController._get_action_string()`'s wording for the two values this add-on actually branches on — `Idle`, `Checking` — falling back to the raw int for anything else) and wrapped all four sites.

#### ♻️ Renamed: `hh_status.read()` → `hh_status.gate_snapshot()`

`hh_status.read(printer, gate, eventtime)` → `hh_status.gate_snapshot(printer, gate, eventtime)` — 2 call sites (`nfc_manager.py:_read_hh_status`, `scan_jog.py:spool_identity_for_gate`).

#### ♻️ Renamed: `hh_status.read_full()` → `hh_status.full_snapshot()`

`hh_status.read_full(printer, eventtime)` → `hh_status.full_snapshot(printer, eventtime)` — 1 call site (`nfc_manager.py:_all_lanes_parked_or_empty`).

#### ♻️ Renamed: `hh_status.GATE_INBUFFER` → `hh_status.GATE_AVAILABLE_FROM_BUFFER`

1 call site (`nfc_manager.py:_all_lanes_parked_or_empty`), now matching V4's real constant name (same value, `2`, as before — this repo had it under a locally-invented name).

#### ✅ No stale references remain

Confirmed no remaining references to the removed names (`hh_status.read(`, `hh_status.read_full(`, `hh_status.GATE_INBUFFER`, `HHGateStatus`, `HHFullStatus`) anywhere in `klippy/extras/nfc_gates/`, and no remaining string-literal action comparisons (`== 'idle'`, `== 'checking'`).

#### ✅ Compiles clean

`hh_status.py`, `nfc_manager.py`, `scan_jog.py` all pass `py_compile`/`ast.parse`.

#### 💡 Not yet verified at runtime

This pass is source-level correctness only (matching the porting plan's own verified-against-source standard from the previous round) — behavior against a running V4 Klipper instance is still open, tracked in the porting plan's §4 checklist.

#### 💡 Explicitly deferred: version-gating cleanup

`_happy_hare_major_version()`/the V3-major-version gating still inside `_happy_hare_allows_scan_action()` was left untouched — only its value comparisons were fixed (string → int). Fully removing the version-detection branch is porting-plan §2.6 scope, not this change; flagged but not actioned.
