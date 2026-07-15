# test/hh_compat/fakes.py
#
# Minimal fakes for the pieces of the Klipper/Happy Hare runtime our code
# touches at construction and in the flows under test. FakeConfig has real
# value semantics (typed defaults, not MagicMock objects) because our code
# branches on config values (`if self._shared:`) -- a MagicMock truthy
# value there would silently take the wrong branch instead of failing loudly.
#
# The mmu object is a spec'd MagicMock(spec=[...]) built from an attribute
# list verified against the real Happy Hare source (see
# test_mmu_api_surface.py) -- not a bare MagicMock(). A bare MagicMock lets
# any nonexistent attribute silently succeed and return another MagicMock,
# which would hide exactly the kind of drift this harness exists to catch.

from unittest.mock import MagicMock

_NO_DEFAULT = object()


class FakeReactor:
    NEVER = float("inf")
    NOW = 0.0

    def __init__(self):
        self._now = 1000.0
        self.timers = []

    def monotonic(self):
        return self._now

    def register_timer(self, callback, waketime=None):
        timer = MagicMock(name="timer")
        self.timers.append((timer, callback))
        return timer

    def update_timer(self, timer, waketime):
        pass

    def register_callback(self, callback):
        pass

    def register_async_callback(self, callback):
        pass

    def pause(self, waketime):
        pass


class FakeGcode:
    def __init__(self):
        self.registered_commands = {}
        self.registered_mux_commands = {}
        self.responses = []

    def register_command(self, name, func, desc=None):
        self.registered_commands[name] = func

    def register_mux_command(self, cmd, key, value, func, desc=None):
        self.registered_mux_commands[(cmd, key, value)] = func

    def respond_info(self, msg):
        self.responses.append(msg)

    def run_script(self, script):
        self.responses.append(("run_script", script))


class FakePrinter:
    def __init__(self, objects=None):
        self.reactor = FakeReactor()
        self.gcode = FakeGcode()
        self._objects = dict(objects or {})
        self._objects.setdefault("gcode", self.gcode)
        self._event_handlers = {}

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=_NO_DEFAULT):
        if name in self._objects:
            return self._objects[name]
        if default is not _NO_DEFAULT:
            return default
        raise Exception("unknown object %r" % name)

    def lookup_objects(self, name):
        return [(k, v) for k, v in self._objects.items()
                if k == name or k.startswith(name + " ")]

    def register_event_handler(self, event, callback):
        self._event_handlers.setdefault(event, []).append(callback)

    def add_object(self, name, obj):
        self._objects[name] = obj


class ConfigError(Exception):
    pass


class FakeConfig:
    """Stand-in for Klipper's ConfigWrapper with real value semantics."""

    def __init__(self, name, printer, values=None):
        self._name = name
        self._printer = printer
        self._values = dict(values or {})

    def get_printer(self):
        return self._printer

    def get_name(self):
        return self._name

    def error(self, msg):
        return ConfigError(msg)

    def _raw(self, key, default):
        return self._values.get(key, default)

    def get(self, key, default=None):
        val = self._raw(key, default)
        return default if val is None else val

    def getboolean(self, key, default=None):
        val = self._raw(key, default)
        if isinstance(val, bool) or val is None:
            return val
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    def getint(self, key, default=None, minval=None, maxval=None):
        val = self._raw(key, default)
        return int(val) if val is not None else val

    def getfloat(self, key, default=None, minval=None, maxval=None):
        val = self._raw(key, default)
        return float(val) if val is not None else val


# Verified against the real Happy Hare checkout's extras/mmu source --
# see test_mmu_api_surface.py, which asserts this list stays accurate.
MMU_SPEC = [
    "action", "drive", "filament_pos", "gate_maps", "gate_selected",
    "initialize_filament_position", "move_filament", "num_gates",
    "select_gate", "tool_selected", "wrap_suppress_visual_log",
    "wrap_sync_gear_to_extruder",
]
GATE_MAPS_SPEC = ["gate_status", "gate_spool_id"]
MMU_DRIVE_SPEC = ["mmu_unit", "mmu_gear_stepper"]
MMU_UNIT_SPEC = ["p"]
MMU_UNIT_PARAMS_SPEC = ["gear_short_move_speed"]
MMU_GEAR_STEPPER_SPEC = ["get_position"]


def build_fake_mmu(mc, num_gates=6, gear_position=0.0):
    """Build a spec'd fake `mmu` using real constants from mmu_constants (mc)."""
    mmu = MagicMock(spec=MMU_SPEC)
    mmu.action = mc.ACTION_IDLE
    mmu.num_gates = num_gates
    mmu.tool_selected = -1
    mmu.gate_selected = -1
    mmu.filament_pos = mc.FILAMENT_POS_UNLOADED

    gate_maps = MagicMock(spec=GATE_MAPS_SPEC)
    gate_maps.gate_status = [mc.GATE_EMPTY] * num_gates
    gate_maps.gate_spool_id = [-1] * num_gates
    mmu.gate_maps = gate_maps

    gear_stepper = MagicMock(spec=MMU_GEAR_STEPPER_SPEC)
    gear_stepper.get_position.return_value = [gear_position, 0.0, 0.0, 0.0]

    unit_params = MagicMock(spec=MMU_UNIT_PARAMS_SPEC)
    unit_params.gear_short_move_speed = 80.0

    mmu_unit = MagicMock(spec=MMU_UNIT_SPEC)
    mmu_unit.p = unit_params

    mmu_drive = MagicMock(spec=MMU_DRIVE_SPEC)
    mmu_drive.mmu_unit = mmu_unit
    mmu_drive.mmu_gear_stepper = gear_stepper
    mmu.drive.return_value = mmu_drive

    mmu.move_filament.return_value = (0.0, False, 0.0, 0.0)
    mmu.wrap_suppress_visual_log.return_value.__enter__ = MagicMock(return_value=mmu)
    mmu.wrap_suppress_visual_log.return_value.__exit__ = MagicMock(return_value=False)
    mmu.wrap_sync_gear_to_extruder.return_value.__enter__ = MagicMock(return_value=mmu)
    mmu.wrap_sync_gear_to_extruder.return_value.__exit__ = MagicMock(return_value=False)

    return mmu
