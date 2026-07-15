# test/hh_compat/bootstrap.py
#
# Makes `from ..mmu.mmu_constants import ...` (and any other
# `klippy.extras.mmu.*` import) inside this repo's klippy/extras/nfc_gates
# package resolve against a REAL, local Happy Hare checkout instead of a
# hand-written stand-in -- so a compatibility test actually proves
# something about the real rfid branch, not about our own assumptions.
#
# How: Python packages support multiple search directories via __path__.
# We build synthetic `klippy` / `klippy.extras` package objects whose
# __path__ lists BOTH this repo's klippy/extras (for `nfc_gates`) AND the
# real Happy Hare checkout's extras/ (for `mmu`). No files are copied,
# symlinked, or written into either repo.
#
# Happy Hare's `extras/mmu` has no __init__.py -- it's a namespace package
# -- so importing klippy.extras.mmu.mmu_constants does not transitively
# import mmu_controller.py and the rest of the Klipper-core-dependent
# stack. That's what makes this possible without a full Klipper checkout.

import logging
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUR_EXTRAS = os.path.join(REPO_ROOT, "klippy", "extras")

HAPPY_HARE_PATH = os.environ.get(
    "HAPPY_HARE_PATH", os.path.expanduser("~/Documents/GitHub/Happy-Hare"))
HH_EXTRAS = os.path.join(HAPPY_HARE_PATH, "extras")

_bootstrapped = False


class HappyHareNotFound(RuntimeError):
    pass


def happy_hare_info():
    """Return (path, branch, is_clean) for the local Happy Hare checkout.

    Shells out to git rather than assuming -- the whole point of this
    harness is to check the real, current state, not a remembered one.
    """
    import subprocess
    if not os.path.isdir(HH_EXTRAS):
        raise HappyHareNotFound(
            "No Happy Hare checkout found at %r (extras/mmu missing). "
            "Set HAPPY_HARE_PATH to override." % HAPPY_HARE_PATH)
    try:
        branch = subprocess.check_output(
            ["git", "-C", HAPPY_HARE_PATH, "branch", "--show-current"],
            text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "-C", HAPPY_HARE_PATH, "status", "--porcelain"],
            text=True).strip())
    except Exception as e:
        branch, dirty = "<unknown: %s>" % e, None
    return HAPPY_HARE_PATH, branch, dirty


def _configure_scratch_logger():
    """Give the root logger a FileHandler before nfc_gates/log.py imports.

    nfc_gates/log.py's _find_klipper_log_dir() looks for a FileHandler on
    the root logger (what real Klipper always has by the time it loads
    extras) and falls back to ~/printer_data/logs if none exists. Without
    this, importing nfc_gates modules in a bare test process fails with
    FileNotFoundError against a path this harness has no business creating
    on a real machine. One FileHandler, added once, is enough to satisfy
    the lookup -- it's never written to.
    """
    root = logging.getLogger()
    if any(isinstance(h, logging.FileHandler) for h in root.handlers):
        return
    import tempfile
    scratch_dir = tempfile.mkdtemp(prefix="hh_compat_logs_")
    handler = logging.FileHandler(os.path.join(scratch_dir, "klippy.log"))
    root.addHandler(handler)


def _stub_klipper_core_bus():
    """reader_factory.py imports real Klipper core's klippy/bus.py at module
    load time (`from .. import bus`), for MCU_I2C_from_config/
    MCU_SPI_from_config -- genuine hardware plumbing, out of scope for this
    harness (it's patched out via reader_factory.create_reader in tests
    that need to construct a gate). Only needs to exist as an importable
    module with plausible names; its functions are never actually called
    once create_reader is patched.
    """
    if "klippy.extras.bus" in sys.modules:
        return
    bus_stub = types.ModuleType("klippy.extras.bus")
    bus_stub.MCU_I2C_from_config = lambda *a, **k: None
    bus_stub.MCU_SPI_from_config = lambda *a, **k: None
    sys.modules["klippy.extras.bus"] = bus_stub


def bootstrap():
    """Set up the merged klippy.extras namespace. Safe to call repeatedly."""
    global _bootstrapped
    if _bootstrapped:
        return
    if not os.path.isdir(HH_EXTRAS):
        raise HappyHareNotFound(
            "No Happy Hare checkout found at %r (extras/mmu missing). "
            "Set HAPPY_HARE_PATH to override." % HAPPY_HARE_PATH)
    if not os.path.isfile(os.path.join(HH_EXTRAS, "mmu", "mmu_constants.py")):
        raise HappyHareNotFound(
            "%r does not look like a Happy Hare V4 checkout "
            "(extras/mmu/mmu_constants.py missing)" % HAPPY_HARE_PATH)

    _configure_scratch_logger()

    klippy_pkg = sys.modules.get("klippy")
    if klippy_pkg is None:
        klippy_pkg = types.ModuleType("klippy")
        klippy_pkg.__path__ = []
        sys.modules["klippy"] = klippy_pkg

    extras_pkg = types.ModuleType("klippy.extras")
    extras_pkg.__path__ = [OUR_EXTRAS, HH_EXTRAS]
    sys.modules["klippy.extras"] = extras_pkg
    klippy_pkg.extras = extras_pkg

    _stub_klipper_core_bus()

    _bootstrapped = True


def import_nfc_gates(name):
    """Import klippy.extras.nfc_gates.<name>, bootstrapping first."""
    bootstrap()
    import importlib
    return importlib.import_module("klippy.extras.nfc_gates.%s" % name)


def import_hh(dotted):
    """Import klippy.extras.<dotted> from the real Happy Hare checkout."""
    bootstrap()
    import importlib
    return importlib.import_module("klippy.extras.%s" % dotted)
