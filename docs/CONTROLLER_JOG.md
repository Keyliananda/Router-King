# Controller Jog

RouterKing supports optional gamepad-assisted manual jogging in the FreeCAD
dock. The feature is off by default and only sends jog commands when all of the
following are true:

- RouterKing is connected to GRBL.
- No G-code stream is running.
- Limit exploration is not running.
- The machine state is Idle or Jog.
- Controller jogging is enabled in the UI.

## macOS + DualShock 4

Modern macOS versions support the PlayStation DualShock 4 controller directly.
No kernel driver is required for normal USB or Bluetooth pairing.

Recommended setup:

1. Pair the controller in macOS Bluetooth settings, or connect it using a USB
   cable that supports data.
2. Start FreeCAD and open the RouterKing dock.
3. In the Control tab, use Controller Jog -> Connect Controller.
4. Use `Test Controller` to verify all sticks, triggers, and buttons before
   enabling machine jogging.
5. Enable controller jogging only while positioning the machine.

## Python dependency

FreeCAD 1.0.2 on this Mac includes PySide2 but does not expose
`PySide2.QtGamepad`. RouterKing therefore uses `pygame` as an optional input
backend.

Install `pygame` into FreeCAD's Python environment before using the controller
feature. RouterKing keeps working without it; the Controller Jog panel will show
that pygame is missing.

## Default mapping

- Right stick and DPad: X/Y
- L2: Z-
- R2: Z+
- L1: slow speed
- R1: medium speed
- no shoulder button: fast speed

RouterKing sends short `$J=G91 ...` jog segments and throttles output to avoid
flooding GRBL. Machine-limit checks still run before every jog segment.

The `Controller Bindings` section can assign multiple controls to the same
action. Entries are comma-separated names from `Test Controller`, for example
`Right X` plus `DPad Left`/`DPad Right` for X movement. Axis bindings can be
inverted with a leading `-`, such as `-Right Y`.
Use `Learn` beside a binding row to capture the next pressed button or strongly
moved axis directly from the controller. `Clear` removes that row's bindings.

The Control tab sections are collapsible. Keep `Controller Bindings`,
`Machine Limits / Tests`, and `Console` collapsed when they are not actively
needed. `Test Controller` opens as a separate minimizable window and disables
controller jogging while it is open.

Use `Test Controller` for live input diagnostics. The tester reads pygame/SDL
only, disables controller jogging before opening, and never sends GRBL commands.

## Manual XYZ probe mode

After a Z probe, use `Prepare Manual XYZ` before positioning the first pocket
corner. The button is a mode switch only; it does not send any motion command.
This avoids moving in work coordinates when the active work offset is not the
intended one.

Controller jogging in this mode is checked against homed machine coordinates.
RouterKing uses the current GRBL `MPos` plus the configured machine travel
limits (`$130/$131/$132` or `machine_profile.json`) and clamps or blocks jog
segments that would leave the valid machine envelope.

When a controller is connected, RouterKing enables the controller immediately
after entering Manual XYZ mode. If machine position or limits are unknown,
controller jogs are blocked until a fresh status report/limits are available.
