# MVP validation — MIT snapshot

Final run: `06663f42a7edc9a0`.
Source/package/license/unit/service/tool SHA-256:
`9ceff8e59cdad02b944a6f58dd6ce3b7296ede9d7f9a3f00527b14d8a91706fd`.
Documentation and receipts are outside that source manifest. No runtime changes
were made after the final snapshot was taken.

[Complete JSON](../reviews/mit/evidence.json) · [Matching HTML](../reviews/mit/report.html)
· [macOS unit receipt](../reviews/mit/native-unit.json) · [Linux unit receipt](../reviews/mit/linux-unit.json)
· [Mutation receipt](../reviews/mit/mutations.json) · [All MVP attempts](../reviews/mit/attempts.json)

## Verification result

- **69/69 macOS and 69/69 Linux portable tests**, identical IDs and source hashes;
  zero failures, errors or skips. The worker-readiness test uses a real subprocess
  with a synthetic process identity on both platforms; actual Linux identities and
  route recovery are separately exercised in the VM.
- **15 production mutations** caught by assertion failures: stale incarnation,
  wrong business result, expired challenge, missing commit decision, forgotten
  reconciliation, skipped drain, bypassed canary, replaced node identity,
  automatic restart resume, bypassed artifact signature, non-atomic settlement,
  lost approval replay, reordered polls, ignored terminal probe and unverified compensation.
  Import errors/crashes do not count as caught mutations.
- **15 real VM scenarios** listed below; **22 corrupted-report controls** rejected.
  These are distinct evidence categories and must not be added into one test count.
- Installed wheel module hashes match every corresponding source module. The
  shipping controller/node units match the manifest; fixture drop-ins add only
  namespace and topology dependencies. Deployed unit file hashes are retained.
  Ownership tests use mocked commands and real temporary files; the VM separately
  proves the owned resource lifecycle, not the presence of real foreign resources.
  Each service runs as `fleetweft`, with
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
| Reordered report | An actual authenticated old A poll is rejected with 409; v3 captures every v2 baseline and rollback restores v2 |
| Lost approval / pause | Real TLS proxy forwards and durably authorizes, drops the first reply; pause retains the grant, exact approval replay lets A settle without follower grants |
| Lost approval / rollback | Same loss boundary; rollback waits for the authorized result and then verifies all three original baselines |
| Failed committed worker | SIGKILL of real v2 worker after COMMITTED; HTTP 503 is observed, durable commit remains recorded, target fails and fleet pauses without followers |
| Failed restored worker | SIGKILL after FAILED_RESTORED; failed probe keeps the exact grant UNKNOWN until actual Agent restart reconstructs a healthy baseline |
| Measurements | All 30 fixed sequential real mTLS requests retained; expected result/version verified; per-service and worker RSS recorded separately |

Additional VM restart evidence is retained separately from those fifteen scenarios.
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
| Median request latency | 11.10 ms | One persistent driver; each request includes a new mTLS connection, node gateway, worker execution and full JSON response read |
| p95 request latency | 28.31 ms | Nearest-rank p95 of all 30 measurements, not repeated-run confidence |
| Maximum request latency | 28.75 ms | Maximum of this small sequential sample |
| Agent SIGKILL → observed new-incarnation v2 response | 1.201 s | Starts before sending systemctl kill; includes polling/client launch overhead; not a recovery-time upper bound |

Driver/netns startup is outside individual request latency. The driver issues no
concurrent load; no saturation throughput, speedup, WAN latency or statistical
performance conclusion follows. Scenario `seconds` includes orchestration and
verification requests and must not be presented as a pure deployment duration.

RSS is `/proc/<pid>/status` VmRSS at one post-request observation, in KiB:

| Process | RSS KiB |
|---|---:|
| Controller | 23,848 |
| Agent A | 49,172 |
| Agent B | 47,544 |
| Agent C | 48,380 |
| App worker A | 18,580 |
| App worker B | 18,580 |
| App worker C | 18,576 |

These are VM process RSS snapshots, not peak memory, PSS, cgroup/VM memory or a
memory-saving comparison. Shared pages must not be interpreted as unique memory
by simply adding RSS. Each measured node retains one worker at this boundary.

## Reproduce and validate

Use the dedicated stopped VM command in README, then:

```sh
.venv/bin/python -m tools.mvp_report results/fresh-mvp-run --current-source
.venv/bin/python -m tools.mvp_report reviews/mit --current-source
```

The verifier checks stage outcomes/timeouts, source hashes, installed wheel,
complete source-discovered test IDs, deployed unit hashes, both process restart
identities, scenario ordering/results, original targets, reboot journal and actual
node phases, fixed A/B/C request assignments and cleanup, then compares exact
regenerated HTML. A PASS flag by itself cannot render a passing incomplete report. Earlier exploration reports
must be reproduced with their matching historical revision/tooling; they predate
this MVP and have different source and mutation manifests.

Both MIT-era attempts passed; the final snapshot also retains the full MIT notice
in each generated first-party signed app and tests that preservation. Its source
manifest includes LICENSE and MIT packaging metadata. Product runtime modules and
shipping units match the preceding audit snapshot; the unit suite adds one license
propagation contract. This run refreshes provenance
and packaging evidence; differences from older one-run timing/RSS values are not
claimed as performance improvements.

The [earlier four audit attempts](../reviews/mvp-audit/attempts.json) remain
historical. Those include two preflight rejections before upload and a Linux mock
isolation failure after live scenarios. They were not converted to passes or
merged into this run. Original pre-MIT MVP/exploration evidence and its own source
fingerprints remain available in reviews/mvp and reviews/ respectively.

## Not tested / not established

Sudden power loss, partial storage writes/corruption, boot-zero-gap policy,
independent host failures, physical fleet behavior, long-duration/saturated load,
malicious signed applications/nodes/root, certificate lifecycle, general
application compatibility, persistent data migration, HA and internet-facing DoS
resilience. The orderly VM restart evidence must not be relabeled as power-loss
recovery. The three-sample canary is a functional gate, not statistical confidence.
