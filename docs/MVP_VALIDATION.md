# MVP validation — 2026-10-21

Final run: `f519bcdfd6cd873a`.
Executable/unit/shipping-unit/tool source SHA-256:
`e4f127e0bc1ff972b0d2b5643a67d23561b2b39e8bed1cb96f54752079ec1d37`.
Documentation and receipts are outside that source manifest. No runtime changes
were made after the final snapshot was taken.

[Complete JSON](../reviews/mvp/evidence.json) · [Matching HTML](../reviews/mvp/report.html)
· [macOS unit receipt](../reviews/mvp/native-unit.json) · [Linux unit receipt](../reviews/mvp/linux-unit.json)
· [Mutation receipt](../reviews/mvp/mutations.json) · [All MVP attempts](../reviews/mvp/attempts.json)

## Verification result

- **41/41 macOS and 41/41 Linux portable tests**, identical IDs and source hashes;
  zero failures, errors or skips. The worker-readiness test uses a real subprocess
  with a synthetic process identity on both platforms; actual Linux identities and
  route recovery are separately exercised in the VM.
- **11 production mutations** caught by assertion failures: stale incarnation,
  wrong business result, expired challenge, missing commit decision, forgotten
  reconciliation, skipped drain, bypassed canary, replaced node identity,
  automatic restart resume, bypassed artifact signature and non-atomic settlement.
  Import errors/crashes do not count as caught mutations.
- **10 real VM scenarios** listed below; **14 corrupted-report controls** rejected.
  These are distinct evidence categories, not 65 interchangeable tests.
- Installed wheel module hashes match every corresponding source module. The
  shipping controller/node units match the manifest; fixture drop-ins add only
  namespace and topology dependencies. Each service runs as `fleetweft`, with
  NoNewPrivileges, empty capabilities and KillMode=control-group.
- Cleanup confirms service MainPID=0, removed namespaces/configuration/test keys,
  unchanged root ruleset digest, removed installed snapshot and stopped VM.

Environment: one Colima VZ Linux ARM64 VM, four CPUs, 6 GiB configured memory;
Linux 6.8.0-117-generic, systemd 255, Python 3.12.3. macOS portable tests use
Python 3.12.14. Four isolated network namespaces represent a controller and three
agents; they share one kernel, disk, Unix service account and failure domain.
No three-host, WAN, physical-device or container performance claim is made.

| Scenario | Observed result |
|---|---|
| Normal canary | A settles its actual serving v2 result before any B/C grant; all three serve v2 and fleet completes |
| Bad canary | A reports healthy but returns 21 instead of 14; baseline v1 restored, fleet paused, no follower grant |
| Startup failure | A verified signed app exits during startup; failed worker is retired, v1 serves, fleet pauses |
| Later failure / partial rollback | A commits `badb`, B's real result fails, C disconnects; rollback is incomplete until C returns; all then verify v1 |
| Offline catch-up | C remains an incomplete original v2 target; v3 supersedes it; after return C receives v3 with no hidden v2 grant |
| Partition | A has durably STAGED its grant when its veth goes down; pause retains exactly that slot; compensation after reconnect settles it |
| Process crash | Actual systemd agent and Controller MainPIDs receive SIGKILL; new service InvocationIDs appear and real committed v2 serves |
| Authentication / tampering | Missing client cert and untrusted server CA fail TLS; wrong role, cross-node poll and public node mutation get exact 409; a truncated HTTPS bundle never activates |
| Delayed command | Old token cached before mutation is invoked after a successor activates; the actual Node writer rejects it and real signed v3 worker/route remains unchanged |
| Measurements | All 30 fixed sequential real mTLS requests retained; expected result/version verified; per-service and worker RSS recorded separately |

Additional VM restart evidence is retained separately from those ten scenarios.
Before orderly VM stop, A actually serves candidate v3 while its durable journal
is still ACTIVATING with committed baseline v2; B/C have committed v2. In the new
boot, a root fixture topology unit reads the journal **before Agent startup** and
observes the same pending token/phase/baseline. After service startup, A serves v2
and reports FAILED_RESTORED; committed B/C reconstruct v2. Controller occupancy
settles and remains paused. Different boot IDs and service InvocationIDs are
recorded. This excludes shutdown-before-test rollback as the explanation.

## Real measurements and their boundaries

One final controlled run, not an SLO or capacity estimate:

| Observation | Result | Definition |
|---|---:|---|
| Request success | 30/30 | Fixed A/B/C round-robin sequence, x=7, expected result 14 and release v2; no discarded failure |
| Median request latency | 11.67 ms | One persistent driver; each request includes a new mTLS connection, node gateway, worker execution and full JSON response read |
| p95 request latency | 27.42 ms | Nearest-rank p95 of all 30 measurements, not repeated-run confidence |
| Maximum request latency | 28.87 ms | Maximum of this small sequential sample |
| Agent SIGKILL → observed new-incarnation v2 response | 1.349 s | Starts before sending systemctl kill; includes polling/client launch overhead; not a recovery-time upper bound |

Driver/netns startup is outside individual request latency. The driver issues no
concurrent load; no saturation throughput, speedup, WAN latency or statistical
performance conclusion follows. Scenario `seconds` includes orchestration and
verification requests and must not be presented as a pure deployment duration.

RSS is `/proc/<pid>/status` VmRSS at one post-request observation, in KiB:

| Process | RSS KiB |
|---|---:|
| Controller | 23,924 |
| Agent A | 49,072 |
| Agent B | 47,480 |
| Agent C | 47,604 |
| App worker A | 18,584 |
| App worker B | 18,584 |
| App worker C | 18,564 |

These are VM process RSS snapshots, not peak memory, PSS, cgroup/VM memory or a
memory-saving comparison. Shared pages must not be interpreted as unique memory
by simply adding RSS. Each measured node retains one worker at this boundary.

## Reproduce and validate

Use the dedicated stopped VM command in README, then:

```sh
.venv/bin/python -m tools.mvp_report results/fresh-mvp-run --current-source
.venv/bin/python -m tools.mvp_report reviews/mvp --current-source
```

The verifier checks stage outcomes/timeouts, source hashes, installed wheel,
platform receipts, service identity, scenario ordering/results, original targets,
reboot journal and cleanup, then compares exact regenerated HTML. A PASS flag by
itself cannot render a passing incomplete report. Earlier exploration reports
must be reproduced with their matching historical revision/tooling; they predate
this MVP and have different source and mutation manifests.

All four MVP attempts are retained in the ledger. Attempt 2's VM work passed but
its report-control exception handling failed, so the runner rejected the attempt;
it was fixed before the final successful snapshot. Superseded passes remain
historical observations rather than being merged with the final measurements.

## Not tested / not established

Sudden power loss, partial storage writes/corruption, boot-zero-gap policy,
independent host failures, physical fleet behavior, long-duration/saturated load,
malicious signed applications/nodes/root, certificate lifecycle, general
application compatibility, persistent data migration, HA and internet-facing DoS
resilience. The orderly VM restart evidence must not be relabeled as power-loss
recovery. The three-sample canary is a functional gate, not statistical confidence.
