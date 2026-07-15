# test/hh_compat/test_shared_reader_compat.py
#
# Dynamic compatibility tests: actually import SharedNFCReader (and its
# full dependency chain -- NFCGate, GateState, tag_handler, spoolman_client,
# KlipperInterface, NFC_LEDManager) with `..mmu.mmu_constants` resolved
# against the REAL local Happy Hare checkout, then construct and exercise
# it against a spec'd fake `mmu` (see fakes.py) built from real, verified
# attribute names -- not a bare MagicMock that would silently swallow a
# typo'd or renamed attribute.
#
# The hardware reader driver (I2C/SPI construction via Klipper's bus.py)
# is patched out -- out of scope here, it doesn't touch Happy Hare's API
# at all and is exercised by this repo's own driver-level code instead.

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bootstrap import HH_EXTRAS, HappyHareNotFound, happy_hare_info, import_hh, import_nfc_gates
from fakes import FakeConfig, FakePrinter, build_fake_mmu


@unittest.skipUnless(os.path.isdir(HH_EXTRAS), "no local Happy Hare checkout")
class SharedNFCReaderCompatTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            happy_hare_info()
        except HappyHareNotFound as e:
            raise unittest.SkipTest(str(e))
        cls.mc = import_hh("mmu.mmu_constants")
        cls.shared_reader_mod = import_nfc_gates("shared_reader")
        cls.nfc_manager_mod = import_nfc_gates("nfc_manager")
        cls.scan_jog_mod = import_nfc_gates("scan_jog")

    def setUp(self):
        self._reader_patch = patch(
            "klippy.extras.nfc_gates.reader_factory.create_reader",
            return_value=MagicMock(name="reader"))
        self._reader_patch.start()
        self.addCleanup(self._reader_patch.stop)
        # Each NFCGate instance registers a mux/plain command on construction
        # via _handle_connect(), but that's wired to klippy:connect, which we
        # never fire here -- construction alone must not require it.
        self.printer = FakePrinter()

    def _make_shared_config(self, **overrides):
        values = {"shared": True}
        values.update(overrides)
        return FakeConfig("nfc_gate shared", self.printer, values)

    def _make_lane_config(self, name, mmu_gate, **overrides):
        values = {"mmu_gate": mmu_gate}
        values.update(overrides)
        return FakeConfig("nfc_gate %s" % name, self.printer, values)

    def test_shared_reader_imports_and_constructs(self):
        SharedNFCReader = self.shared_reader_mod.SharedNFCReader
        config = self._make_shared_config()
        gate = SharedNFCReader(config, defaults=None)
        self.assertTrue(gate._shared)
        self.assertIsInstance(gate, self.nfc_manager_mod.NFCGate)

    def test_get_status_shape_matches_shared_fields(self):
        SharedNFCReader = self.shared_reader_mod.SharedNFCReader
        gate = SharedNFCReader(self._make_shared_config(), defaults=None)
        status = gate.get_status()
        for key in ("pending_spool_id", "pending_auto_created",
                    "preload_spool_id", "preload_auto_created",
                    "has_per_lane_readers"):
            self.assertIn(key, status)
        # Nothing staged yet -- defaults, not garbage from an unmocked read.
        self.assertEqual(status["pending_spool_id"], -1)
        self.assertEqual(status["preload_spool_id"], -1)

    def test_lane_get_status_has_no_shared_leak(self):
        """A plain NFCGate's get_status() must not expose real shared state
        even if somehow set -- confirms the base/override split in
        get_status() didn't regress into always returning True/real values."""
        NFCGate = self.nfc_manager_mod.NFCGate
        gate = NFCGate(self._make_lane_config("lane0", 0), defaults=None)
        gate._shared_pending_spool = 42  # would only matter if leaked
        status = gate.get_status()
        self.assertEqual(status["has_per_lane_readers"], False)
        self.assertEqual(status["pending_spool_id"], -1)

    def test_bypass_selected_reads_real_tool_gate_bypass_constant(self):
        SharedNFCReader = self.shared_reader_mod.SharedNFCReader
        gate = SharedNFCReader(self._make_shared_config(), defaults=None)
        mmu = build_fake_mmu(self.mc)
        gate.mmu = mmu

        mmu.tool_selected = self.mc.TOOL_GATE_BYPASS
        self.assertTrue(gate._shared_bypass_selected())

        mmu.tool_selected = 0
        self.assertFalse(gate._shared_bypass_selected())

    def test_has_per_lane_readers_populated_on_connect(self):
        """Exercises the 2026-07-14 fix directly against real constants:
        a SharedNFCReader among enabled lane NFCGates must see
        has_per_lane_readers=True after _handle_connect()."""
        NFCGate = self.nfc_manager_mod.NFCGate
        SharedNFCReader = self.shared_reader_mod.SharedNFCReader
        nfc_manager = self.nfc_manager_mod

        lane = NFCGate(self._make_lane_config("lane0", 0), defaults=None)
        shared = SharedNFCReader(self._make_shared_config(), defaults=None)
        self.printer.add_object("mmu", build_fake_mmu(self.mc))

        nfc_manager._lane_instances[:] = [lane, shared]
        try:
            shared._handle_connect()
        finally:
            nfc_manager._lane_instances[:] = []

        self.assertTrue(shared._has_per_lane_readers)

    def test_has_per_lane_readers_false_when_shared_only(self):
        NFCGate = self.nfc_manager_mod.NFCGate
        SharedNFCReader = self.shared_reader_mod.SharedNFCReader
        nfc_manager = self.nfc_manager_mod

        shared = SharedNFCReader(self._make_shared_config(), defaults=None)
        self.printer.add_object("mmu", build_fake_mmu(self.mc))

        nfc_manager._lane_instances[:] = [shared]
        try:
            shared._handle_connect()
        finally:
            nfc_manager._lane_instances[:] = []

        self.assertFalse(shared._has_per_lane_readers)

    def test_scan_jog_get_speed_reads_real_gear_short_move_speed_path(self):
        """scan_jog.get_speed() walks mmu.drive(gate).mmu_unit.p.<param> --
        the exact chain verified statically in test_mmu_api_surface.py.
        This confirms it also actually works end to end against the fake
        built from that same verified shape."""
        scan_jog = self.scan_jog_mod

        class FakeGate:
            _gate = 0
            printer = None

        mmu = build_fake_mmu(self.mc)
        printer = FakePrinter(objects={"mmu": mmu})
        fake_gate = FakeGate()
        fake_gate.printer = printer

        speed = scan_jog.get_speed(fake_gate)
        self.assertEqual(speed, 80.0)

    def test_scan_jog_mmu_gear_position_reads_real_get_position_shape(self):
        """mmu_gear_position() does mmu.drive(gate).mmu_gear_stepper
        .get_position()[0] -- confirms the [0]-indexing assumption holds
        against the real MmuStepper.get_position() return shape."""
        scan_jog = self.scan_jog_mod

        class FakeGate:
            _gate = 0
            printer = None

        mmu = build_fake_mmu(self.mc, gear_position=123.5)
        printer = FakePrinter(objects={"mmu": mmu})
        fake_gate = FakeGate()
        fake_gate.printer = printer

        pos = scan_jog.mmu_gear_position(fake_gate)
        self.assertEqual(pos, 123.5)

    def test_reader_type_present_in_reported_status(self):
        # Smoke test that construction all the way through get_status()
        # doesn't throw for a lane gate either -- catches accidental
        # coupling introduced by the extraction (e.g. a leftover
        # self._shared_* read on the base class get_status()).
        NFCGate = self.nfc_manager_mod.NFCGate
        gate = NFCGate(self._make_lane_config("lane1", 1), defaults=None)
        status = gate.get_status()
        self.assertEqual(status["gate"], 1)
        self.assertIn("reader_type", status)


if __name__ == "__main__":
    unittest.main()
