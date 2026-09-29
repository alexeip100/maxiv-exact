"""Standalone HDF5 metadata scanner used by the GUI via QProcess.

This module deliberately imports no Qt code. Each HDF5 file is opened and
closed entirely inside this helper process so slow/network HDF5 access cannot
block the application's GUI event loop.
"""
from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

import h5py


def _emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _open_h5_read(path, retries: int = 3):
    last_error = None
    for i in range(max(1, int(retries))):
        try:
            return h5py.File(path, "r", swmr=True, libver="latest", locking=False)
        except TypeError:
            return h5py.File(path, "r")
        except OSError as exc:
            last_error = exc
            time.sleep(0.05 * (i + 1))
        except Exception as exc:
            last_error = exc
            time.sleep(0.05 * (i + 1))
    try:
        return h5py.File(path, "r", locking=False)
    except Exception as exc:
        raise last_error or exc


def scan_file(abs_path):
    abs_path = os.path.abspath(str(abs_path))
    root_children = []
    norm_channels = []
    all_channels = set()
    with _open_h5_read(abs_path) as f:
        for name in f.keys():
            obj = f[name]
            kind = "other"
            has_children = False
            is_1d_dataset = False
            if isinstance(obj, h5py.Group):
                kind = "group"
                try:
                    has_children = bool(len(obj.keys()))
                except Exception:
                    has_children = False
            elif isinstance(obj, h5py.Dataset):
                kind = "dataset"
                is_1d_dataset = (obj.ndim == 1)
            root_children.append({
                "name": str(name),
                "path": str(name),
                "kind": kind,
                "has_children": bool(has_children),
                "is_1d_dataset": bool(is_1d_dataset),
            })

        for key in f.keys():
            try:
                entry = f[key]
                if isinstance(entry, h5py.Group) and "measurement" in entry:
                    meas_group = entry["measurement"]
                    for ds_name, ds_obj in meas_group.items():
                        if isinstance(ds_obj, h5py.Dataset) and ds_obj.ndim == 1:
                            norm_channels.append(str(ds_name))
                    break
            except Exception:
                continue

        # The GUI's "All in channel" combobox needs the names of every 1-D
        # dataset in the file.  This recursive traversal can be expensive on
        # large/network files, so it must happen here rather than later in the
        # Qt GUI thread.
        def _visit(name, obj):
            try:
                if isinstance(obj, h5py.Dataset):
                    shape = tuple(getattr(obj, "shape", ()) or ())
                    if len(shape) == 1 and getattr(obj, "size", 0) > 0:
                        channel = str(name).lstrip("/").split("/")[-1]
                        if channel:
                            all_channels.add(channel)
            except Exception:
                pass

        try:
            f.visititems(_visit)
        except Exception:
            pass

    return {
        "abs_path": abs_path,
        "root_children": root_children,
        "norm_channels": norm_channels,
        "all_channels": sorted(all_channels, key=str.lower),
    }


def main(argv=None):
    paths = list(sys.argv[1:] if argv is None else argv)
    for path in paths:
        abs_path = os.path.abspath(str(path))
        _emit({"type": "progress", "message": f"Loading {os.path.basename(abs_path)}..."})
        try:
            payload = scan_file(abs_path)
        except Exception as exc:
            _emit({"type": "file_failed", "path": abs_path, "message": str(exc)})
            continue
        _emit({"type": "file_ready", "payload": payload})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
