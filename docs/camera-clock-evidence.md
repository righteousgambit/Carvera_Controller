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
