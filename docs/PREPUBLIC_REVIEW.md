# Pre-publication review — 2026-10-21

Reviewed base commit: `2a2d5be6cb32a51accfc64dd84e2388ce9b8f517`.
Runtime/test/service/tool fingerprint:
`aaabf9003e084bab1582e8812dc89e6124c3849f7ff602df351bb6505a893423`.

The current review changes documentation and ignore rules only. Runtime, formal
tests, service units and validation tools remain byte-identical to the audited VM
snapshot. No additional live Linux VM run or new performance measurement was made
for this review. The retained Linux evidence is reused because its complete
source fingerprint matches; a new macOS unit/mutation check was performed.

## Outcome and evidence

| Area | Checked result |
|---|---|
| Current implementation | Reviewed control/agent flow, signed artifact and mTLS entry points, worker lifecycle and shipping units against documented scope |
| Current macOS tests | 68 passed, zero failures/errors/skips; [fresh receipt](../reviews/prepublic/native-unit.json) |
| Production negative controls | 15 assertion-catching mutations passed again; [fresh receipt](../reviews/prepublic/mutations.json) |
| Matching Linux/VM record | [Audit run e746ebafc9d228b4](../reviews/mvp-audit/evidence.json): 68 identical Linux tests, 15 live VM scenarios, actual orderly VM reboot and successful cleanup |
| JSON/HTML | Current verifier and all 22 corruption controls passed; exact regenerated HTML matches the retained report |
| Metrics | Recomputed all 30 fixed A/B/C requests: median 11.74 ms, nearest-rank p95 24.31 ms, max 28.30 ms; RSS and 1.352 s observed restart interval match the raw record |
| Packaging | Built wheel has 18 entries: first-party modules plus distribution metadata; module bytes match source, no tests/tools/credentials/database/interpreter vendored, no third-party Python runtime requirements |
| License | No project LICENSE or license declaration in pyproject/wheel metadata; GitHub licenseInfo remains unset. Installed build-tool license metadata agrees with THIRD_PARTY_NOTICES |
| Repository privacy | Four pre-review reachable commits and 112 unique blobs scanned for key/token patterns, personal paths, credential URLs/assignments, unexpected email addresses and excluded artifact paths; none found |
| Access state | Owner and target verified as andrew29mo/fleetweft, Private, main at the reviewed commit, collaborator list contains only the owner; no access or visibility change |

The privacy check combines file/history inspection with pattern checks; it is not
proof against every possible secret encoding or a third-party security assessment.
Git author metadata uses the intended GitHub noreply identity. Retained node UUIDs,
operation IDs, process IDs and private-range/documentation addresses are generated
fixture observations, not active production credentials. Keys and runtime state
were removed in the recorded cleanup. Local results, environments and personal
agent instructions are ignored and have not been uploaded.

## Corrections in this review

- Clarified that post-commit failure pauses the fleet at **operation settlement**.
  After a target has settled successfully, later heartbeat failures update health
  observations/admission but do not automatically revoke its historical canary
  pass or trigger rollback. A direct production-reducer check confirmed admission
  can continue if another healthy node satisfies the policy. No continuous fleet
  monitor or automatic repair is claimed.
- Removed a stale combined-test-count example and tidied scope wording so portable
  tests, production mutations, live scenarios and report controls remain separate.
- Corrected OpenSSL's classification: artifact verification is a runtime dependency,
  not solely test infrastructure. Recorded packaging's actual license expression
  as Apache-2.0 OR BSD-2-Clause; this does not license Fleetweft itself.
- Added ignore rules for generated certificates/CSRs/PKCS#12 material, wheel files,
  coverage/cache output and logs. No already tracked artifact needed removal.

## Publication boundary

Technical/documentation checks above are complete within the stated MVP scope.
The repository remains Private and the project license remains unselected as
requested. This is not an open-source release, production qualification or a
permission to change visibility. There is no remote CI pass claim; evidence is
local macOS and the recorded isolated Linux VM workflow.

The evidence does not establish sudden power-loss recovery, boot-zero-gap
protection, independent host/physical-device behavior, saturation throughput,
peak/unique memory, HA, compromised-node resistance, continuous canary monitoring
or an operational SLO. See [full validation limits](MVP_VALIDATION.md).
