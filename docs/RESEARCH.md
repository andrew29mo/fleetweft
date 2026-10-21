# Research mapped to implementation decisions

These are reference materials, not claims that Fleetweft reproduces the guarantees
of the referenced products. No third-party implementation was copied into this
stdlib-only exploration. Tool/package licenses remain separate; an authored-source
license has not been chosen.

| Primary material | Decision informed |
|---|---|
| [Mender deployment model](https://docs.mender.io/overview/deployment) | Fix target membership; represent already-installed and individual outcomes |
| [Mender Update Module file API](https://github.com/mendersoftware/mender/blob/master/Documentation/update-modules-v3-file-api.md) | Separate installation, commit and compensating rollback; backend recovery contract |
| [hawkBit rollout management](https://github.com/eclipse-hawkbit/hawkbit/wiki/Rollouts%2BManagement) | Cohort admission, error thresholds and explicit stop conditions |
| [hawkBit DDI](https://github.com/eclipse-hawkbit/hawkbit/wiki/DDI-API) | Cancellation request and target cancellation acknowledgement are different events |
| [AWS UpdateJobExecution](https://docs.aws.amazon.com/iot/latest/apireference/API_iot-jobs-data_UpdateJobExecution.html) | Conditional execution-state updates; metadata CAS alone is not resource fencing |
| [Greengrass deployments](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-deployments.html) | Desired deployment and actual per-device outcome must be separate |
| [Kleppmann: distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) | A delayed writer needs rejection at the resource boundary; expiration alone is insufficient |
| [systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html) | Kill the service cgroup, inspect actual process identity and confirm retirement |
| [TUF specification](https://theupdateframework.github.io/specification/latest/) | Fixed signatures/checksums alone do not imply freshness, delegation or key-rotation protection |

## Questions resolved by the exploration design

- Pause stops new capabilities, not a remote action already authorized.
- A pending operation keeps its slot through lost messages, partitions and epoch
  changes; explicit actual terminal result is needed to settle it.
- The gateway's unique writer owns the check-and-switch critical section. An
  executor may request a switch but never own a direct stale route handle.
- A Controller commit decision must precede local COMMITTED, otherwise insufficient
  canary evidence could be discovered only after the node made its change durable.
- A local compensation remains an outcome of the same operation; fleet rollback
  uses a separate newer generation. They are not interchangeable concepts.

## Still missing evidence

Actual multi-node scheduling and availability budgets, signed artifact and disk
management, authenticated enrollment/re-enrollment, production application
compatibility, physical-device behavior and reboot/power-loss fault models. No
market demand, commercial advantage or measured operational savings have been
established by these experiments. The immediate product hypothesis is a small
stateless application fleet with intermittent control connectivity.
