# Controller dynamic work area guard

## Scope

This iteration fixed four connected controller-safety issues:

- Manual/controller X/Y jogs no longer rely on a hardcoded `-travel..0` envelope when a profile supplies explicit machine-limit orientation.
- Jog safety now uses one dynamic machine-limit resolver for controller jogs, travel tests, and preview work-area calculations.
- X/Y jogs are checked against the current work-coordinate milling area as well as machine coordinates, so a negative jog at work X/Y `0` is blocked even when homing pull-off leaves a small negative machine margin.
- Z-only controller movement in fast mode uses the normal step interval, so Z motion remains smooth without L1/R1.
- A GRBL `error:` response invalidates predicted jog guard positions and requests fresh status, allowing recovery when the UI shows no active alarm.

## Behavior

`_current_machine_limits()` is now the shared source for current `_limits`, machine profile fields, and GRBL settings-derived travel. Explicit profile `machine_limits` preserve orientation, while plain travel values continue to default to the existing GRBL-compatible `-travel..0` interval.

The controller guard tracks both machine position and work position. Machine limits protect physical travel; work limits protect the usable milling coordinate area. If a negative-home setup exposes a work area such as `-3..297` because of homing pull-off, controller X/Y jog safety treats it as `0..297` for manual milling movement.

## Verification

- `python3 -m pytest tests/test_main_dock.py tests/test_gamepad.py tests/test_grbl_validator.py tests/test_machine_gcode_validator.py -q`
- `python3 -m pytest -q`
- `git diff --check`
