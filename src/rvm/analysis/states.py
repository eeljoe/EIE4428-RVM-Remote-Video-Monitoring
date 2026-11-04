"""The states an optional analyser can report.

One vocabulary for every analyser, because the dashboard, the REST payloads and
the tests all have to agree on what "nothing to report" means.  The point of
six strings instead of a boolean is that they are six different situations:

``disabled``
    switched off by configuration; nothing was attempted.
``pending``
    switched on, but the models are still loading or no picture has been
    analysed yet.  Without this state "switched off" and "not started yet"
    would render identically, which is exactly the confusion the vocabulary
    exists to prevent.
``unavailable``
    a dependency or a model file is missing.
``error``
    the analyser ran and failed on this picture.
``no-faces`` / ``no-hands`` / ``no-known-faces``
    it ran fine and had nothing to report: an empty scene, or faces seen while
    no identity has been registered at all.  A face that matches nobody in a
    populated database is ``mediapipe`` with an empty list -- the recogniser
    ran, and "no match" is a result rather than an absence.
``mediapipe``
    it ran and produced results.
"""

from __future__ import annotations

__all__ = [
    "STATE_DISABLED",
    "STATE_PENDING",
    "STATE_UNAVAILABLE",
    "STATE_ERROR",
    "STATE_NO_FACES",
    "STATE_NO_HANDS",
    "STATE_NO_KNOWN",
    "STATE_RUNNING",
]

STATE_DISABLED = "disabled"
STATE_PENDING = "pending"
STATE_UNAVAILABLE = "unavailable"
STATE_ERROR = "error"
STATE_NO_FACES = "no-faces"
STATE_NO_HANDS = "no-hands"
STATE_NO_KNOWN = "no-known-faces"
STATE_RUNNING = "mediapipe"
