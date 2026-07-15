# test/hh_compat/test_mmu_api_surface.py
#
# Static, source-level verification that every Happy Hare V4 API surface
# point this repo's nfc_gates code depends on actually exists in the real,
# local Happy Hare checkout -- not just that our own code is internally
# consistent. Uses `ast` against the real source files rather than
# importing them, since importing mmu_controller.py transitively needs
# full Klipper core (kinematics, mcu, toolhead, ...) that isn't checked
# out here. This also means these tests still run (and mean something)
# even without a full Klipper install alongside Happy Hare.
#
# Every touchpoint here was enumerated by grepping klippy/extras/nfc_gates/
# for every `mmu.<x>` / `mmu_constants.<X>` reference -- see the
# HH-2026-07-14 shared-reader-extraction pass in
# docs/shared/v4-implementation-log.md for how this list was built.

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bootstrap import HAPPY_HARE_PATH, HH_EXTRAS, HappyHareNotFound, happy_hare_info


def _parse(path):
    with open(path) as f:
        return ast.parse(f.read(), filename=path)


def _class_method_names(tree, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    return None


def _module_level_assigned_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def _instance_attrs_assigned_in_init(tree, class_name):
    """Names assigned via self.<name> = ... anywhere in a class's methods.

    Broader than just __init__ on purpose -- e.g. gate_selected/action get
    reassigned in cmd handlers too, and we only care whether the attribute
    exists at all, not which method sets it first.
    """
    attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    for t in inner.targets:
                        if (isinstance(t, ast.Attribute)
                                and isinstance(t.value, ast.Name)
                                and t.value.id == "self"):
                            attrs.add(t.attr)
            return attrs
    return attrs


@unittest.skipUnless(os.path.isdir(HH_EXTRAS), "no local Happy Hare checkout")
class MmuApiSurfaceTest(unittest.TestCase):
    """One assertion per real API touchpoint klippy/extras/nfc_gates/ relies on."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.hh_path, cls.hh_branch, cls.hh_dirty = happy_hare_info()
        except HappyHareNotFound as e:
            raise unittest.SkipTest(str(e))
        cls.constants_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "mmu_constants.py"))
        cls.controller_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "mmu_controller.py"))
        cls.filament_movement_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "mmu_filament_movement.py"))
        cls.gate_maps_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "mmu_gate_maps.py"))
        cls.mmu_drive_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "unit", "mmu_drive.py"))
        cls.mmu_unit_tree = _parse(
            os.path.join(HH_EXTRAS, "mmu", "mmu_unit.py"))
        stepper_path = os.path.join(
            os.path.dirname(HH_EXTRAS), "extras", "mmu_stepper.py")
        # mmu_stepper.py lives at extras/mmu_stepper.py, a sibling of the
        # mmu/ package, not inside it.
        stepper_path = os.path.join(HH_EXTRAS, "mmu_stepper.py")
        cls.stepper_tree = _parse(stepper_path)

    def test_reports_which_checkout_and_branch(self):
        # Not a pass/fail assertion -- printed so a CI log or local run
        # always states exactly what was checked against, since "works
        # with the rfid branch" is meaningless without knowing whether
        # this run actually used it.
        print("\n[hh_compat] Happy Hare checkout: %s" % self.hh_path)
        print("[hh_compat] branch: %s%s" % (
            self.hh_branch, " (dirty)" if self.hh_dirty else ""))
        if self.hh_branch != "rfid":
            print("[hh_compat] WARNING: not on the rfid branch -- "
                  "results below may not reflect it")

    def test_mmu_constants_present(self):
        names = _module_level_assigned_names(self.constants_tree)
        required = {
            "GATE_EMPTY", "GATE_AVAILABLE", "GATE_AVAILABLE_FROM_BUFFER",
            "FILAMENT_POS_UNLOADED", "ACTION_IDLE", "ACTION_CHECKING",
            "TOOL_GATE_BYPASS",
        }
        missing = required - names
        self.assertFalse(
            missing, "mmu_constants.py is missing: %s" % sorted(missing))

    def test_mmu_controller_instance_attrs_present(self):
        attrs = _instance_attrs_assigned_in_init(
            self.controller_tree, "MmuController")
        required = {
            "action", "num_gates", "tool_selected", "gate_selected",
            "filament_pos", "gate_maps",
        }
        missing = required - attrs
        self.assertFalse(
            missing,
            "MmuController never assigns self.<attr> for: %s" % sorted(missing))

    def test_mmu_controller_methods_present(self):
        methods = _class_method_names(self.controller_tree, "MmuController")
        for name in ("drive", "select_gate", "initialize_filament_position",
                     "wrap_suppress_visual_log"):
            self.assertIn(
                name, methods,
                "MmuController.%s() not found (checked %s @ %s)"
                % (name, self.hh_branch, self.hh_path))

    def test_move_filament_signature(self):
        tree = self.filament_movement_tree
        found = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "move_filament":
                found = node
                break
        self.assertIsNotNone(found, "move_filament() not found")
        arg_names = {a.arg for a in found.args.args} | {
            a.arg for a in found.args.kwonlyargs}
        required_kwargs = {
            "trace_str", "dist", "speed", "accel", "motor", "homing_move",
            "endstop_name", "wait",
        }
        missing = required_kwargs - arg_names
        self.assertFalse(
            missing,
            "move_filament() signature is missing params our code passes: "
            "%s (found params: %s)" % (sorted(missing), sorted(arg_names)))

    def test_wrap_sync_gear_to_extruder_present(self):
        methods = _class_method_names(
            self.filament_movement_tree, "MmuFilamentMovement")
        self.assertIn(
            "wrap_sync_gear_to_extruder", methods or set(),
            "MmuFilamentMovement.wrap_sync_gear_to_extruder() not found")

    def test_gate_maps_attrs_present(self):
        attrs = _instance_attrs_assigned_in_init(
            self.gate_maps_tree, "MmuGateMaps")
        for name in ("gate_status", "gate_spool_id"):
            self.assertIn(
                name, attrs,
                "MmuGateMaps never assigns self.%s" % name)

    def test_mmu_drive_attrs_present(self):
        attrs = _instance_attrs_assigned_in_init(self.mmu_drive_tree, "MmuDrive")
        for name in ("mmu_unit", "mmu_gear_stepper"):
            self.assertIn(
                name, attrs, "MmuDrive never assigns self.%s" % name)

    def test_mmu_unit_has_params_accessor(self):
        attrs = _instance_attrs_assigned_in_init(self.mmu_unit_tree, "MmuUnit")
        self.assertIn(
            "p", attrs,
            "MmuUnit never assigns self.p (mmu.drive(gate).mmu_unit.p... "
            "would fail)")

    def test_gear_short_move_speed_param_exists(self):
        # ParamSpec('gear_short_move_speed', ...) -- a call, not a plain
        # assignment, so check for the string literal as the first arg
        # of any ParamSpec(...) call in the unit-parameters source.
        path = os.path.join(HH_EXTRAS, "mmu", "unit", "mmu_unit_parameters.py")
        tree = _parse(path)
        found = False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "ParamSpec"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "gear_short_move_speed"):
                found = True
                break
        self.assertTrue(
            found, "gear_short_move_speed ParamSpec not found in %s" % path)

    def test_gear_stepper_get_position_shape(self):
        tree = self.stepper_tree
        found = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MmuStepper":
                for inner in node.body:
                    if isinstance(inner, ast.FunctionDef) and inner.name == "get_position":
                        found = inner
                break
        self.assertIsNotNone(found, "MmuStepper.get_position() not found")
        # scan_jog.py does pos[0] -- confirm the return is list/tuple-shaped
        # with the position first, not e.g. a dict or scalar.
        returns = [n for n in ast.walk(found) if isinstance(n, ast.Return)]
        self.assertTrue(returns, "get_position() has no return statement")
        self.assertIsInstance(
            returns[0].value, (ast.List, ast.Tuple),
            "get_position() does not return a list/tuple -- scan_jog.py's "
            "pos[0] indexing assumption would be wrong")


if __name__ == "__main__":
    unittest.main()
