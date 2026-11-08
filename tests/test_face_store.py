"""The known-face registry: load, save, add, remove, and how it degrades.

These tests are about the file, not about faces: a registry that survives a
corrupt write, a missing file and a failed save is what makes "register once
during the demo rehearsal" safe.  Expected values are hand-written literals
(``[1.0, 2.0]``), never recomputed with the same code the store uses.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from rvm.analysis.face_store import (
    DEFAULT_KNOWN_FACES,
    FaceStore,
    FaceStoreError,
)

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
# Where it lives
# --------------------------------------------------------------------------


def test_the_default_path_is_the_project_data_directory():
    assert DEFAULT_KNOWN_FACES == Path("data") / "known_faces.json"


def test_the_default_list_is_ignored_by_git():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "data/known_faces.json" in [line.strip() for line in ignored]
