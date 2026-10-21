# Security policy

Fleetweft is an experimental, single-controller MVP, not production-qualified.
Only the current main branch is maintained. Review the operational boundaries in
[README](README.md) before running it. Signed application code is trusted code,
not a sandbox; never use the historical unauthenticated exploration service on an
exposed network.

## Reporting a vulnerability

Use GitHub's [private vulnerability reporting](https://github.com/andrew29mo/fleetweft/security/advisories/new).
Do not put credentials, private keys or exploitable vulnerability details in a
public issue. Include affected revision, reproduction steps and expected impact.
No response-time guarantee is offered.

## Repository controls

See [publication checks](docs/PUBLICATION.md) for the checked configuration.
Repository read access is public; write access remains restricted to the owner.
These controls do not establish that the code or dependencies are vulnerability-free.
