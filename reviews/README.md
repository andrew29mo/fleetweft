# Four Linux VM protocol explorations — 2026-10-21

Run `765bd7248cef5f62`, executable source fingerprint:
`58902eb436bd5710253e99d58520633669c39114c66cd056a2f059870f02ae43`.

[Raw JSON](evidence.json) · [Exact HTML](report.html) · [macOS portable tests](native-unit.json)
· [Production mutations](mutations.json) · [Attempt ledger](attempts.json)

## Observed result

All four scenarios passed in an isolated Colima Linux VM. The production module
hashes installed in the wheel match this executable snapshot. The fixture created
two real systemd services, both running as `fleetweft-probe` with an empty capability
bounding set and NoNewPrivileges. The Controller and node were in separate network
namespaces connected by a veth. Python 3.12.3, systemd 255, Linux 6.8.0-117-generic,
aarch64. This is one VM, not three independent physical edge devices.

The same snapshot passed **15 portable tests on macOS and 15 on Linux**, exact
test IDs matching, no errors/failures/skips. Five production-core mutations were
caught by assertions, not import/syntax errors. Sixteen corrupted-report controls
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
not production thresholds or representative fleet statistics. No RSS, throughput,
recovery-time upper bound or speedup is claimed by this run.

## Corrections and failed attempts

The protocol was tightened to require a durable Controller commit authorization
before local COMMITTED. Otherwise canary rejection could arrive after the node had
already committed. Commit authorization and a confirmed execution result remain
separate; a lost response does not free occupancy.

The ledger retains all five development attempts, not only the final passing run:

- A: missing setuptools in the initially reused build environment; VM stopped.
- B: reset-failed on not-yet-loaded units was treated as a mandatory setup result.
- C: initial Type=simple service startup was mistaken for HTTP readiness.
- D: the same bounded readiness distinction was still missing after restart;
  authorization/partition and delayed-executor scenarios had passed, but the run
  remained failed.
- E: own pinned build environment, corrected readiness at every restart and exact
  source/test receipts; all four scenarios passed.

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
