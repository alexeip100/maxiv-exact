from pathlib import Path

from maxiv_exact import hdf5_loading as h5load


def test_supported_hdf5_extensions_are_case_insensitive():
    assert h5load.is_supported_hdf5_extension("scan.h5")
    assert h5load.is_supported_hdf5_extension("scan.HDF5")
    assert not h5load.is_supported_hdf5_extension("notes.txt")


def test_normalize_hdf5_path_extracts_tree_payload_hdf5_part():
    payload = ("/tmp/acquisition/scan001.h5", "entry0001/measurement/tey")
    assert h5load.normalize_hdf5_path(payload) == "entry0001/measurement/tey"


def test_normalize_hdf5_path_handles_nested_tree_payloads():
    nested = ("/tmp/acquisition/scan001.h5", ("/tmp/acquisition/scan001.h5", "entry0002/measurement/I0"))
    assert h5load.normalize_hdf5_path(nested) == "entry0002/measurement/I0"


def test_make_and_split_tree_payload_are_canonical(tmp_path: Path):
    file_path = tmp_path / "scan001.h5"
    payload = h5load.make_tree_payload(file_path, "/entry0003/measurement/tey/")
    split = h5load.split_tree_payload(payload)
    assert split is not None
    assert split[0] == str(file_path.resolve())
    assert split[1] == "/entry0003/measurement/tey/"


def test_split_supported_hdf5_paths_filters_invalid_and_duplicate_names(tmp_path: Path):
    first = tmp_path / "scan001.h5"
    second = tmp_path / "scan002.hdf5"
    duplicate_dir = tmp_path / "copy"
    duplicate_dir.mkdir()
    duplicate = duplicate_dir / "scan001.h5"
    invalid = tmp_path / "notes.txt"
    for p in (first, second, duplicate, invalid):
        p.write_text("dummy", encoding="utf-8")

    valid, skipped = h5load.split_supported_hdf5_paths([first, invalid, second, duplicate])

    assert valid == [str(first.resolve()), str(second.resolve())]
    assert "notes.txt" in skipped
    assert "scan001.h5 (duplicate in selected files)" in skipped
