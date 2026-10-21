# MIT license adoption

Fleetweft-authored source and documentation now use the [MIT License](../LICENSE),
Copyright (c) 2026 Andrew Yuan. The repository was Private when this licensing
snapshot was verified. It is now Public following explicit owner authorization;
see [publication checks](PUBLICATION.md). Licensing alone does not change access.

README, THIRD_PARTY_NOTICES and pyproject agree on MIT. The package declares
`license = "MIT"` and includes `LICENSE` in both wheel and source distribution.
The built wheel has `License-Expression: MIT` and `License-File: LICENSE`; its
packaged license bytes match the repository. Package verification details are in
[package.json](../reviews/mit/package.json). No third-party runtime Python package,
interpreter, model, dataset, cryptographic binary or VM image is bundled.

[Third-party notices](../THIRD_PARTY_NOTICES.md) distinguish first-party MIT from
external licenses. Installed build-tool metadata and primary upstream license
references were checked. No conflict was identified for the current first-party
wheel/source distribution. External tools keep their own terms; this is not a
claim that the entire deployment image is MIT or that future bundled dependencies
would need no further review.

The full source snapshot now includes LICENSE, so wheel creation inside the Linux
validation fixture includes the same license as local builds. Relative to the
pre-MIT audit, manifest changes are LICENSE, pyproject.toml, tools/evidence.py,
tools/mvp_fixture.py and tests/test_mvp.py. Product modules and service units are
identical; the fixture retains MIT as payload comments and the new test checks it.
This preserves the distinction between a license/packaging change and a runtime
feature change.

The first-party sample app includes the full MIT notice as comments before signing;
the three-entry bundle format and application behavior are unchanged. Generic
caller-supplied payloads are not automatically relicensed.

A fresh complete run `06663f42a7edc9a0` passed: 69 tests on each of macOS/Linux,
15 production mutations, 15 live VM scenarios, actual orderly VM restart and 22
report controls. Cleanup completed and the VM is stopped. Source fingerprint:
`9ceff8e59cdad02b944a6f58dd6ce3b7296ede9d7f9a3f00527b14d8a91706fd`.

[Current validation](MVP_VALIDATION.md) links JSON/HTML, exact source receipts and
fresh measurements. No speedup or improvement is inferred from timing differences
between single runs. Sudden power loss, boot-zero-gap and independent physical
hosts remain untested. Earlier records describing unselected licensing retain
that historical scope and are not silently rewritten as MIT-era validation.
