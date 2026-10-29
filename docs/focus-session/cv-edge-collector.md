# Optional local CV edge collector

`cogniflow-edge` is a separate opt-in process. FastAPI and core CogniFlow do not
import its CV dependencies or open a camera. Frames and MediaPipe results remain
in memory and are immediately reduced to scalars through a one-frame queue. Only
a validated five-minute `CvFeatureWindowEvent` reaches the authenticated API;
images, video, landmarks, embeddings, window titles, and screen content do not.

## Install and reviewed asset

The verified CachyOS lock uses CPython 3.11 x86-64/glibc 2.44,
`mediapipe==1.2.0`, and `opencv-contrib-python==5.0.0.93`:

```fish
uv sync --extra cv
```

The reviewed asset is Google's official Face Landmarker float16 bundle version
1: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`.
It is 3,758,596 bytes and has SHA-256
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.
MediaPipe code/package licensing is Apache-2.0; Google's linked model cards and
site terms remain authoritative for model usage.

Download is an explicit operator action. Store the binary outside Git. Startup
fails closed if it is missing or mismatched; capture and tests never download or
replace it.

```fish
mkdir -p $XDG_DATA_HOME/cogniflow/models
curl --fail --location --output $XDG_DATA_HOME/cogniflow/models/face_landmarker-v1.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
sha256sum $XDG_DATA_HOME/cogniflow/models/face_landmarker-v1.task
uv run --extra cv cogniflow-edge --consent-camera --session-id SESSION_ID \
  --model-asset $XDG_DATA_HOME/cogniflow/models/face_landmarker-v1.task
```

Without `--consent-camera`, the command exits before asset, API, CV imports, or
camera access. It waits for the next exact active-segment boundary before opening
the camera, releases resources on stop/error, and refuses partial windows.

Set the API key without exposing it in the process list:

```fish
read --silent --prompt-str 'CogniFlow API key: ' COGNIFLOW_EDGE_API_KEY
set --export COGNIFLOW_EDGE_API_KEY
```

`--api-key` remains compatible but is discouraged because other local users may
be able to inspect command arguments. `COGNIFLOW_API_KEY` is also accepted as a
fallback.

The process reports only bounded counters and status: camera index open/close,
window percentage, captured/processed/dropped counts, tracked-frame count,
effective FPS, and tracking ratio. Rejections identify no frames, no face track,
tracking below 80%, incomplete proxies, insufficient 10 FPS blink sampling, or a
partial window. Expected camera and quality limitations exit with status 2 and
no traceback. No frame content, landmarks, embeddings, or derived face geometry
is logged.

## Proxy definitions and limitations

- Face presence is tracked frames divided by sampled observations.
- Gaze-away is a `>=0.5` threshold over MediaPipe eye-look blendshapes.
- Head-pose variability is population variance of a rotation-matrix displacement
  proxy; it is not calibrated anatomical pose.
- A blink is an open-to-closed transition with both eye-blink scores `>=0.55`.
  Blink rate requires at least 10 effective FPS.
- At least 80% of observations must track a face and tracked observations must
  contain every proxy; otherwise no event is submitted.

These are observational proxies, not emotion, clinical cognitive load, a mental
health signal, an attention diagnosis, or ground-truth effort. Camera denial or
disconnection, absent dependencies/assets, weak tracking, a crash, or user stop
leaves the application behavior-only and never creates an all-zero measurement.

The v1 contract requires every feature when `camera_available=true`. It therefore
cannot represent a working camera with scientifically inadequate blink sampling;
this collector omits that event. A future reviewed contract should support
per-feature availability and quality counts rather than redefining missing data
as zero.

## Local synthetic performance evidence

On 2026-10-28, the real pinned CPU MediaPipe runtime and reviewed model processed
100 synthetic 640×480 black frames on the 16 GiB CachyOS host. At a paced 10 FPS,
median/p95 inference latency was 5.07/5.97 ms, effective throughput 9.99 FPS,
average process CPU was 0.088 cores, peak RSS was 219.7 MiB, and no frames
dropped. Per-frame CPU sampling measured 0.085 median and 0.100 p95 cores. An
unpaced maximum-throughput run reached 216.9 FPS with 4.54/4.96 ms latency but
used 1.73 cores and 229.9 MiB RSS. Thus the paced baseline met the one-core and
150 ms objectives; unrestricted throughput did not meet the CPU objective.

Black frames deliberately produced 0% tracking availability, so these figures
validate runtime cost and failure behavior, not feature accuracy. Release/stop
behavior and dropped-frame reconciliation used deterministic test doubles. No
real camera was opened and no real face recording was used.
