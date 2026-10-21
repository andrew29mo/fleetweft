# MVP acceptance after protocol exploration

Exploration pass is a gate to building the MVP, not a claim these conditions have
already passed. See the evidence directory for exact tested boundaries.

| Requirement | Required operational evidence | Current status |
|---|---|---|
| Grant durability and retry | Lost grant/accept/terminal response does not duplicate a change or release an unresolved slot | Exploration |
| Pause/cancel partition | Real network disconnection retains occupancy; reconnect, confirmed compensation and reconciliation free it | Exploration |
| Stale executor | Cached preflight followed by a late real switch request cannot change successor HTTP output | Exploration; not a paused write inside the critical section |
| Worker retention | Repeated successful/cancelled operations return with one worker, obsolete identities gone; deterministic pinned-request wait test plus real HTTP observation | Exploration; stalled requests may be interrupted after bounded drain |
| Canary freshness | Wrong business result despite healthy endpoint, replay, expired challenge and old agent identity cannot commit/promote | Exploration |
| Process crash | STAGED, before/after route, before/after commit have actual SIGKILL evidence and different committed/uncommitted recovery | Exploration |
| Controller crash | Durable grant survives epoch change; cannot grant a successor before reconciliation | Exploration |
| Three-node sequencing | A must pass canary before B/C activate; no hidden grants to offline nodes | Not implemented/tested |
| Offline catch-up | Original target stays incomplete; latest compatible version only after stale operations settle | Not implemented/tested |
| Fleet rollback | New generation restores captured per-node baseline; offline/failed restore prevents global success | Not implemented/tested |
| Availability policy | Separate active-change and observed-health budgets; test one already-offline node | Not implemented/tested |
| Trusted artifacts | Real signed payload, digest mismatch, truncated input, extraction limits, retained rollback copy and disk quota | Not implemented/tested |
| Node identity | mTLS, manual enrollment, lost-state rejection and explicit re-enrollment | Not implemented/tested |
| Service lifecycle | Installed shipping unit, agent crash and actual VM reboot, plus independently observed HTTP state | Exploration units only; VM reboot not tested |
| Operator experience | CLI plan/pause/resume/rollback/status and honest original target history | Exploration APIs only |

## Completion conditions for the actual MVP

- Package one immutable stateless application with a real verified rollback copy.
- Use three isolated same-platform Linux nodes and one Controller. Container
  observations and VM/service observations are reported separately.
- Persist fixed targets, canary choice, grants, occupancy and operator decisions.
- Demonstrate one normal rollout, one failed canary, one later-node failure,
  partially completed global rollback and an offline node returning after a newer
  version supersedes its previous target.
- Challenge delayed, duplicated and reordered commands and reports against actual
  serving versions. At least one negative control must corrupt each key safety
  decision and be caught by an assertion, not an import error.
- Never mark a target successful using only acceptance, a stored desired version,
  an expired timer, or a stale health observation.
- Preserve all scheduled requests/failures/unknowns in measurements and reports.
  No selecting only successful nodes or scenarios. Record process RSS separately
  from cgroup/VM memory and define all timing boundaries.
- After failure, prove controlled resources are retired and unrelated services,
  root firewall rules and network configuration remain unchanged.
- Require exact protocol rejection (HTTP 409), rather than counting arbitrary
  nonzero exits, import failures, crashes or HTTP 503 as admission protection.
- Verify actual serving release and application result on both sides of every
  crash boundary. At after-route, the candidate must have served before SIGKILL;
  after-commit must have a durable candidate commit before termination.
- Keep JSON/HTML checks complete: both installed units, namespace/identity, exact
  failure categories, canary bindings/window, worker retirement and every expected
  mutation name/test must remain present. Missing or contradictory observations
  cannot retain report PASS.

## Excluded claims

No control-plane HA, Byzantine/compromised-node protection, persistent-data
migrations, indefinite rollback retention, whole-fleet instantaneous cancellation,
zero downtime, statistical canary representativeness, firmware or hardware
qualification. VM reboot and sudden power-loss recovery remain untested until
their own evidence is collected. An unreachable target may require explicit
operator retirement; that is an incomplete/abandoned original target, not success.
