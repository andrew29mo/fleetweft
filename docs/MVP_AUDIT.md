# MVP audit and regression coverage

The initial `493966e` MVP receipts passed their recorded checks. Independent
runtime and security/evidence reviews identified additional passing-but-wrong
sequences; a green initial receipt did not cover these sequences.

## Confirmed defects and changes

| Finding | Trigger and consequence | Fix and regression evidence |
|---|---|---|
| Reordered same-incarnation report | After v2 commits, an older report can replace the Controller's baseline with v1; the next rollback can target the wrong version | Per-boot poll sequence is persisted and strictly increasing; generation/revision cannot regress. Production reducer tests and an authenticated stale-poll VM request preserve the v2 baseline through a v3 rollout/rollback |
| Lost authorization reply plus pause/rollback | Controller persists approval, reply is lost, pause blocks reauthorization while cancellation is suppressed; unresolved grant cannot settle | Identical durable approval is replayable only for the same token/incarnation/route and without pending reconciliation. Real mTLS fixture forwards approval, drops the first reply, gates polls until pause/rollback, then verifies exact replay and settlement |
| Negative probe after commit | Actual COMMITTED report with failed current worker probe still marks canary passed and admits followers | Preserve the durable COMMITTED fact and settle known execution, but mark target failed and pause; do not promote. VM kills the real candidate worker at after_commit and verifies HTTP 503 and no follower grant |
| Unverified compensation | FAILED_RESTORED label could clear occupancy without a functioning baseline | Keep the original grant UNKNOWN and pause until the baseline actually probes correctly. VM kills the restored worker at after_cancel, verifies retained token, then restarts Agent and verifies baseline before settlement |
| Foreign VM resources | Failed setup after useradd collision could delete an existing account; existing unit files could be overwritten/deleted | Full host/guest preflight plus exclusive creation and a run/inode/hash ownership ledger. Unknown, changed or partially recorded resources cause failure; mock/tempfile regression tests cover foreign accounts, units, symlinks, namespaces, interfaces and cleanup failures. Real VM tests exercise the owned setup/reboot/cleanup path |
| Incomplete/contradictory report | Both platform receipts could omit the same tests; controller restart ID and reboot node phase were not fully checked; request node labels could be changed | Exact source-discovered test IDs, actual deployed unit hashes, both service restart identities, reboot node snapshots, fixed A/B/C assignments and corrupted-report controls |
| Oversized local artifact reads | Runtime cache/server read whole files before checking lengths | Bounded reads with pre-read size checks for cache bundle/app and artifact serving; sparse oversized-cache regression. This is a resource bound, not protection against compromised root |

The earlier seen_ns=0 test sentinel was also replaced by an explicitly expired
relative monotonic timestamp. Supported Python 3.12 receipts already passed;
this improves the test's clock assumption rather than repairing production time.

## Important distinctions

A durable commit is an execution fact, not proof that an application still serves.
If its current probe fails, the Controller records that committed fact and the
failed release outcome separately; it pauses rather than spreading the release.
A failed restoration has not met its postcondition, so it keeps occupancy. A
stopped/failed worker may require an Agent restart; there is no claim of a fully
autonomous application supervisor or unlimited recovery.

An already-issued durable approval may be replayed after pause. This does not
issue new authority, and does not permit another route/incarnation or a fresh
commit decision while paused. Controller restart still requires reconciliation.

Ownership tests with synthetic commands/files are distinguished from the real
VM's owned-resource lifecycle. They do not establish safe recovery from malicious
root, arbitrary concurrent host administration or sudden power loss. The VM is
explicitly dedicated and protected by the host's profile lock.

The fault proxy is test infrastructure, not a product alternate write path: it
uses real mTLS to forward requests into the installed Controller, loses one real
approval response, and later resumes traffic. Actual Agent/Controller code, signed
applications and shipping service units are exercised. The proxy itself is a
tracked, unprivileged fixture unit and is stopped during cleanup.

See [current validation](MVP_VALIDATION.md) for final source, all attempts,
measurements, JSON/HTML and remaining limits. No power-loss, boot-zero-gap,
physical-fleet, HA or production-grade security claim follows from this audit.
