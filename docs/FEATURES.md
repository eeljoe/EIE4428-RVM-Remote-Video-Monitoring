# Optional analysis modules

Four analysers sit on top of the monitoring pipeline described in the README.
None of them is required to stream; each one reports itself **unavailable**
instead of failing when a dependency or a model file is missing, and the
dashboard shows the difference between "switched off", "still starting",
"unavailable" and "working on an empty scene".

| Module | File | Backend | Depends on |
|---|---|---|---|
| Object tracking | `analysis/track.py` | connected regions + nearest-centroid matching | nothing |
| Face identification | `analysis/recognition.py` → `FaceRecognizer` | MediaPipe FaceLandmarker landmarks | `mediapipe` + `models/face_landmarker.task` |
| Expression classification | `analysis/recognition.py` → `EmotionRecognizer` | MediaPipe FaceLandmarker blendshapes | same model |
| Hand gestures | `analysis/gesture.py` | MediaPipe HandLandmarker | `mediapipe` + `models/hand_landmarker.task` |
| Acoustic events | `audio/` | RMS / zero-crossing rate / spectral centroid | `pyaudio` + a microphone |

## Installing the analysers

```powershell
pip install -r requirements.txt            # core stream
pip uninstall -y opencv-python-headless    # FIRST: see below, keep ONE cv2
pip install -r requirements-analysis.txt   # THEN the analysers and contrib
```

**Keep exactly one OpenCV distribution, and remove the headless one first.**
MediaPipe depends on `opencv-contrib-python`, and it installs into the same
`cv2/` directory as `opencv-python-headless`. Whichever is installed last wins,
and uninstalling either one deletes files the survivor's RECORD still claims —
after which `import cv2` fails with an `AttributeError` that says nothing about
packaging. That is why the order above matters: uninstalling headless *after*
contrib is installed reproduces the broken state every time, while removing it
first leaves contrib as the single provider.

**Keep exactly one OpenCV distribution.** MediaPipe depends on
`opencv-contrib-python`, and it installs into the same `cv2/` directory as
`opencv-python-headless`. Whichever is installed last wins, and uninstalling
either one deletes files the survivor's RECORD still claims — after which
`import cv2` fails with an `AttributeError` that says nothing about packaging.
pip does not warn about this. The server prints a warning at start-up when it
finds more than one, and the analysis flow above swaps headless for contrib
rather than stacking them.

OpenCV is pinned below 5 in both files. The 5.x wheels carry neither the Haar
cascade data nor, in the main wheel, the cascade API, so face detection
reported "unavailable" on a clean 5.x install and looked exactly like an empty
room. The cascade itself is vendored in `models/haarcascades/` and preferred
over the copy inside OpenCV, so the detector no longer depends on what cv2
happens to ship in `cv2/data` — but the `CascadeClassifier` API cannot be
vendored, hence the pin.

The model files are **not** inside the built wheel (only `rvm/web` is declared
as package data; a 12 MB download is not something an installer should spring
on someone). A source checkout finds them automatically; a `pip install`
deployment must set `RVM_MODELS_DIR` to the folder holding the `.task` files,
and every analyser reports `unavailable` until it does.

## How it is wired

`StreamSession` runs the analysers on a **cadence**, not on every picture:

```
capture → motion → faces → tracks → [analysis every analysis_interval s] → encode → packetise
```

The reason is arithmetic. Encoding one 320×240 picture costs 34–49 ms on the
demonstration laptop; one analysis pass costs 19–35 ms (measured medians: face
2.4–9.4 ms, expression 2.1–10.3 ms, gesture 14.9–15.1 ms). Running that per
frame would add roughly a third to every picture to refresh a dashboard panel.
At the default 0.5 s cadence it is 4–7 % of the encoder's time instead, and the
panel still updates twice a second.

What the cadence costs, stated plainly: a tick runs **inside** the encode
thread, so the frame it lands on is one frame slower. Measured 160×128: median
frame 30.7 ms → 47.3 ms when a tick is due. End-to-end frame rate therefore
moves a little: 13.25 vs 13.33 fps in one clean run, 9.6 vs 10.4 fps on a
loaded laptop. The per-tick cost is the stable number; the frame rate is not,
because it depends on what else the machine is doing.

Three details that fall out of that choice:

- **Models are loaded in a background thread at start-up.** Creating a
  landmarker reads a multi-megabyte model (about 2 s for the face one). Doing
  that inside the encode loop would hold the first picture of the stream for
  that long, so the stream starts immediately and the analysers join once
  `features()["ready"]` is true.
- **Analysis is off unless the CLI asks for it.** `python run_server.py` turns
  it on; `--no-analysis` turns it off; `StreamSession(analysis=False)` is the
  default so tests and headless runs never pay for models they do not use.
