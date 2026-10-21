# Fleetweft

Experimental durable coordination for small edge application rollouts.

This repository currently contains **four protocol explorations**, not the full
fleet manager. A single Controller and one agent/gateway run as separate installed
Python services in two isolated Linux network namespaces. Real subprocess HTTP
applications exercise the resource being changed. The later three-node scheduler
is a specification, not an implemented feature.

The name Fleetweft is provisional. The repository stays Private. No open-source
license has been selected; no permission to redistribute is granted by this README.

## Implemented exploration core

- SQLite FULL-synchronous grant/occupancy records, one controller owner, retry of
  the same grant, explicit pause/cancel/reconcile semantics.
- One local route writer: it validates operation and agent incarnation while
  holding the mutation lock. An external executor has no direct route handle.
- Real HTTP application samples, unpredictable rotating challenges, sample
  sequence, recipe digest, route/worker identity and observation window checks.
- A Controller commit decision before local COMMITTED persistence; restart
  reconstructs a committed version, or compensates an unfinished candidate.
- Commit/cancel retirement of obsolete workers: route borrowing and switching
  share a lock, pinned requests get a bounded drain, then old processes are reaped.
- Exact installed-module provenance, real systemd SIGKILL boundaries, raw JSON
  observations, HTML, source fingerprints and corrupted-report checks.

The bounded application backend supports only built-in `v1`, `v2`, `v3` and a
deliberately wrong `bad` release. Its digest identifies the installed worker recipe
and release label, **not a downloaded/signed artifact**. Canary experiment thresholds
are three samples over at least 50 ms with a two-second freshness bound. They are
test settings, not production recommendations or a statistical quality guarantee.

## Read first

- [Architecture and protocol](docs/ARCHITECTURE.md)
- [Revised MVP acceptance conditions](docs/MVP_ACCEPTANCE.md)
- [Research and design decisions](docs/RESEARCH.md)
- [Audit findings and fixes](docs/AUDIT.md)
- [Retained experiment evidence](reviews/README.md)

## Reproduce

Python 3.12+ is required. Runtime has no third-party Python dependencies. The
Linux experiments additionally require systemd, iproute2, nftables and a dedicated
stopped Colima VM. The runner creates/removes only its owned fixture resources
and stops the VM afterward. Do not use a VM serving unrelated workloads.

```sh
python3.12 -m venv .venv
.venv/bin/pip install build==1.3.0 setuptools==80.9.0 wheel==0.45.1
.venv/bin/python -m unittest discover -v
.venv/bin/python -m tools.validate_vm \
  --colima-home /path/to/dedicated-colima-home \
  --toolchain /path/to/pinned-colima-and-lima/bin \
  --output results/fresh-run
.venv/bin/python -m tools.report results/fresh-run --current-source
```

Raw logs, SQLite state, wheels and environment-specific paths remain under ignored
results directories. Retained JSON contains only historical experiment operations,
not real credentials. The report is incomplete until cleanup and provenance pass.

## Boundaries

Control APIs deliberately have **no authentication or TLS** and belong only in
the harness's isolated namespaces. The fixture unit runs services as a dedicated
unprivileged user with no capabilities; this is not application-code sandboxing.
An authenticated control protocol and signed artifacts remain required before an
operational MVP. Do not expose these exploration APIs as a deployment service.

The experiments do not establish full fleet canary rollout, autonomous continuous
polling, artifact download security, availability budgets, physical-device support,
VM/host reboot recovery, power-loss durability, or malicious-agent resistance.
Actual client connections may fail during process restart. No universal
zero-downtime, recovery-time or throughput claim is made.

Obsolete-worker drain is bounded at 2.5 seconds, after which stalled requests may
be interrupted by retirement. No guarantee that every request survives a switch
or cleanup failure is made. Terminal worker retention, not a memory reduction,
is what the exploration measures.
