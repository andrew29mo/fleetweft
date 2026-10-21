# Publication checks

Checked on 2026-10-22 (Asia/Taipei), with explicit owner authorization to publish
`andrew29mo/fleetweft`. The repository is Public and GitHub identifies the root
LICENSE as MIT. Only owner `andrew29mo` has direct write/admin access; public read
access and forks do not grant writes to this repository.

## Source and retained validation

The published executable/test/license snapshot matches the MIT validation source
fingerprint `9ceff8e59cdad02b944a6f58dd6ce3b7296ede9d7f9a3f00527b14d8a91706fd`.
[Current validation](MVP_VALIDATION.md) and [MIT receipts](../reviews/mit/README.md)
retain run `06663f42a7edc9a0`: macOS/Linux each 69 tests, 15 production mutation
controls, 15 isolated-VM service scenarios, an orderly VM stop/start, and 22 report
corruption controls. The current-source verifier accepts the JSON and regenerated
HTML. Publishing does not constitute a new Linux VM run or remote CI pass.

The publication change updates documentation and repository controls, not product
modules, shipping service units, or the executable validation manifest. Historical
Private/pre-MIT review statements retain their original historical scope.

Before publication, 81 tracked files and all 145 reachable historical file blobs
were checked for private-key blocks, common GitHub token formats and personal host
paths; none matched. No generated credentials, runtime databases, wheels, private
results, personal AGENTS files or VM images were tracked. This focused scan is not
proof that no secret or vulnerability can exist.

## Security settings read back from GitHub

- Secret scanning and secret-scanning push protection enabled.
- Dependabot vulnerability alerts and automatic security updates enabled.
  Weekly pip version-update configuration is included. Runtime has no external
  Python packages. Scanner coverage does not establish the security of separately
  installed Linux, OpenSSL, VM tooling or sample applications; development tools
  mentioned only in commands are not a complete dependency inventory.
- Private vulnerability reporting enabled; see [security policy](../SECURITY.md).
- main protection applies to administrators: force pushes and branch deletion
  disallowed, linear history and conversation resolution required. Direct owner
  commits remain allowed; mandatory second-person approval is not configured for
  this single-maintainer project.
- Actions defaults to read-only tokens and cannot approve pull requests. Only
  GitHub-owned actions are allowed; other third-party actions are not allowlisted.
  All external contributors require approval before fork PR workflows run.
- There are no tracked Actions workflows or required remote status checks. The
  local macOS/Linux receipts are the validation evidence, not a remote CI result.

At the check, secret-scanning and Dependabot APIs returned zero open alerts.
Scanning is asynchronous and limited to supported detectors/dependency sources;
zero reported alerts is not a vulnerability-free guarantee. Settings can change,
so this document records a point-in-time check, not continuous monitoring.

Sudden power loss, boot-zero-gap protection, three independent physical nodes,
HA, production qualification and performance SLAs remain outside the evidence.
