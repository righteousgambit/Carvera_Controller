# Request-bound camera clock evidence

The camera Source tab displays a reported server-to-desktop clock interval and,
when the service declares frame timestamp precision, a frame-time interval in
local monotonic seconds. Recorded camera replay also shows that interval relative
to the selected controller status **receipt**. These are timing estimates under
explicit assumptions; neither interval qualifies sensor exposure synchronization,
controller sample time, physical position, or machining engagement.

Each existing JPEG GET carries a fresh UUID in `X-Camera-Request-ID`. A cooperating
origin service records UTC at request arrival and immediately before sending
headers, echoes that exact nonce, and sends:

| Response header | Meaning |
| --- | --- |
| `X-Camera-Request-ID` | Exact current request nonce; never a cached echo |
| `X-Camera-Clock-ID` | UUID generated at service start or clock epoch change |
| `X-Camera-Request-Received` | Origin request arrival UTC, Unix seconds |
| `X-Camera-Response-Sent` | Origin response-header UTC, Unix seconds |
| `X-Camera-Clock-Precision` | Declared maximum timestamp error, seconds |
| `X-Camera-Frame-Precision` | Optional independently declared frame timestamp error |
| `X-Camera-Frame-Time-Basis` | Optional `jpeg-assembled` or service-declared `sensor-exposure` |

`machine.camera_clock.camera_clock_headers` is the origin-service hook. The service
must retain its existing `X-Camera-Frame-Time` frame timestamp rather than relabel
response time as frame capture. This repository change does not deploy the hook to
Ubuntu, change clocks, camera settings, forwarding configuration, or CNC control.

The desktop records UTC and monotonic time before the GET and after the bounded
JPEG transfer. Nonnegative one-way transit bounds the server-minus-client offset
between server-send minus client-receive and server-receive minus client-send.
No symmetric-link assumption or HTTP Date value is used. Declared precision,
observed local UTC/monotonic discrepancy, numeric rounding, and an explicit
**assumed 100 ppm relative clock-rate bound** widen intervals. That rate has not
been measured. Frame translation uses at most 30 seconds of extrapolation and
requires independently declared frame precision. Clock steps, endpoint timestamp
semantics and the physical sensor timestamp need independent qualification.

Missing, replayed, incomplete, nonfinite, reversed or inconsistent clock metadata
withholds clock estimates while retaining an otherwise valid JPEG and receipt-time
association. A service clock identity change is visible and prevents association
across that epoch. Invalid metadata never changes raw frame timestamps or silently
substitutes receipt time for capture time.

References and lens studies retain the immutable exchange. New camera manifests
use schema 2 and retain clock evidence with their existing hash chain, bounded
writer and JPEG integrity checks. Readers still accept schema 1; portable camera
bundles retain both forms. Replay remains ordered by local receipt time; estimated
frame timing is separate evidence and does not move controller poses.

Verification uses a real localhost HTTP origin with a deliberate two-minute clock
offset, missing/invalid/replayed metadata, asymmetric transit, epoch changes,
strict numeric/identity validation, exact reference/manifest/bundle round trips,
and rendered live/replay views at narrow and wide sizes. All controller commands
are intercepted and asserted absent. Actual Ubuntu service support, measured
clock stability, installed-runtime use and physical synchronization remain open.

## Prepared integration for the existing Ubuntu origin

Readback on 2026-10-10 found the user `carvera-camera.service` running
`/home/wes/.local/share/carvera-camera/viewer.py`, SHA256
`d2508383aa96508cf15b11814de5f097e6eba20bbd8d93ea1fe72b5c18295548`. Its timestamp is
assigned after the FFmpeg JPEG reaches the service, rather than at sensor
exposure. The prepared integration explicitly labels that basis `jpeg-assembled`.
It preserves the original FFmpeg arguments, listeners, allowed-client rules,
HTML viewer, camera control/query and POST validation semantics.

`python3 scripts/prepare_camera_origin.py original-viewer.py new-output-directory`
prepares `viewer.py`, a standalone `camera_origin.py`, and a SHA256 readback
receipt. It requires the reviewed original hash and unique source structure,
compares protected AST semantics, reads only bounded regular source files and
refuses existing outputs. It creates local reviewable files; it does not connect,
install, restart services or send camera/CNC controls. Partial failed attempts
remain preserved. The helper uses only Python's standard library.

The origin brackets each UTC read with monotonic reads. Its declared precision
covers that sampling bracket and timestamp quantization. Observed clock steps
or invalid samples rotate the service clock epoch. Requests spanning an epoch
change receive no clock estimates; an otherwise valid response remains
available. A cached frame from an older epoch receives no frame-time precision.
A fresh same-epoch frame restores the estimate. Absent or malformed request
nonces preserve legacy JPEG behavior without reflecting arbitrary header text.
The reported precision and rate/no-step assumptions do not qualify absolute UTC
accuracy, sensor exposure, FFmpeg buffering delay or machine position.

Client records retain the optional timestamp basis. Old clock records without
that field remain readable. References, manifests and portable camera bundles
preserve the basis; live/replay notices distinguish JPEG assembly from an
unverified sensor-exposure declaration. Numeric rounding also covers local
monotonic timestamps; unsupported timestamp resolution is refused.

Qualification includes portable HTTP/patch tests and thirteen tests against the
exact prepared service source with FFmpeg/camera controls intercepted. A
memory-only probe on the existing Ubuntu Python 3.12.3 compiles the candidate
service and executes the exact standalone helper, including real clock sampling
and nonce/epoch/basis checks. It writes no remote files and does not run capture
or restart the service. Actual origin deployment and physical synchronization
remain separate OPEN gates. Before deployment, independently revalidate the live
source hash and support-file ownership, retain a rollback copy and read back both
installed file hashes and the resulting live protocol after the camera restart.

`python3 scripts/verify_camera_origin.py new-receipt.json` checks the configured
default loopback feed (or an explicit `--url`). It retains only bounded metadata,
JPEG hashes and clock records; source URLs, image bytes and request-exception
details are withheld. 2–8 JPEG GETs require accepted clock metadata, the reviewed
JPEG-assembly basis, reported freshness within two seconds, one clock epoch,
unique request nonces, advancing local receipts and advancing/nondecreasing frame
timestamps. Repeated timestamps across the whole probe do not qualify. Receipt
writes are exclusive with fsync/readback; a protocol gap returns exit code 2.
Even a passing receipt does not prove installed service-file identity, sensor
exposure, actual content freshness, physical accuracy or machine position. Those
need their separate authoritative observations.

## Authorized live origin deployment, 2026-10-10

After Wes explicitly approved deployment, independent live source/ownership and
service readback matched the reviewed original hash above. The exact prepared
`viewer.py` (SHA256 `6c0831545f3766919a781f8f76865aa15efb682bf33cb35f77fd8953c2ec98dd`)
and `camera_origin.py` (SHA256
`4a9f19ce37b68329819d051add19482af241eaef24dbab9af416f9d8115ec745`)
were installed with a retained original rollback copy. Only the existing user
camera service was restarted; its unit file remained byte-identical.

Independent post-restart file/service readback and four live forwarded snapshot
requests passed. Frames remained 1280 by 720; exact nonces, one clock epoch,
advancing frame timestamps and accepted JPEG-assembly metadata were retained.
Reported frame-age upper bounds were approximately 0.05–0.20 seconds in that
probe. Deployment, readback and metadata-only protocol receipts are retained in
`carvera-camera-deploy-20261010/`. This closes that deployment and live protocol
scope. Sensor exposure, measured clock-rate stability, optical registration,
installed desktop timing display and physical synchronization remain OPEN.
