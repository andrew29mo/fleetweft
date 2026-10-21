# Fleetweft

A small, single-controller release manager for three Linux edge application nodes.
It rolls out a signed stateless Python HTTP application through a designated
canary, pauses on failed business checks, and restores captured per-node baselines
through new, fenced operations.

**Public, MIT-licensed MVP.** See [LICENSE](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md). This is not production qualification.

## What it implements

- A pull agent and mutually authenticated TLS control plane. Operators can deploy,
  pause, resume, request rollback and inspect original target history. Nodes cannot
  issue operator commands or impersonate another enrolled node.
- SQLite FULL-synchronous grants, fixed rollout targets and durable commit
  decisions. Fleet progress and grant settlement share one transaction.
- Canary checks against the actual serving worker: result, signed bundle digest,
  worker/route identity, rotating challenge, sample sequence, observation duration
  and freshness must agree before commit. Experiment settings are three samples,
  at least 150 ms, and a two-second freshness limit; not statistical confidence.
- At most one granted change, with at least one **other recently observed healthy**
  node before admission. These are separate policies, not an availability guarantee.
- Loss of contact retains an issued grant. Pause stops admission; cancellation
  must be confirmed by actual baseline serving evidence; an unverified restoration
  remains UNKNOWN. At operation settlement, a committed candidate with a failed
  current probe pauses the fleet without hiding the durable commit fact. An offline ungranted target stays
  incomplete and can catch up to a superseding release without pretending its
  older rollout succeeded.
- Higher-generation rollback, persistent node identity/boot sequence, ordered
  poll reports, controller reconciliation and a single local mutation writer
  prevent stale operations from
  changing a successor route.
- Bounded signed ZIP packages: RSA/SHA-256 verification through system OpenSSL,
  SHA-256 content addressing, strict entries/size/platform checks, atomic cache
  promotion and a hard cache quota. Retained baselines are not evicted automatically.
- Shipping unprivileged systemd units, bounded worker startup and request drain,
  process cleanup, reproducible JSON evidence and deterministic HTML reports.

## Evidence and limits

See [MVP validation](docs/MVP_VALIDATION.md) for the exact source fingerprint,
platform results, all scenarios, latency/RSS definitions and retained JSON/HTML.
[Acceptance conditions](docs/MVP_ACCEPTANCE.md) distinguish implementation,
observations and excluded claims. Earlier four-protocol exploration reports remain
historical evidence, with their own source fingerprints.

The supported backend is one trusted, signed, stateless Python file on the tested
Linux ARM64 platform. The three nodes are network namespaces within one isolated
VM, not three physical hosts. The agent and application share a Unix identity;
signing authorizes trusted code, not sandboxing. An unresponsive/compromised node,
CA compromise, persistent application data, HA, automatic certificate rotation,
indefinite history/cache retention and arbitrary update plugins are outside scope.

Orderly VM restart and process SIGKILL tests do not establish sudden power-loss
durability, storage-corruption repair, boot-zero-gap protection or zero downtime.
Requests may fail during restart or after the 2.5-second obsolete-worker drain
expires. An unknown grant can block progress indefinitely until reconciled. After a target
settles successfully, later heartbeat failures affect health observations and new
admission checks; they do not automatically revoke the earlier canary result or
trigger fleet rollback. Continuous rollout monitoring requires additional design.

## Use and reproduce

Python 3.12+, system OpenSSL and Linux systemd are required for the operational
service. Runtime has no third-party Python packages. macOS runs portable tests;
it does not run the Linux agent backend.

- [Deployment, credentials and CLI](docs/DEPLOYMENT.md)
- [MVP architecture](docs/ARCHITECTURE.md)
- [Research and trade-offs](docs/RESEARCH.md)
- [Pre-publication review and license status](docs/PREPUBLIC_REVIEW.md)
- [MVP audit and regressions](docs/MVP_AUDIT.md)
- [Earlier exploration audit](docs/AUDIT.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Publication checks](docs/PUBLICATION.md)
- [Security policy](SECURITY.md)

```sh
python3.12 -m venv .venv
.venv/bin/pip install build==1.3.0 setuptools==80.9.0 wheel==0.45.1
.venv/bin/python -m unittest discover -v
.venv/bin/python -m tools.validate_mvp \
  --colima-home /path/to/dedicated-colima-home \
  --toolchain /path/to/pinned-colima-and-lima/bin \
  --output results/fresh-mvp-run
```

The runner requires an existing **stopped, dedicated** Colima VM (systemd,
Python venv support, OpenSSL, iproute2 and nftables installed). It refuses occupied
fixture paths, takes an immutable source/wheel snapshot, runs both platform suites,
installs shipping services with namespace-only fixture drop-ins, restarts the VM,
checks cleanup and stops it afterward. Timeouts/nonzero exits are failures.
Ignored `results/` holds private logs, keys and runtime state. Only sanitized
receipts are retained in `reviews/`; never commit test credentials or snapshots.

The old `fleetweft.service` HTTP exploration entry point is retained solely for
historical reproduction. The `fleetweft` command uses the mTLS MVP entry point.
Do not expose the unauthenticated exploration service.
