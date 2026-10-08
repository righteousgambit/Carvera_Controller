# Ubuntu camera forwarding and recovery

The controller uses the local snapshot URL `http://127.0.0.1:18091/snapshot.jpg`.
The Ubuntu camera service owns port 8091; machine control remains a direct Mac-to-CNC
connection. Camera transport and CNC transport are independent.

On 2026-10-05 the saved URL refused connections because the local forward had
stopped. Authenticated Tailscale SSH inspection found `carvera-camera.service`
active with its existing localhost camera listener. Its local snapshot returned
HTTP 200. A direct camera-port connection from the Mac was refused, so recovery
restored the existing loopback SSH path without changing the remote service.

The Mac user LaunchAgent `com.carvera.camera-forward` now supervises the SSH
forward. Its listener binds only to 127.0.0.1; `ExitOnForwardFailure`, server-alive
checks, BatchMode and strict host-key checking are enabled. Launchd retries after
failure with a 15-second throttle and starts it at user login. This does not add
network exposure, grant new access or configure machine motion.

Standard SSH found a stale key for the Ubuntu address. The current public host
key was read over the already authenticated Tailscale SSH path and pinned in the
forward's separate known-hosts file. The user's normal known_hosts and SSH
configuration were preserved. Future identity changes fail strict verification
and require a fresh authenticated identity check; do not disable checking.

Local configuration lives in `~/Library/LaunchAgents/com.carvera.camera-forward.plist`
and `~/.carvera/camera-ssh-known-hosts`. Logs are `~/.carvera/camera-forward-error.log`
and `~/.carvera/camera-forward.log`. These are machine-local configuration, not
portable job assets. `launchctl print gui/$(id -u)/com.carvera.camera-forward` reads
its state. `launchctl bootout gui/$(id -u)/com.carvera.camera-forward` stops it;
bootstrap the existing plist to start it again. These operations affect camera
viewing only. A running forward alone does not prove a fresh image.

Recovery readback confirmed HTTP 200, JPEG bytes and the remote frame timestamp,
with a measured frame age of 0.123 seconds. Native DESKTOP186 displayed the image
with `Live · captured 0.1s ago`, while reporting Idle and zero spindle/feed. Exact
receipts are `/private/tmp/carvera-camera-recovery-receipt-20261005.json` and
`/private/tmp/carvera-camera-forward-config-20261005.json`. This closes recovery
of the existing camera viewing path. Physical camera registration, synchronization,
measurement accuracy and the full camera-calibration workflow remain open.

A controlled failure check terminated only the verified owned SSH forward.
Launchd KeepAlive restarted it under a different PID; HTTP 200 and fresh JPEG
recovered with a frame age of 0.064 seconds. Exact readback:
`/private/tmp/carvera-camera-restart-probe-20261005.json`. No remote camera service
restart or CNC command was required. User-login restart behavior is configured,
but an actual logout/login cycle has not been exercised.
