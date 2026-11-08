"""The known-face registry: load, save, add, remove, and how it degrades.

These tests are about the file, not about faces: a registry that survives a
corrupt write, a missing file and a failed save is what makes "register once
during the demo rehearsal" safe.  Expected values are hand-written literals
(``[1.0, 2.0]``), never recomputed with the same code the store uses.

The last section is the one part of the registry the file cannot show on its
own: two requests changing the list at once.  A deletion copies the list,
removes a name and writes it back, so a registration that commits between the
copy and the write-back is erased by a list that never heard of it.  Those
tests drive ``StreamSession`` -- the only caller that mutates the list -- with
a real thread and a real lock, and force the interleaving rather than hope for
it.
"""

import json
import threading
from pathlib import Path

import numpy as np
import pytest

from rvm.analysis.face_store import (
    DEFAULT_KNOWN_FACES,
    FaceStore,
    FaceStoreError,
)
from rvm.server.session import StreamSession

REPO_ROOT = Path(__file__).resolve().parent.parent


def write_list(path: Path, faces: dict, version: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "faces": faces}), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def test_a_missing_file_loads_as_an_empty_list_and_is_not_created(tmp_path, caplog):
    path = tmp_path / "data" / "known_faces.json"
    store = FaceStore(path)

    assert store.load() == {}
    assert store.names() == []
    assert not path.exists(), "loading must not write anything"


def test_a_saved_list_is_loaded_back_exactly(tmp_path):
    path = tmp_path / "known_faces.json"
    write_list(path, {"Alice Ng": [1.0, 2.0, 3.0]})

    faces = FaceStore(path).load()

    assert list(faces) == ["Alice Ng"]
    assert faces["Alice Ng"].tolist() == [1.0, 2.0, 3.0]


def test_a_corrupt_file_is_reported_and_the_list_starts_empty(tmp_path, caplog):
    path = tmp_path / "known_faces.json"
    path.write_text("{not json at all", encoding="utf-8")

    with caplog.at_level("WARNING", logger="rvm.analysis.face_store"):
        faces = FaceStore(path).load()

    assert faces == {}
    assert any("corrupt" in record.message for record in caplog.records)


def test_a_file_with_the_wrong_shape_is_treated_as_corrupt(tmp_path, caplog):
    path = tmp_path / "known_faces.json"
    path.write_text(json.dumps({"version": 1, "faces": {"Alice": "not a vector"}}), encoding="utf-8")

    with caplog.at_level("WARNING", logger="rvm.analysis.face_store"):
        faces = FaceStore(path).load()

    assert faces == {}
    assert any("corrupt" in record.message for record in caplog.records)


def test_vectors_of_different_lengths_are_treated_as_corrupt(tmp_path, caplog):
    """Two widths mean two incompatible registries, not a list of faces.

    One landmarker produced every vector of a list, so they are all the same
    length.  A file where they are not is a hand edit or a leftover from an
    older model, and comparing those vectors raises instead of mismatching --
    inside the analysis tick, which kills the picture pump.  Refusing the file
    at load time keeps that arithmetic out of the encode thread.
    """
    path = tmp_path / "known_faces.json"
    write_list(path, {"Alice": [1.0, 2.0], "Bob": [1.0, 2.0, 3.0]})

    with caplog.at_level("WARNING", logger="rvm.analysis.face_store"):
        faces = FaceStore(path).load()

    assert faces == {}
    assert any("corrupt" in record.message for record in caplog.records)


def test_a_list_of_one_width_still_loads(tmp_path):
    """The width check must not reject a perfectly ordinary list."""
    path = tmp_path / "known_faces.json"
    write_list(path, {"Alice": [1.0, 2.0, 3.0], "Bob": [4.0, 5.0, 6.0]})

    faces = FaceStore(path).load()

    assert faces["Alice"].tolist() == [1.0, 2.0, 3.0]
    assert faces["Bob"].tolist() == [4.0, 5.0, 6.0]


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------


