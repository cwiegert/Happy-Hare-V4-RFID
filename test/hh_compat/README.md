# Happy Hare compatibility harness

Answers one question: **does the shared-reader code in `klippy/extras/nfc_gates/`
actually work against a real, local Happy Hare checkout** — not against our
own assumptions about its API, restated as docs.

## Running

```sh
./run_tests.sh
# or, from anywhere:
HAPPY_HARE_PATH=/path/to/Happy-Hare python3 -m unittest discover -s test/hh_compat -p "test_*.py" -v
```

Defaults to `~/Documents/GitHub/Happy-Hare`. If no checkout is found there,
every test in this directory **skips** (not fails) — safe to leave in a
general test run on a machine without Happy Hare cloned.

`test_reports_which_checkout_and_branch` always prints which path and git
branch were actually checked, since "works with the rfid branch" is
meaningless without knowing whether a given run actually used it.

## What's here

- **`bootstrap.py`** — the load-bearing piece. Makes this repo's
  `klippy.extras.nfc_gates` package and the real Happy Hare checkout's
  `klippy.extras.mmu` package resolve as siblings under one synthetic
  `klippy.extras` namespace, so `from ..mmu.mmu_constants import ...` inside
  our code resolves against the *real* file. No copying, no symlinks — pure
  `sys.modules`/`__path__` construction, reverted by nothing because nothing
  on disk changes. Works because `extras/mmu` has no `__init__.py` (a Python
  namespace package) and `mmu_constants.py` has zero imports of its own, so
  neither pulls in the rest of the Klipper-core-dependent MMU stack we don't
  have checked out here.

- **`fakes.py`** — `FakeConfig`/`FakePrinter`/`FakeReactor` with real value
  semantics (not bare `MagicMock`s — our code branches on config values, so
  a truthy mock in the wrong place would silently take the wrong path
  instead of failing loudly). `build_fake_mmu()` builds a
  `MagicMock(spec=[...])` `mmu` object from an attribute list verified
  against the real source — not a bare `MagicMock()`, which would let any
  nonexistent attribute silently succeed and return another mock, hiding
  exactly the kind of drift this harness exists to catch.

- **`test_mmu_api_surface.py`** — static, source-level checks (via `ast`,
  not import) that every `mmu.*` / `mmu_constants.*` touchpoint our code
  depends on actually exists in the real checkout, with a compatible
  signature/shape. Runs without needing full Klipper core, so it works even
  when the dynamic tests below can't fully construct something.

- **`test_shared_reader_compat.py`** — dynamic tests: actually import
  `SharedNFCReader` (and its full dependency chain) against the real
  `mmu_constants`, construct it with `FakeConfig`/`FakePrinter`, and
  exercise real code paths (`get_status()` shape, `_shared_bypass_selected()`
  against the real `TOOL_GATE_BYPASS` value, the `_has_per_lane_readers`
  fix, `scan_jog.get_speed()`'s `mmu.drive(gate).mmu_unit.p...` chain, etc.)
  against the spec'd fake `mmu`. The hardware reader driver (I2C/SPI via
  Klipper's `bus.py`) is patched out — genuine hardware plumbing, orthogonal
  to Happy Hare API compatibility, exercised by this repo's own
  driver-level code instead.

## What this caught

First run found a real bug, not a Happy-Hare-compatibility gap: the
2026-07-14 `SharedNFCReader` extraction moved `_shared_led_failsafe_event`
off the base `NFCGate` class, but `NFCGate.__init__` still registered it as
a timer callback **unconditionally** —
`self.reactor.register_timer(self._shared_led_failsafe_event)` with no
`if self._shared:` guard. Every plain per-lane `NFCGate` construction
crashed with `AttributeError` at `__init__`. Every other moved-method
reference left in `nfc_manager.py` was checked and is properly guarded;
this was the one that wasn't. Fixed in `nfc_manager.py`'s `__init__`.

## What this does not cover

- Real hardware I/O (I2C/SPI reader chips) — patched out on purpose, tested
  elsewhere.
- `_poll_timer_event()`/`_poll()` themselves — deliberately left
  unrefactored on `NFCGate` per the current extraction scope; these tests
  exercise call paths *through* them only incidentally, not their full
  branching logic.
- Anything requiring a full Klipper core checkout (kinematics, `mcu.py`,
  `toolhead.py`, `reactor.py`'s real implementation) — out of reach without
  one on this machine; `FakeReactor` stands in.
