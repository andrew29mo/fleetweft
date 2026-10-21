# Deployment: explicit trust and state provisioning

This MVP targets a trusted single-platform stateless application. It is not a
remote arbitrary-command executor. Use a test environment first. A signed app has
the agent's Unix privileges; the systemd restrictions are not a tenant sandbox.

## Provisioning order

1. Install the wheel in `/opt/fleetweft/venv`. Create an unprivileged `fleetweft`
   account. Create `/etc/fleetweft` and per-service `/var/lib/fleetweft/{controller,a,b,c}`
   directories. Protect private keys/configuration, assign state/cache directories
   to that service user, and keep application signing/CA private keys offline.
2. Provision a CA and separate certificates: one `operator`, one `controller`, and
   one for each node with CN `a`, `b`, `c`. Server certificates require SANs matching
   their HTTPS URLs and serverAuth; polling clients require clientAuth. Certificates
   are verified against the configured CA and server hostname/IP. CA issuance must
   enforce unique role identities. Example fixture certificates expire after two
   days and are test-only; this is not a credential lifecycle system.
3. Build each release using `fleetweft bundle --app app.py --release v2 --key
   /offline/sign.key --output v2.zip`. Publish only the public verification key,
   immutable bundles and release-to-bundle SHA-256 catalog. Bundle platform is
   `linux-aarch64`; only that platform is qualified by current evidence.
4. Prepare controller/node configurations below. Provision the controller with
   `fleetweft provision-controller --config /etc/fleetweft/controller.json`.
5. As the node service user, run `fleetweft provision-node --config
   /etc/fleetweft/a.json`; retain its printed `node_uuid`. Then seed the verified
   baseline using `fleetweft cache --config /etc/fleetweft/a.json --release v1
   --bundle /path/to/v1.zip`. Repeat for b/c. Provision/cache are explicit offline
   administrative operations; the service never silently reinitializes missing
   state or overwrites a damaged committed cache.
6. Install the supplied controller and node template units. The operational layout
   is normally one unit per host; the VM fixture uses network-namespace drop-ins
   to isolate three agents on one VM. After starting the controller, enroll all
   three identities before creating a fleet: `fleetweft ctl --config operator.json
   enroll --body '{"node":"a","node_uuid":"<provisioned identity>"}'`.
   Enrollment is allowed only before a fleet exists. Lost/replaced node state
   requires deliberate reprovisioning of the experiment, not automatic adoption.
7. Start nodes; wait until all three baselines have been observed. Use `ctl status`,
   then `ctl deploy --body '{"release":"v2","canary":"a"}'`. Use `ctl pause`,
   `ctl resume`, `ctl rollback`. An unfinished grant prevents resume/supersession;
   reconnect and reconcile it first. A rollback request is durable even when it
   must wait for a disconnected node's current operation to settle.

Run `systemctl daemon-reload` after installing units. Enable only the controller
or node units needed on that host. They use Restart=on-failure, a one-second retry
and five starts per minute. Invalid cache/configuration can exhaust this limit;
auto-restart is not a repair mechanism. An operator must repair the cause and
reset the failed unit. Do not discard journals to bypass unknown occupancy.

## Configuration shape

```json
{
  "role": "node",
  "node": "a",
  "state": "/var/lib/fleetweft/a",
  "listen": "192.0.2.11",
  "port": 19443,
  "controller": "https://192.0.2.1:19443",
  "ca": "/etc/fleetweft/ca.crt",
  "cert": "/etc/fleetweft/a.crt",
  "key": "/etc/fleetweft/a.key",
  "signing_public_key": "/etc/fleetweft/sign.pub",
  "cache": "/var/lib/fleetweft/a/cache",
  "cache_quota": 1048576,
  "catalog": {"v1": "<64 lowercase hex characters>", "v2": "<64 lowercase hex characters>"}
}
```

Replace documentation-only IPs with actual host addresses. Controller config uses
`role=controller`, its own state/listen/cert/key, the **same immutable catalog**,
`bundles=/opt/fleetweft/bundles`, and optional `samples`/`window`. Store each bundle
as `<sha256>.zip` in that directory. The operator config needs only `controller`,
`ca`, `cert`, `key`. No certificate/key material belongs in Git.

The sample application contract is a Python file taking `release instance`
arguments, writing one JSON `{"port":12345}` readiness line within three seconds,
then serving loopback HTTP `/work?x=7&challenge=...&delay_ms=0`. It returns release,
worker instance, identical challenge, `result=2*x` and a healthy flag. The canary
uses the result independently of the health flag. This fixed contract makes the
MVP verifiable; it is not an arbitrary application health language.

## Operational boundaries

- Manual fixed membership, single controller, no certificate revocation/rotation
  automation, no RBAC groups or external immutable audit sink.
- Local FULL-synchronous SQLite records are recovery state, not tamper-proof
  evidence against root, a compromised trusted app, or broken storage.
- Catalog/signing trust is manually provisioned. No TUF metadata expiry,
  threshold signatures, key rotation or generalized anti-freeze protection.
- Cache quota is per node and includes retained bundles, extracted files and
  incomplete staging files. There is no online garbage collector: exhausted quota
  refuses the new grant and preserves the baseline. History is bounded to eight
  superseded fleets and 2,048 journal events; capacity exhaustion rejects changes
  and needs operator maintenance. There is no hidden eviction of rollback state.
- HTTPS request bodies/responses, artifact sizes, startup waits and worker drains
  are bounded. Connection/thread admission is not a hardened internet-facing DoS
  boundary; keep endpoints on a protected management network.

## Audit-era protocol compatibility and recovery

Agents now send ordered poll sequence numbers within each persistent boot identity.
Upgrade controller and agents together during a stopped experiment; mixed older
protocol versions are not supported. Do not reset state to bypass replay checks.

Pause prevents new authorization; an already-persisted approval can be retried
without losing that durable decision. If an application fails after committing,
the commit remains recorded but the fleet pauses and the target fails. If a
restored baseline cannot be probed, the original slot stays UNKNOWN. Reconnect or
restart the Agent and verify its retained baseline before resuming. The MVP has no
independent application watchdog that automatically repairs every worker failure.
