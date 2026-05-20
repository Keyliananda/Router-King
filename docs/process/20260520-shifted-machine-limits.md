# Process Note 2026-05-20

## Shifted GRBL Machine Limits

RouterKing profiles may store `machine_limits` as measured live GRBL `MPos`
bounds, not only normalized `[-travel, 0]` intervals. For the current machine
the verified safe bounds are:

```json
{
  "x": [-297.0, 103.0],
  "y": [-377.0, 23.0],
  "z": [-3.0, 57.0]
}
```

These spans are still `400 x 400 x 60`; the controller coordinate frame is just
shifted. Do not "fix" those values back to `[-400, 0]` or infer a smaller
machine from the post-homing `MPos`.

Use this distinction:

- `MPos` is the raw GRBL controller coordinate and may be shifted.
- `work_envelope_mm` is the usable travel span.
- `machine_limits` is the authoritative raw `MPos` safety box when
  `prefer_profile_limits` is true.
- `$130/$131/$132` are travel spans, not necessarily the displayed `MPos`
  interval endpoints.

Future validation, preview, and jog guards must preserve explicit profile
`machine_limits` orientation and offset. Only synthesize `[-travel, 0]` when no
measured limits are present.
