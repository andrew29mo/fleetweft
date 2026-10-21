# Protocol exploration audit — 2026-10-21

This audit checks the experimental single-Controller/single-node implementation,
not a production fleet manager. Retained results and exact source are linked in
[the evidence index](../reviews/README.md).

## Findings corrected

1. **P2: obsolete workers accumulated across operations.** Every activation and
   cancellation spawned a worker, but commit/cancel never retired earlier workers
   until service shutdown. Resetting the fixture between cases hid the growth.
   Terminal operations now drain existing route borrows, kill/wait obsolete
   workers, close handles and update journal children. The repeated-operation VM
   check requires one terminal worker and exact old-process retirement.
2. **P2: execution failure could masquerade as admission rejection.** The partition
   test accepted any nonzero exit from its new-plan request. It now requires the
   real Controller's HTTP 409 and expected client exit category; unrelated errors
   fail the experiment. Transport loss has its own distinct category.
3. **P2: report PASS did not require key raw observations.** Changing after-route's
   pre-crash HTTP release to baseline, supplying wrong application output, deleting
   unit evidence or replacing rejection with a signal could still pass. Checks now
   require both units, exact response/failure categories, each pre-crash phase and
   serving release, application output, canary observation bindings and window,
   worker retention, complete mutation receipts and optional native receipts.

The concurrency review also challenged the new drain test: seeing an in-flight
request before calling cancel does not guarantee it remains in flight when cancel
arrives. A deterministic portable test now blocks the production Node.work
transport, waits until retire_obsolete is actually waiting, asserts no kill,
then releases the request and requires retirement. A production mutation removes
that wait and must be caught by assertion. The VM slow-request observation is
complementary and is not presented as a deterministic schedule proof.

## Evidence interpretation

Installed wheel hashes match the source manifest; real services run with separate
network namespaces and no capabilities. The node/Controller tests call the same
core and HTTP services as the exploration entry points, not a second simulator.
Portable tests use controlled data/transport boundaries; real process retirement,
network disconnection and SIGKILL evidence come from the separate Linux VM run.

Pause retains unresolved occupancy. Stale executor tests include a successor's
valid STAGED phase, so a mismatched phase alone cannot explain rejection. Canary
tests include healthy-looking wrong business data and old/expired/replayed
observations. Five node crash points distinguish pending compensation from
durable commit reconstruction; Controller restart preserves the pending grant.

No full fleet scheduler, authenticated enrollment, TLS, signed downloads, VM reboot
or sudden power-loss capability is promoted by this audit. No RSS/performance
benefit, universal request continuity or recovery SLA is claimed.
