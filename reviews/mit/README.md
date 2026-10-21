# MIT snapshot verification

[License adoption](../../docs/LICENSE_ADOPTION.md) · [Current validation](../../docs/MVP_VALIDATION.md)
· [JSON](evidence.json) · [HTML](report.html) · [macOS](native-unit.json)
· [Linux](linux-unit.json) · [Mutations](mutations.json) · [Attempt](attempts.json)
· [Wheel/source license verification](package.json)

Run `06663f42a7edc9a0`, source fingerprint
`9ceff8e59cdad02b944a6f58dd6ce3b7296ede9d7f9a3f00527b14d8a91706fd`:
69 tests per platform, 15 production mutations, 15 VM service scenarios,
orderly VM stop/start and 22 report controls passed. MIT applies to first-party
code; external dependency notices remain separate. This snapshot was verified
while Private; the repository is now Public. See
[publication checks](../../docs/PUBLICATION.md).

```sh
.venv/bin/python -m tools.mvp_report reviews/mit --current-source
```

Private keys, runtime journals, wheels, source archives and VM images are excluded.
No power-loss, continuous fleet monitoring or production-readiness guarantee is made.
