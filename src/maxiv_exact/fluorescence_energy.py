"""Incident-energy association for fluorescence maps; no Qt dependencies."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import h5py
import numpy as np

@dataclass
class EnergyAssociation:
    values: np.ndarray
    master_file: str
    entry: str
    channel: str


def detector_entry_id(path):
    match = re.search(r"(?:^|[_\-])entry(\d+)(?=$|[^0-9])", Path(path).stem, re.I)
    return match.group(1) if match else None


def available_entries(path):
    with h5py.File(path, 'r') as h:
        return [key for key in h if isinstance(h[key], h5py.Group) and key.lower().startswith('entry')]


def read_energy(path, entry, count, channel=None):
    with h5py.File(path, 'r') as h:
        if entry not in h or not isinstance(h[entry], h5py.Group):
            raise ValueError(f'Master entry {entry} not found.')
        group=h[entry]
        if 'entry_identifier' in group:
            ident=group['entry_identifier'][()]
            ident=ident.decode(errors='replace') if isinstance(ident, bytes) else str(ident)
            suffix=re.search(r'(\d+)$',entry)
            if suffix and ident.strip()!=suffix.group(1):
                raise ValueError(f'Master entry identifier {ident!r} disagrees with {entry}.')
        channels=(channel,) if channel else ('pcap_energy_av','mono_traj_energy')
        for name in channels:
            key=f'measurement/{name}'
            if key not in group:continue
            values=np.asarray(group[key][...],dtype=float).ravel()
            if values.size==count and np.isfinite(values).all() and np.all(np.diff(values)>0):
                return EnergyAssociation(values,str(Path(path).resolve()),entry,name)
    raise ValueError(f'No valid increasing incident-energy array with {count} points in {entry}.')


def match_master(detector_path, master_paths, count, selected=None):
    """Automatic match only with explicit filename entry ID; no length-only guess."""
    ident=detector_entry_id(detector_path)
    if ident is None:return None
    candidates=[]
    for path in master_paths:
        try:
            for entry in available_entries(path):
                if entry.lower()==f'entry{ident}'.lower():
                    candidates.append((path,entry))
        except (OSError,ValueError):continue
    if len(candidates)!=1:return None
    path,entry=candidates[0]
    try:return read_energy(path,entry,count)
    except (ValueError,OSError,KeyError):return None
