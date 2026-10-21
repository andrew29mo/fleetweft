# MVP acceptance

Current receipts and exact results are in [MVP validation](MVP_VALIDATION.md).
Historical exploration evidence retains its original fingerprint and is not
relabeled as evidence for the new scheduler or authenticated artifact path.

| Requirement | Evidence required and retained |
|---|---|
| Three-node canary | Installed services: A's actual serving samples and committed result settle before any follower grant |
| Failure pause | Wrong business result and candidate startup failure restore baseline, retain failure and prevent follower grants |
| Later-node failure / fleet rollback | A can commit while B fails; a disconnected C prevents global rollback success until it reconnects and verifies its baseline |
| Offline catch-up | Original target C remains incomplete; superseding v3 reaches C without a hidden v2 grant |
| Lost authorization / network partition | STAGED A's real veth is disabled; pause does not release its grant; reconnection and confirmed compensation settle it |
| Restart recovery | Shipping systemd agent and controller SIGKILL; changed InvocationID and independently observed serving version |
| Actual VM restart | Different boot ID and service InvocationIDs; pre-agent journal still has pending ACTIVATING state, then A restores v2 while committed B/C reconstruct v2 |
| Poll ordering | Same-boot old poll cannot replace a newer baseline; sequence floor survives Controller restart and resets only for a valid newer boot |
| Lost commit decision reply | Real mTLS response loss plus pause/rollback still settles the original authorization; no new authority inferred |
| Terminal health | Failed committed worker pauses propagation; failed restored worker retains UNKNOWN until an actual healthy baseline is reconstructed |
| Stale executor | Cached earlier token invokes the actual Node mutation method after a successor activates; real signed backend route/result remain unchanged |
| mTLS | Missing client certificate and untrusted server CA fail TLS; wrong-role/cross-node/public-node-mutation requests get exact HTTP 409 |
| Signed artifacts | Production verifier tests wrong signing key, truncated bytes, payload changes, unsafe entries, platform mismatch, quota and changed cached app; actual HTTPS tampered bundle refuses and leaves baseline serving |
| Portable tests | Identical formal Python/unit/service-file source fingerprint and test IDs on macOS/Linux; no skips/errors/failures |
| Negative controls | Named production mutations must fail assertions, not imports/execution errors; report corruption controls reject incomplete/contradictory evidence |
| Metrics | All fixed sequential requests retained with timing boundary; per-service and worker RSS separated; VM observations labeled |
| Cleanup | Run-specific account/unit/link/namespace ownership must match; unknown/replaced resources block cleanup. Units MainPID=0, namespaces/config/private keys removed, root firewall digest unchanged, snapshot removed and VM stopped |

## Scope of the evidence

Formal tests include reducer contracts and isolated worker-startup/drain tests;
they do not individually establish complete networking behavior. VM scenarios use
the installed wheel, matching source hashes, real signed payloads, mTLS sockets and
shipping service units with namespace-only drop-ins. Original single-node crash
boundary and lost-reply exploration receipts are historical; new scheduler claims
rely on the current MVP receipts, not those old source revisions.

The stale-executor VM scenario delays a cached command **before entering** the
mutation method. It does not pause a write inside the critical section. Linux
workers are actual subprocesses; this is not testing firmware, containers or
physical devices. Three namespaces do not represent independent host failures.

Orderly VM stop/start is tested separately from SIGKILL. No sudden power loss,
corrupt-disk repair, boot-zero-gap protection, zero downtime, control-plane HA,
statistical canary confidence, compromised-node/root resistance or application-data
migration is claimed. The min-other-health observation can become stale; it is
not an SLA. Unknown occupancy may require manual diagnosis and prevents progress.
