#!/usr/bin/env python3
"""
Build EXACT's frozen X-ray reference database from two pinned upstream sources:

1) CXRO/Henke current atomic scattering-factor archive:
   https://henke.lbl.gov/optical_constants/sf.tar.gz

2) XrayDB release 4.5.8 SQLite database (Chantler tables):
   https://raw.githubusercontent.com/xraypy/XrayDB/4.5.8/xraydb.sqlite

The output is an HDF5 file intended to be shipped with EXACT. Runtime use of
EXACT should not require internet access.

The full available source energy ranges are preserved in the HDF5 file.
Any soft-X-ray display or correction-range restriction should be applied later
by EXACT at runtime, not by truncating the source reference data.

Only source tabulations are copied here. Interpolation is deliberately kept
out of the build step so that downstream code can make that policy explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np


CXRO_URL = "https://henke.lbl.gov/optical_constants/sf.tar.gz"
XRAYDB_TAG = "4.5.8"
XRAYDB_URL = (
    f"https://raw.githubusercontent.com/xraypy/XrayDB/{XRAYDB_TAG}/xraydb.sqlite"
)
SCHEMA_VERSION = "1"
BUILDER_VERSION = "0.1"
EXACT_SOFT_XRAY_GUIDE_MAX_EV = 2500.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MAXIV-EXACT-reference-builder/0.1"},
    )
    with urllib.request.urlopen(req, timeout=120) as src, destination.open("wb") as dst:
        while True:
            block = src.read(1024 * 1024)
            if not block:
                break
            dst.write(block)


def ensure_source(
    path: Path | None,
    url: str,
    default_name: str,
    cache_dir: Path,
) -> Path:
    if path is not None:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    target = cache_dir / default_name
    if not target.exists():
        print(f"Downloading {url}")
        download(url, target)
    return target


def parse_henke_archive(path: Path) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}

    with tarfile.open(path, "r:gz") as tf:
        members = [
            m
            for m in tf.getmembers()
            if m.isfile() and m.name.lower().endswith(".nff")
        ]
        if not members:
            raise RuntimeError("No .nff files found in CXRO/Henke archive")

        for member in members:
            symbol = Path(member.name).stem.title()
            fh = tf.extractfile(member)
            if fh is None:
                continue

            raw = fh.read().decode("ascii", errors="strict").strip().splitlines()
            if not raw:
                continue

            rows = []
            for line in raw[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) < 3:
                    continue
                rows.append(
                    (float(parts[0]), float(parts[1]), float(parts[2]))
                )

            arr = np.asarray(rows, dtype=np.float64)
            if arr.ndim != 2 or arr.shape[1] != 3:
                raise RuntimeError(
                    f"Unexpected CXRO table shape for {symbol}: {arr.shape}"
                )
            energy = arr[:, 0]
            diff = np.diff(energy)

            # Preserve the CXRO source table exactly as supplied.  Some
            # experimental-update files contain repeated energies at sharp
            # features and even occasional very small local reversals in the
            # tabulated order.  These are source-data properties, not build
            # errors.  Record them explicitly for provenance and for later
            # interpolation policy, but do not sort, average, or discard them
            # here.
            duplicate_indices = np.where(diff == 0)[0].astype(np.int64)
            decreasing_indices = np.where(diff < 0)[0].astype(np.int64)

            out[symbol] = {
                "energy_eV": energy,
                "f1": arr[:, 1],
                "f2": arr[:, 2],
                "_duplicate_energy_indices": duplicate_indices,
                "_decreasing_energy_indices": decreasing_indices,
            }

    if len(out) != 92:
        raise RuntimeError(
            f"Expected 92 CXRO elements, found {len(out)}"
        )

    return out


def decode_json_array(value, label: str, symbol: str) -> np.ndarray:
    if value is None:
        raise RuntimeError(f"Missing {label} for {symbol}")

    arr = np.asarray(json.loads(value), dtype=np.float64)
    if arr.ndim != 1:
        raise RuntimeError(f"{label} for {symbol} is not 1-D")
    return arr


def read_xraydb(path: Path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"Chantler", "elements", "Version"}
        missing = required - tables
        if missing:
            raise RuntimeError(
                f"XrayDB file is missing tables: {sorted(missing)}"
            )

        element_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(elements)")
        }

        for col in ("atomic_number", "element", "molar_mass", "density"):
            if col not in element_columns:
                raise RuntimeError(
                    f"XrayDB elements table lacks required column {col!r}"
                )

        elements = {}
        for row in conn.execute(
            "SELECT atomic_number, element, molar_mass, density "
            "FROM elements "
            "WHERE atomic_number BETWEEN 1 AND 92 "
            "ORDER BY atomic_number"
        ):
            elements[row["element"]] = {
                "atomic_number": int(row["atomic_number"]),
                "molar_mass": (
                    float(row["molar_mass"])
                    if row["molar_mass"] is not None
                    else np.nan
                ),
                "density_g_cm3": (
                    float(row["density"])
                    if row["density"] is not None
                    else np.nan
                ),
            }

        version_rows = list(
            conn.execute("SELECT * FROM Version ORDER BY id")
        )
        version_info = dict(version_rows[-1]) if version_rows else {}

        chantler = {}

        query = (
            "SELECT element, sigma_mu, mue_f2, density, corr_henke, "
            "corr_cl35, corr_nucl, energy, f1, f2, mu_photo, "
            "mu_incoh, mu_total "
            "FROM Chantler ORDER BY id"
        )

        for row in conn.execute(query):
            symbol = row["element"]
            if symbol not in elements:
                continue

            arrays = {
                "energy_eV": decode_json_array(
                    row["energy"], "energy", symbol
                ),
                "f1": decode_json_array(row["f1"], "f1", symbol),
                "f2": decode_json_array(row["f2"], "f2", symbol),
                "mu_photo_cm2_g": decode_json_array(
                    row["mu_photo"], "mu_photo", symbol
                ),
                "mu_incoh_cm2_g": decode_json_array(
                    row["mu_incoh"], "mu_incoh", symbol
                ),
                "mu_total_cm2_g": decode_json_array(
                    row["mu_total"], "mu_total", symbol
                ),
            }

            n = len(arrays["energy_eV"])

            if n == 0:
                raise RuntimeError(
                    f"Empty Chantler energy grid for {symbol}"
                )

            if any(len(v) != n for v in arrays.values()):
                raise RuntimeError(
                    f"Mismatched Chantler array lengths for {symbol}"
                )

            if np.any(np.diff(arrays["energy_eV"]) <= 0):
                bad = np.where(
                    np.diff(arrays["energy_eV"]) <= 0
                )[0]
                arrays["_nonincreasing_indices"] = bad.astype(np.int64)

            scalars = {}
            for key in (
                "sigma_mu",
                "mue_f2",
                "density",
                "corr_henke",
                "corr_cl35",
                "corr_nucl",
            ):
                value = row[key]
                scalars[key] = (
                    float(value) if value is not None else np.nan
                )

            chantler[symbol] = {
                "arrays": arrays,
                "scalars": scalars,
            }

        if not chantler:
            raise RuntimeError("No Chantler rows found")

        return elements, chantler, version_info

    finally:
        conn.close()


def write_array(
    group: h5py.Group,
    name: str,
    data: np.ndarray,
    *,
    units: str | None = None,
):
    ds = group.create_dataset(
        name,
        data=np.asarray(data, dtype=np.float64),
        compression="gzip",
        compression_opts=6,
        shuffle=True,
    )
    if units:
        ds.attrs["units"] = units
    return ds


def build_h5(
    out_path: Path,
    henke_path: Path,
    xraydb_path: Path,
) -> None:
    henke = parse_henke_archive(henke_path)
    elements, chantler, xraydb_version = read_xraydb(xraydb_path)

    now = datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(out_path, "w") as h5:
        h5.attrs["format_name"] = "EXACT X-ray Reference Database"
        h5.attrs["schema_version"] = SCHEMA_VERSION
        h5.attrs["builder_version"] = BUILDER_VERSION
        h5.attrs["built_utc"] = now
        h5.attrs["purpose"] = (
            "Frozen reference data for EXACT visualization and "
            "future X-ray spectral corrections"
        )
        h5.attrs[
            "exact_soft_xray_guide_max_eV"
        ] = EXACT_SOFT_XRAY_GUIDE_MAX_EV
        h5.attrs["energy_range_policy"] = (
            "Full upstream source ranges are preserved. "
            "The 2500 eV value is a user-interface / intended-use "
            "guide, not a database truncation."
        )
        h5.attrs["source_grid_policy"] = (
            "Raw upstream energy grids are preserved exactly, including "
            "duplicate or locally non-monotonic points. Interpolation-ready "
            "canonicalization is intentionally deferred to the EXACT runtime "
            "reference backend, where the policy can be explicit and tested."
        )

        sources = h5.create_group("sources")

        g = sources.create_group("henke_cxro")
        g.attrs[
            "display_name"
        ] = "CXRO / Henke atomic scattering factors"
        g.attrs["source_url"] = CXRO_URL
        g.attrs["source_sha256"] = sha256_file(henke_path)
        g.attrs["retrieved_or_supplied_utc"] = now
        g.attrs["reference"] = (
            "B. L. Henke, E. M. Gullikson, J. C. Davis, "
            "Atomic Data and Nuclear Data Tables 54 (1993) 181-342, "
            "with later CXRO elemental updates."
        )
        g.attrs["energy_units"] = "eV"
        g.attrs["f1_units"] = "electrons"
        g.attrs["f2_units"] = "electrons"
        g.attrs["note"] = (
            "CXRO uses f1=-9999 as a sentinel below about 29 eV "
            "where f1 is not supplied."
        )

        g = sources.create_group("chantler_xraydb")
        g.attrs[
            "display_name"
        ] = "Chantler tables via XrayDB"
        g.attrs["xraydb_release"] = XRAYDB_TAG
        g.attrs["source_url"] = XRAYDB_URL
        g.attrs["source_sha256"] = sha256_file(xraydb_path)
        g.attrs["retrieved_or_supplied_utc"] = now
        g.attrs[
            "license"
        ] = "XrayDB project data are distributed as Public Domain / CC0"
        g.attrs[
            "reference"
        ] = "Chantler tabulations as packaged by XrayDB"

        if xraydb_version:
            g.attrs["xraydb_version_record_json"] = json.dumps(
                xraydb_version,
                sort_keys=True,
                default=str,
            )

        g.attrs["energy_units"] = "eV"
        g.attrs["f1_units"] = "electrons"
        g.attrs["f2_units"] = "electrons"
        g.attrs["mass_attenuation_units"] = "cm^2/g"
        g.attrs["interpolation_note"] = (
            "The HDF5 stores raw tabulation points only. "
            "XrayDB itself uses a spline for f1 and log-log "
            "interpolation for f2 and attenuation quantities."
        )

        elems = h5.create_group("elements")

        all_symbols = sorted(
            set(henke) | set(chantler),
            key=lambda s: elements.get(
                s, {}
            ).get("atomic_number", 999),
        )

        for symbol in all_symbols:
            eg = elems.create_group(symbol)

            info = elements.get(symbol)
            if info:
                eg.attrs[
                    "atomic_number"
                ] = info["atomic_number"]
                eg.attrs[
                    "molar_mass_g_mol"
                ] = info["molar_mass"]
                eg.attrs[
                    "density_g_cm3"
                ] = info["density_g_cm3"]

            if symbol in henke:
                hg = eg.create_group("henke")
                hg.attrs[
                    "source_ref"
                ] = "/sources/henke_cxro"
                hg.attrs["raw_source_symbol"] = symbol
                hg.attrs["f1_missing_sentinel"] = -9999.0

                write_array(
                    hg,
                    "energy_eV",
                    henke[symbol]["energy_eV"],
                    units="eV",
                )
                write_array(
                    hg,
                    "f1",
                    henke[symbol]["f1"],
                    units="electrons",
                )
                write_array(
                    hg,
                    "f2",
                    henke[symbol]["f2"],
                    units="electrons",
                )

                dup = henke[symbol]["_duplicate_energy_indices"]
                dec = henke[symbol]["_decreasing_energy_indices"]

                if len(dup):
                    hg.create_dataset(
                        "source_duplicate_energy_indices",
                        data=dup,
                    )
                    hg.attrs["duplicate_energy_note"] = (
                        "CXRO source contains repeated energy values. "
                        "Raw source ordering and values are preserved exactly."
                    )

                if len(dec):
                    hg.create_dataset(
                        "source_decreasing_energy_indices",
                        data=dec,
                    )
                    hg.attrs["decreasing_energy_note"] = (
                        "CXRO source contains locally decreasing energy values. "
                        "Raw source ordering and values are preserved exactly; "
                        "no sorting or averaging was applied during database build."
                    )

            if symbol in chantler:
                cg = eg.create_group("chantler")
                cg.attrs[
                    "source_ref"
                ] = "/sources/chantler_xraydb"

                arrays = chantler[symbol]["arrays"]
                scalars = chantler[symbol]["scalars"]

                write_array(
                    cg,
                    "energy_eV",
                    arrays["energy_eV"],
                    units="eV",
                )
                write_array(
                    cg,
                    "f1",
                    arrays["f1"],
                    units="electrons",
                )
                write_array(
                    cg,
                    "f2",
                    arrays["f2"],
                    units="electrons",
                )
                write_array(
                    cg,
                    "mu_photo_cm2_g",
                    arrays["mu_photo_cm2_g"],
                    units="cm^2/g",
                )
                write_array(
                    cg,
                    "mu_incoh_cm2_g",
                    arrays["mu_incoh_cm2_g"],
                    units="cm^2/g",
                )
                write_array(
                    cg,
                    "mu_total_cm2_g",
                    arrays["mu_total_cm2_g"],
                    units="cm^2/g",
                )

                if "_nonincreasing_indices" in arrays:
                    cg.create_dataset(
                        "source_nonincreasing_energy_indices",
                        data=arrays[
                            "_nonincreasing_indices"
                        ],
                    )
                    cg.attrs["energy_grid_note"] = (
                        "Source grid contains repeated/non-increasing "
                        "points; stored exactly as supplied."
                    )

                for key, value in scalars.items():
                    cg.attrs[key] = value

        h5.attrs["element_count"] = len(elems)
        h5.attrs["henke_element_count"] = len(henke)
        h5.attrs[
            "chantler_element_count"
        ] = len(chantler)


def validate_h5(path: Path) -> None:
    with h5py.File(path, "r") as h5:
        if h5.attrs["schema_version"] != SCHEMA_VERSION:
            raise RuntimeError("Unexpected schema version")

        if "elements" not in h5 or "sources" not in h5:
            raise RuntimeError("Required root groups missing")

        if int(h5.attrs["henke_element_count"]) != 92:
            raise RuntimeError("Henke element count is not 92")

        for symbol, eg in h5["elements"].items():
            for source in ("henke", "chantler"):
                if source not in eg:
                    continue

                sg = eg[source]
                n = len(sg["energy_eV"])

                if n < 2:
                    raise RuntimeError(
                        f"Too few points for {symbol}/{source}"
                    )

                if len(sg["f1"]) != n or len(sg["f2"]) != n:
                    raise RuntimeError(
                        f"f1/f2 length mismatch for "
                        f"{symbol}/{source}"
                    )

                if source == "chantler":
                    for name in (
                        "mu_photo_cm2_g",
                        "mu_incoh_cm2_g",
                        "mu_total_cm2_g",
                    ):
                        if len(sg[name]) != n:
                            raise RuntimeError(
                                f"{name} length mismatch "
                                f"for {symbol}"
                            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build EXACT's frozen X-ray reference HDF5 database."
        )
    )

    parser.add_argument(
        "--henke-archive",
        type=Path,
        help=(
            "Existing CXRO sf.tar.gz. "
            "If omitted, download the current CXRO URL."
        ),
    )

    parser.add_argument(
        "--xraydb-sqlite",
        type=Path,
        help=(
            "Existing XrayDB SQLite file. If omitted, download "
            "XrayDB release 4.5.8."
        ),
    )

    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".exact_reference_sources"),
        help="Directory used for downloaded raw sources.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("xray_reference.h5"),
        help="Output HDF5 path.",
    )

    args = parser.parse_args()

    cache = args.cache_dir.expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)

    henke_path = ensure_source(
        args.henke_archive,
        CXRO_URL,
        "cxro_sf_current.tar.gz",
        cache,
    )

    xraydb_path = ensure_source(
        args.xraydb_sqlite,
        XRAYDB_URL,
        f"xraydb-{XRAYDB_TAG}.sqlite",
        cache,
    )

    print(f"CXRO/Henke source: {henke_path}")
    print(f"  SHA-256: {sha256_file(henke_path)}")
    print(f"XrayDB source:     {xraydb_path}")
    print(f"  SHA-256: {sha256_file(xraydb_path)}")

    build_h5(
        args.output,
        henke_path,
        xraydb_path,
    )

    validate_h5(args.output)

    print(
        f"Wrote and validated: "
        f"{args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
