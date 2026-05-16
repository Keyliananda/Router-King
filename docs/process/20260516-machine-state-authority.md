# Process Note 2026-05-16

## Machine State Authority before Streaming

Decision: before real machine streaming, the live GRBL controller state is the
source of truth. RouterKing must read current status and coordinate parameters
after Auto Connect, homing, or probing before validation and streaming.

The active work offset comes from live `WCO` when reported, or from live GRBL
coordinate parameters (`$#`, active `G54`) when status reports omit `WCO`.
`machine_profile.json` remains a cache/fallback for limits, settings, probe
defaults, and offline validation; cached `work_offset` or `status` values must
not override the connected controller state for a real stream.
