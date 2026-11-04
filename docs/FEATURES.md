# Optional analysis modules

Four analysers sit on top of the monitoring pipeline described in the README.
None of them is required to stream; each one reports itself **unavailable**
instead of failing when a dependency or a model file is missing, and the
dashboard shows the difference between "switched off", "unavailable" and
"working on an empty scene".

| Module | File | Backend | Depends on |
|---|---|---|---|
| Object tracking | `analysis/track.py` | connected regions + nearest-centroid matching | nothing |
| Face identification | `analysis/recognition.py` → `FaceRecognizer` | MediaPipe FaceLandmarker landmarks | `mediapipe` + `models/face_landmarker.task` |
| Expression classification | `analysis/recognition.py` → `EmotionRecognizer` | MediaPipe FaceLandmarker blendshapes | same model |
| Hand gestures | `analysis/gesture.py` | MediaPipe HandLandmarker | `mediapipe` + `models/hand_landmarker.task` |
| Acoustic events | `audio/` | RMS / zero-crossing rate / spectral centroid | `pyaudio` + a microphone |

## Installing the analysers

```powershell
pip install -r requirements.txt          # includes the optional extras
# or, if the package was installed editable:
pip install -e ".[analysis]"
```

OpenCV is pinned below 5 in both the base requirements and the analysis extra.
The 5.x wheels dropped the Haar cascade API and the cascade data, which is what
the core face detector runs on: on a clean 5.x install, face detection reported
"unavailable" and looked exactly like an empty room. The cascade itself is also
shipped in this repository (`models/haarcascades/`) and preferred over the copy
inside OpenCV, so installing a different OpenCV build cannot change what the
detector does.

## How it is wired

`StreamSession` runs the analysers on a **cadence**, not on every picture:

```
capture → motion → faces → tracks → [analysis every analysis_interval s] → encode → packetise
```

The reason is arithmetic. Encoding a 320×240 picture costs a few milliseconds;
one FaceLandmarker call costs 7–50 ms. Running recognition per frame would cut
the stream's frame rate by more than half to refresh a dashboard panel. At the
default 0.5 s cadence the stream keeps its frame rate and the panel still
updates twice a second.

Two details that fall out of that choice:

- **Models are loaded in a background thread at start-up.** Creating a
  landmarker reads a multi-megabyte model (about 2 s for the face one). Doing
  that inside the encode loop would hold the first picture of the stream for
  that long, so the stream starts immediately and the analysers join once
  `features()["ready"]` is true.
- **Analysis is off unless the CLI asks for it.** `python run_server.py` turns
  it on; `--no-analysis` turns it off; `StreamSession(analysis=False)` is the
  default so tests and headless runs never pay for models they do not use.

Measured on the demonstration machine at 320×240, webcam-free synthetic scene:

| Configuration | Frame rate |
|---|---|
| `--no-analysis` | 11.3 fps |
| analysis on (face + expression + gesture) | 10.0 fps |

## API

Every analyser has a read endpoint, and the same data also rides along in the
`/api/status` payload the WebSocket already pushes — the dashboard needs no
second polling loop.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/features` | which analysers are enabled / ready / available |
| `GET` | `/api/tracks` | `{count, tracks[]}` — id, bbox, centroid, trail |
| `GET` | `/api/faces/identities` | `{count, identities[], recognizer}` |
| `GET` | `/api/emotions` | `{count, emotions[], detector}` |
| `GET` | `/api/gestures` | `{count, gestures[], detector}` |
| `GET` | `/api/audio/events` | `{count, events[], running}` |
| `POST` | `/api/audio/control` | `{"enabled": true}` starts or stops the microphone |

## Reported states

The state string attached to every result is what keeps three different
situations distinguishable:

| State | Meaning |
|---|---|
| `disabled` | the analyser is switched off (`--no-analysis`, or audio before `POST /api/audio/control`) |
| `unavailable` | a dependency or model file is missing; `features()` names why |
| `error` | the analyser ran and failed on this frame |
| `no-faces` / `no-hands` | it ran fine and found nothing |
| `no-known-faces` | faces were found, but no face has been registered to compare against |
| `mediapipe` | it ran and produced results |

## Gesture and expression rules

Both classifiers are rule tables over landmarks, not trained models, so their
behaviour is auditable and their cost is bounded.

- **Gestures** — which fingertips sit above their knuckles gives the extended
  fingers; the combination names the pose: open palm, closed fist, pointing,
  peace, thumbs up/down, OK. The thumb is the one finger tested sideways, which
  is why thumb poses must be checked *before* "no long finger extended" — that
  test is exactly a fist, and ordering it first makes thumbs-up unreachable.
- **Expressions** — seven weighted sums over ARKit-style blendshapes (smile +
  cheek squint → happy, brow down + jaw forward + mouth press → angry, and so
  on). A dominant score below 0.15 is reported as a neutral face rather than as
  a weak version of something else.
- **Acoustic events** — loud and bright with a very short burst → gunshot;
  bright with high zero-crossing rate → glass break; a sustained level across
  five chunks → alarm; otherwise a plain loud sound. Moderate energy with a
  high crossing rate reads as speech. A quiet chunk produces **no event**;
  reporting an "ambient" event per chunk floods the list at 15 chunks a second
  and hides the events worth seeing.

## Limitations (stated plainly)

- **Face identification has no enrolment path.** There is no camera-side
  "remember this person" flow, so unless `FaceRecognizer.add_known_face()` is
  called from code the honest answer is `no-known-faces`. The embedding is the
  flattened landmark vector compared by Euclidean distance, which is
  serviceable for a demo and is not a face-recognition model.
- **Audio is analysed locally and never streamed.** The core stream is video
  only. Audio events describe what the microphone heard; a remote viewer does
  not receive audio.
- **One face model instance per recogniser.** `FaceRecognizer` and
  `EmotionRecognizer` each construct a FaceLandmarker, so a face costs two
  inferences per analysis tick. Sharing one instance per frame would halve that
  but couples the two modules; the cadence keeps the cost acceptable instead.
- **Gesture classification is a geometric heuristic.** It assumes an upright
  hand; a rotated hand misreads, and a raised thumb on a mirrored selfie camera
  can invert. The landmarker's handedness label is reported, not compensated.