- **Audio is a separate switch.** It is drained from the frame loop regardless
  of the analysis flag, because a microphone that reports "running" while
  never producing an event is worse than no microphone at all.

## API

Every analyser has a read endpoint, and the same data also rides along in the
`/api/status` payload the WebSocket already pushes — the dashboard needs no
second polling loop.

| Method | Path | Returns | State field |
|---|---|---|---|
| `GET` | `/api/features` | which analysers are enabled / ready / available | `enabled`, `ready`, `audio_available` |
| `GET` | `/api/tracks` | `{count, tracks[]}` — id, bbox, centroid, trail | none (tracking has no failure state) |
| `GET` | `/api/faces/identities` | `{count, seen, identities[], state}` | `state` |
| `GET` | `/api/emotions` | `{count, emotions[], state}` | `state` |
| `GET` | `/api/gestures` | `{count, gestures[], state}` | `state` |
| `GET` | `/api/audio/events` | `{count, events[], running}` | `running` (the capture either runs or does not) |
| `POST` | `/api/audio/control` | `{"enabled": true}` starts or stops the microphone | returned `running` / `available` / `reason` |

## Reported states

The state string attached to every analyser result is what keeps six different
situations distinguishable. It lives in `analysis/states.py` so the dashboard,
the payloads and the tests agree on one vocabulary.

| State | Meaning |
|---|---|
| `disabled` | switched off by configuration (`--no-analysis`, or audio before `POST /api/audio/control`) |
| `pending` | switched on, but the models are still loading or no picture has been analysed yet |
| `unavailable` | a dependency or model file is missing; `features()` says which analysers are affected |
| `error` | the analyser ran and failed on this picture |
| `no-faces` / `no-hands` | it ran fine and found nothing |
| `no-known-faces` | faces were found (`seen`) and **no identity has been registered at all**, so there is nothing to compare against. A face that is simply nobody the database knows about is `mediapipe` with an empty list: the recogniser ran, and "no match" is a result |
| `mediapipe` | it ran and produced results |

## Gesture and expression rules

Both classifiers are rule tables over landmarks, not trained models, so their
behaviour is auditable and their cost is bounded.

- **Gestures** — which fingertips sit above their knuckles gives the extended
  fingers; the combination names the pose: open palm, closed fist, pointing,
  peace, thumbs up/down, OK. The thumb folds across the palm rather than down,
  so it is judged by how far its tip reaches from the wrist compared with its
  own joint. A sideways comparison would read a vertical thumbs-up as a fist
  and would invert on a mirrored camera.
- **Expressions** — seven weighted sums over ARKit-style blendshapes (smile +
  cheek squint → happy, brow down + jaw forward + mouth press → angry, and so
  on). A dominant score below 0.15 is reported as a neutral face rather than as
  a weak version of something else.
- **Acoustic events** — loud and bright with a high crossing rate → gunshot;
  bright and noisy at moderate level → glass break; a sustained level across
  five chunks → alarm; otherwise a plain loud sound. Speech must hold for three
  consecutive chunks and then reports at most once every eight chunks (~0.5 s):
  a microphone's noise floor sits in the speech band, so a quiet room produced
  an event every other frame before those two rules. A quiet chunk produces no
  event at all — the removed "ambient" event fired once per chunk and buried the
  events worth seeing.

## Limitations (stated plainly)

- **Face identification has no enrolment path.** There is no camera-side
  "remember this person" flow, so unless `FaceRecognizer.add_known_face()` is
  called from code the honest answer is `no-known-faces` plus a count of faces
  seen. The embedding is the flattened landmark vector compared by Euclidean
  distance, and `confidence = 1 − distance` is a similarity score with an
  arbitrary scale, not a probability — the threshold is a distance cut-off.
- **A face costs two inferences per tick.** `FaceRecognizer` and
  `EmotionRecognizer` each build their own landmarker from the same model file
  (one without blendshapes, one with). Sharing one instance per frame would
  halve that but couples the two modules.
- **Audio is analysed locally and never streamed.** The core stream is video
  only. Audio events describe what the microphone heard; a remote viewer does
  not receive audio.
- **Gesture classification assumes an upright hand.** It is a geometric
  heuristic over 21 landmarks; a rotated hand misreads. The handedness label is
  reported, not compensated.
- **A fist with the thumb tucked flat across the knuckles reads as
  `thumbs_up`.** The thumb test is reach from the wrist, which that pose also
  satisfies. Telling them apart needs palm-relative geometry (where the tip
  lies relative to the four knuckles), which is the next step if the pose
  matters.
- **The first ~2 s of a session report `pending`.** That is the model load, and
  it is deliberately visible instead of being disguised as "off" or "no
  hands".
