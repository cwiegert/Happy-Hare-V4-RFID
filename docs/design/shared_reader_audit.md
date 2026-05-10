# Shared Reader Implementation Audit

> Working memory for auditing the shared reader implementation against
> `docs/design/shared_reader.md`.
>
> Green means the current tree has an implementation matching the baseline.
> Red means the item is missing, incomplete, or still requires validation.

| Implemented | Baseline requirement | Files affected |
|:---:|---|---|
| ✅ | Shared reader is configured as `[nfc_gate shared]` with `shared: true`. | `klippy/extras/nfc_gates/nfc_manager.py`, `install.sh`, `docs/shared/configuration.md` |
| ✅ | Shared reader does not require or accept a user-facing `mmu_gate`; code uses internal sentinel gate `255`. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | Only one shared reader may be configured. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `scan_enabled` is forced off for the shared reader; shared must not enter scan-jog. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | Shared reader does not register `NFC GATE=` mux commands; all user control goes through `NFC_SHARED`. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `NFC_SHARED` supports `READ`, `STATUS`, `CLEAR`, `PRELOAD_CHECK`, `POLL`, `SCAN`, `INIT`, and `CLEAR_CACHE`. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` |
| ✅ | Shared state tracks pending UID, pending spool ID, pending deadline, auto-created flag, last error, and read deadline. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | Successful tag resolution stores a pending spool, starts `shared_pending_timeout`, stops polling, and keeps the pending spool after tag removal. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | UID-only / unresolved tag records an error without clearing a previously pending spool. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `shared_pending_timeout` defaults to `120.0` seconds and expires stale pending spools before preload staging. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` |
| ✅ | `shared_read_timeout` defaults to `120.0` seconds and stops manual/eject-triggered polling when no valid tag resolves. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` |
| ✅ | `startup_polling: 1` starts polling after PN532 init without applying the manual read timeout. | `klippy/extras/nfc_gates/nfc_manager.py`, `install.sh` |
| ✅ | Shared polling skips I2C reads while printing. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | Shared polling skips I2C reads while Happy Hare reports active load, unload, or homing. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `PRELOAD_CHECK` uses the existing safety posture: check printing / HH busy state, but do not read NFC during preload check. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `PRELOAD_CHECK` stages the pending spool with `MMU_GATE_MAP NEXT_SPOOLID=<id>` and never blocks normal loading when no spool is pending. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | After successful `PRELOAD_CHECK`, shared polling restarts for the next spool with no read deadline. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | `READ=0` stops polling but keeps any pending spool; `CLEAR=1` stops polling and clears pending/shared state. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` |
| ✅ | `CLEAR_CACHE=1` clears the `GateState` tag cache without clearing pending shared spool state. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` |
| ✅ | Successful tag read can trigger a named HH LED effect via `shared_tag_read_effect`; design example is blinking yellow `mmu_RFID_read`. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` |
| ✅ | `NFC_SHARED STATUS=1` reports idle, polling, pending, expired, error, and reader-failed shared states. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` |
| ✅ | `NFC_STATUS` includes the shared reader after numbered lane readers. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` |
| ✅ | Shared reader ready/init messages use `NFC_SHARED` commands and do not include lane HH seed notes. | `klippy/extras/nfc_gates/nfc_manager.py` |
| ✅ | Happy Hare pre-load hook bridge exists as `_NFC_SHARED_PRELOAD` and calls `NFC_SHARED PRELOAD_CHECK=1`. | `config/nfc_macros.cfg`, `install.sh`, `docs/shared/configuration.md` |
| ✅ | Happy Hare post-unload hook bridge exists as `_NFC_SHARED_POST_UNLOAD` and calls `NFC_SHARED READ=1`. | `config/nfc_macros.cfg`, `install.sh`, `docs/shared/configuration.md` |
| ✅ | Installer supports an upfront lane/shared branch, defaults lane, and writes a shared-only hardware config when selected. | `install.sh` |
| ✅ | Installer detects existing `[nfc_gate shared]` config and existing shared MCU for reinstall defaults. | `install.sh` |
| ✅ | Installer next steps call out shared MCU flash and HH hook wiring. | `install.sh` |
| ✅ | Normal PN532 driver waits use injectable `sleep_fn`, and `NFCGate` supplies a reactor-cooperative sleep using `reactor.pause`. | `klippy/extras/nfc_gates/pn532_driver.py`, `klippy/extras/nfc_gates/nfc_manager.py` |
| ❌ | Installer generated shared config should expose every important shared timeout/effect knob clearly; current output comments `shared_tag_read_effect` and `shared_pending_timeout`, but not `shared_read_timeout`. | `install.sh` |
| ❌ | Shared reader behavior should have direct tests for config parsing, command handling, timeout behavior, pending spool staging, status output, and no-op preload behavior. Current tests only set `_shared = False` in scan-jog fixtures. | `tests/` |
| ❌ | PN532 low-level debug helpers still contain direct `time.sleep()` calls; either convert them to `sleep_fn` or document them as an explicit debug-only exception. | `klippy/extras/nfc_gates/pn532_driver.py` |
| ❌ | Lane-only wiring / architecture docs need a shared-reader exception so they do not imply shared installs are unsupported. | `docs/i2c-pn532/wiring.md`, `docs/shared/architecture-decisions.md` |
| ❌ | HH post-unload timing needs hardware validation to confirm shared polling starts after the gate is empty. | Happy Hare runtime, printer hardware |
| ❌ | HH LED effect invocation needs hardware validation for `MMU_SET_LED EXIT_EFFECT=<shared_tag_read_effect> DURATION=3`. | Happy Hare runtime, LED config |
| ❌ | Auto-created Spoolman spool IDs still need hardware / HH validation to confirm `MMU_GATE_MAP NEXT_SPOOLID=<id>` works without an explicit `MMU_SPOOLMAN REFRESH=1`. | `klippy/extras/nfc_gates/nfc_manager.py`, Happy Hare runtime |

## Audit Notes

- The active terminology is **shared** throughout this feature.
- The design says shared-only installs do not need `[nfc_gate laneN]` sections.
  The installer path matches that by writing only `[nfc_gate shared]` hardware.
- The biggest implementation risk is not the core path; it is validation. The
  shared path needs unit tests and one real Happy Hare integration pass for
  `NEXT_SPOOLID`, post-unload timing, LED effect invocation, and auto-created
  Spoolman IDs.