def test_a_save_writes_names_and_vectors_and_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "data" / "known_faces.json"
    store = FaceStore(path)
    store.add("Alice Ng", np.array([0.5, -0.25]))

    store.save()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["faces"] == {"Alice Ng": [0.5, -0.25]}
    assert sorted(entry.name for entry in path.parent.iterdir()) == ["known_faces.json"]


def test_a_save_replaces_the_previous_list_whole(tmp_path):
    path = tmp_path / "known_faces.json"
    write_list(path, {"Old": [9.0]})
    store = FaceStore(path)
    store.load()
    store.remove("Old")
    store.add("New", [1.0])

    store.save()

    assert json.loads(path.read_text(encoding="utf-8"))["faces"] == {"New": [1.0]}


def test_a_failed_save_raises_and_keeps_the_previous_file(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("this is a file, not a directory", encoding="utf-8")
    store = FaceStore(blocker / "known_faces.json")
    store.add("Alice", [1.0])

    with pytest.raises(FaceStoreError):
        store.save()

    assert blocker.is_file()
    assert blocker.read_text(encoding="utf-8") == "this is a file, not a directory"


# --------------------------------------------------------------------------
# Changes are replacements, not edits
# --------------------------------------------------------------------------


def test_adding_a_face_replaces_the_mapping_instead_of_mutating_it(tmp_path):
    store = FaceStore(tmp_path / "known_faces.json")
    store.add("Alice", [1.0])
    held = store.faces

    store.add("Bob", [2.0])

    assert held is not store.faces, "the old mapping must be left untouched"
    assert list(held) == ["Alice"]
    assert store.names() == ["Alice", "Bob"]


def test_removing_a_face_replaces_the_mapping_instead_of_mutating_it(tmp_path):
    store = FaceStore(tmp_path / "known_faces.json")
    store.add("Alice", [1.0])
    held = store.faces

    assert store.remove("Alice") is True
    assert store.remove("Alice") is False

    assert held is not store.faces
    assert list(held) == ["Alice"]
    assert store.names() == []


def test_names_are_sorted_so_responses_and_files_agree(tmp_path):
    store = FaceStore(tmp_path / "known_faces.json")
    for name in ("Zoe", "alice", "Bob"):
        store.add(name, [1.0])

    assert store.names() == ["Bob", "Zoe", "alice"]


# --------------------------------------------------------------------------
# Changes that race with each other
# --------------------------------------------------------------------------

#: Brightness of the three analysed frames a registration averages over:
#: (10 + 20 + 30) / 3 = 20.0 is the embedding every seeded face gets.
SAMPLES = (10, 20, 30)


def make_session(tmp_path) -> StreamSession:
    """A session whose registration and removal run for real, without models.

    ``sample_faces`` is the only MediaPipe call a registration makes; standing
    it in keeps everything else -- the name check, the mean, the store, the
    file, the recogniser mirror -- running for real, and makes the stored
    vector a hand-computable 20.0 instead of 1400 landmarks.
    """
    session = StreamSession(
        width=64,
        height=48,
        fps=10.0,
        bitrate=200_000,
        record_dir=tmp_path / "clips",
        analysis=False,
        analysis_interval=0.0,
        known_faces=tmp_path / "data" / "known_faces.json",
    )
    session.analysis_enabled = True
    session._models_ready.set()
    session.face_recognizer.sample_faces = lambda frame: [
        np.array([float(frame[0, 0, 0])])
    ]
    # The three frames the next registration would average; ``run_once`` would
    # need the Haar detector to produce them and this is the same buffer.
    session._recent_frames = [
        np.full((48, 64, 3), value, dtype=np.uint8) for value in SAMPLES
    ]
    return session


class ObservedLock:
    """The list lock, plus a signal for "another thread is about to wait".

    The lost update this ticket fixes exists only in one interleaving: the
    removal copies the list, another request publishes, the removal writes its
    stale copy back.  Nothing outside the lock distinguishes that order from
    the correct one, so a test that forced it with a sleep would be guessing.
    The one point on the path that is outside the critical section in the
    broken version and inside it in the fixed one is the moment a thread asks
    for the lock, so the gate sits there: this is the same re-entrant lock,
    and it releases ``waiting`` when a thread that does not already hold it is
    about to block.  The test holds the lock, waits for that release (a real
    thread blocked on a real lock, not a pause), publishes its own change, and
    lets the waiter in.  Whether the copy happened before or after that moment
    is exactly what the lock is supposed to decide.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._owner: int | None = None
        self._depth = 0
        self.waiting = threading.Semaphore(0)

    def __enter__(self) -> "ObservedLock":
        me = threading.get_ident()
        if self._owner != me:
            self.waiting.release()
        self._lock.acquire()
        self._depth += 1
        self._owner = me
        return self

    def __exit__(self, *exc_info) -> bool:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
        self._lock.release()
        return False


@pytest.fixture
def session(tmp_path):
    built = make_session(tmp_path)
    yield built
    built.close()


def stored(tmp_path) -> dict:
    """The list as the file has it, so "persisted" is checked, not assumed."""
    path = tmp_path / "data" / "known_faces.json"
    return json.loads(path.read_text(encoding="utf-8"))["faces"]


def test_a_registration_that_lands_during_a_removal_is_not_lost(session, tmp_path):
    """The 02 r2 gate's lost update: a 201 that a concurrent delete erases.

    Alice and Bob are registered.  A thread calls ``remove_face("Bob")`` and is
    parked at the list lock, which the test holds.  The test then publishes
    Carol exactly as a registration's critical section does, and lets the
    removal finish.  When the removal copies the list *outside* the lock, it
    copies it before Carol exists and writes that stale copy back afterwards:
    Carol is gone from the store, the file and the recogniser mirror even
    though its registration was answered.  With the copy inside the lock the
    removal cannot read until Carol is published, so both changes survive.
    """
    session.register_face("Alice")
    session.register_face("Bob")
    assert session.known_face_names() == ["Alice", "Bob"]

    lock = ObservedLock()
    session._faces_lock = lock
    outcome = {}

    def remove_bob() -> None:
        outcome["body"] = session.remove_face("Bob")

    with lock:
        remover = threading.Thread(target=remove_bob, daemon=True)
        remover.start()
        assert lock.waiting.acquire(timeout=5), "the removal never asked for the lock"
        faces = dict(session.face_store.faces)
        faces["Carol"] = np.array([7.0])
        session._publish_faces(faces)
    remover.join(timeout=5)

    assert not remover.is_alive()
    assert outcome["body"]["removed"] is True
    # Hand-written expectations: Bob was deleted, Carol was registered.
    assert session.known_face_names() == ["Alice", "Carol"]
    assert set(session.face_recognizer.known_faces) == {"Alice", "Carol"}
    assert stored(tmp_path) == {"Alice": [20.0], "Carol": [7.0]}


def test_two_removals_of_different_names_both_take_effect(session, tmp_path):
    """Two operators deleting two people must not resurrect one of them.

    Same interleaving as above, with a second removal in the middle: Bob's
    removal copies the list, Carol's removal commits, Bob's stale copy is
    written back and Carol reappears in the list she was deleted from.
    """
    for name in ("Alice", "Bob", "Carol"):
        session.register_face(name)

    lock = ObservedLock()
    session._faces_lock = lock
    outcome = {}

    def remove_bob() -> None:
        outcome["body"] = session.remove_face("Bob")

    with lock:
        remover = threading.Thread(target=remove_bob, daemon=True)
        remover.start()
        assert lock.waiting.acquire(timeout=5), "the removal never asked for the lock"
        session.remove_face("Carol")
    remover.join(timeout=5)

    assert not remover.is_alive()
    assert outcome["body"]["removed"] is True
    assert session.known_face_names() == ["Alice"]
    assert set(session.face_recognizer.known_faces) == {"Alice"}
    assert stored(tmp_path) == {"Alice": [20.0]}


# --------------------------------------------------------------------------
# Where it lives
# --------------------------------------------------------------------------


def test_the_default_path_is_the_project_data_directory():
    assert DEFAULT_KNOWN_FACES == Path("data") / "known_faces.json"


def test_the_default_list_is_ignored_by_git():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "data/known_faces.json" in [line.strip() for line in ignored]
