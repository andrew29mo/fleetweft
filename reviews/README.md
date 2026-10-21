Current three-node authenticated MVP evidence: [reviews/mvp](mvp/README.md).

The following is historical exploration evidence from an earlier source revision.

# Four Linux VM protocol explorations — 2026-10-21

Run `ab21b5abe8753081`, executable source fingerprint:
`e7be82faaee962b6ebcba55a4cd70a0a997c6638526867b884a32fadbd49d3a7`.

[Raw JSON](evidence.json) · [Exact HTML](report.html) · [macOS portable tests](native-unit.json)
· [Production mutations](mutations.json) · [Attempt ledger](attempts.json) · [Audit fixes](../docs/AUDIT.md)

## Observed result

All four scenarios passed in an isolated Colima Linux VM. The production module
hashes installed in the wheel match this executable snapshot. The fixture created
two real systemd services, both running as `fleetweft-probe` with an empty capability
bounding set and NoNewPrivileges. The Controller and node were in separate network
namespaces connected by a veth. Python 3.12.3, systemd 255, Linux 6.8.0-117-generic,
aarch64. This is one VM, not three independent physical edge devices.

The audit snapshot passed **21 portable tests on macOS and 21 on Linux**, exact
test IDs matching, no errors/failures/skips. Six production mutations were
caught by assertions, not import/syntax errors. Twenty-seven corrupted-report controls
were rejected. These counts are separate: portable contracts, real service
scenarios, mutations and report controls are not interchangeable evidence.

| Exploration | Actual observation |
|---|---|
| Lost authorization/partition | A forwarding fixture completed grant retrieval and acceptance then dropped the reply; retries returned the same grant/accepted state. Taking the Controller-side veth DOWN broke real node-to-Controller requests while the local HTTP baseline still worked. Pause retained occupancy; cancellation required confirmed restoration before settlement. |
| Delayed executor | An external process with a cached preflight was SIGSTOPped. An old switch request during the successor's valid STAGED phase returned HTTP 409 without changing state. After v3 committed, resuming the external process also returned 409; external HTTP output remained v3 with the same worker. |
| Canary freshness | A worker claiming healthy returned 21 instead of expected 14. Its sample, premature commit, replayed sample, expired challenge and old-incarnation sample were rejected. Actual node process restart cleared observation binding; fresh samples were required for a new commit. |
| Crash recovery | SIGKILL of the actual node MainPID at STAGED, before route, after route, before commit and after durable commit. The first four recovered v1; after-commit reconstructed v2. Unit invocation/signal status and child retirement were checked. Controller SIGKILL preserved the outstanding grant across epoch change and required reconciliation. A lost finish reply was retried without duplicating settlement. |

At after-route, external HTTP already served v2 while the durable committed
baseline was still v1. SIGKILL bypassed graceful application rollback; the restarted
runtime reconstructed v1. At after-commit, SQLite already retained v2 and restart
reconstructed v2. This distinguishes recovery from a shutdown-before-test rollback.

The delayed-executor boundary is a cached preflight before the resource request.
It does **not** mean a writer was paused inside the check-and-switch critical
section while a second writer bypassed its lock. The route has one mutation owner;
there is no direct executable-worker route handle. Malicious local processes and
arbitrary root writers are not tested.

Canary uses three real application samples over at least 50 ms, with a two-second
challenge/commit-observation age bound. These accelerated experiment settings are
not production thresholds or representative fleet statistics. A deterministic portable Event/Condition test establishes the active-borrow drain
ordering; its skip-drain production mutation is caught by assertion. The separate
VM slow-HTTP observation alone does not prove the request remained active at the
exact retirement entry. Four consecutive commit/cancel operations each returned
with one live worker, exact obsolete identities retired, and correct external HTTP
results. Cancellation may transiently use a third worker, and stalled requests
may be interrupted after the 2.5-second drain bound.

No RSS, throughput,
recovery-time upper bound or speedup is claimed by this run.

## Corrections and failed attempts

The protocol was tightened to require a durable Controller commit authorization
before local COMMITTED. Otherwise canary rejection could arrive after the node had
already committed. Commit authorization and a confirmed execution result remain
separate; a lost response does not free occupancy.

The ledger retains all five development attempts and the audit rerun, not only the latest passing run:

- A: missing setuptools in the initially reused build environment; VM stopped.
- B: reset-failed on not-yet-loaded units was treated as a mandatory setup result.
- C: initial Type=simple service startup was mistaken for HTTP readiness.
- D: the same bounded readiness distinction was still missing after restart;
  authorization/partition and delayed-executor scenarios had passed, but the run
  remained failed.
- E: own pinned build environment, corrected readiness at every restart and exact
  source/test receipts; all four scenarios passed.
- Audit A: worker-retention fix, exact HTTP rejection, expanded evidence contracts,
  deterministic portable request-drain test and added real-process/HTTP observations;
  all four updated scenarios passed on the final identified snapshot.

No failed run was promoted to PASS. Raw logs remain ignored/local. The final VM
fixture units, dedicated user, workers, state, namespaces and uploaded source were
removed. The root-namespace nftables digest was unchanged and the VM ended Stopped.

## What this does not establish

These are **protocol/process-crash explorations**, not a complete fleet MVP.
The control APIs use isolated HTTP without authentication; TLS, signed artifact
downloads, continuous agent polling, three-node canary scheduling, latest-version
offline catch-up, availability budgets and fleet-wide rollback remain unimplemented
or untested. Wrong application results are rejected and the harness explicitly
requests compensation; autonomous business-health rollback is not established.

Only process restart in a running VM was tested. **VM/host reboot and sudden
power-loss recovery remain untested.** No actual device, firmware, bootloader,
storage corruption or disk-exhaustion claim follows from these observations.

```sh
.venv/bin/python -m tools.report reviews --current-source
```
