# Architecture

The backend owns the authoritative state. `CameraService` captures continuously on a dedicated thread. `VisualecRuntime` samples the newest frame at the configured inference interval, runs `DetectionService` outside the event loop, assigns bottom-center points with `ZoneService`, advances monotonic timers in `OccupancyService`, and asks `RelayService` to reconcile desired state. Only transitions are persisted and transmitted to hardware.

`RuntimeState` is a locked, in-memory projection for low-latency WebSocket snapshots. SQLite stores configuration and audit events; frontend restarts therefore do not lose analytics history. SQLAlchemy isolates storage-specific code so PostgreSQL is the intended production upgrade.

Failure policy:

- Missing/disconnected camera produces no frames, reports an offline state, and triggers reconnect attempts plus the configured camera-loss safety action.
- Relay commands use bounded retry/timeout and only update authoritative state after acknowledgement.
- Duplicate desired states are no-ops.
- Emergency stop disables inference and forces all relays OFF until explicit reset.
- Manual overrides expire using monotonic time; automatic reconciliation then resumes.
