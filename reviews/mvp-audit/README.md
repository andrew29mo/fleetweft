Historical pre-MIT audit snapshot. Current MIT/package verification is in
[reviews/mit](../mit/README.md). Reproduce this archive with its matching revision.

# Audited Fleetweft MVP evidence

Final run `e746ebafc9d228b4`; executable/unit/unit-file/tool source fingerprint:
`aaabf9003e084bab1582e8812dc89e6124c3849f7ff602df351bb6505a893423`.

[Audit findings/fixes](../../docs/MVP_AUDIT.md) · [Original interpretation](https://github.com/andrew29mo/fleetweft/blob/2a2d5be/docs/MVP_VALIDATION.md)
· [JSON](evidence.json) · [HTML](report.html) · [macOS](native-unit.json)
· [Linux](linux-unit.json) · [Mutations](mutations.json) · [All attempts](attempts.json)
· [Actual systemd query output](systemd-query-probe.json)

68 portable tests per platform, 15 assertion-catching production mutations,
15 live VM scenarios, actual orderly VM stop/start and 22 report-corruption controls
passed. These are separate evidence categories. All fixed measurement requests
are retained. No physical fleet, power-loss, boot-zero-gap or production assurance
is claimed. Keys, databases, wheels, environment paths and private logs are excluded.

Validation with the matching source/tool revision:

```sh
.venv/bin/python -m tools.mvp_report reviews/mvp-audit --current-source
```
