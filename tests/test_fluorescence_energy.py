import h5py
import numpy as np
import pytest
from maxiv_exact.fluorescence_energy import detector_entry_id, match_master, read_energy


def test_realistic_filename():
    assert detector_entry_id('XAS_SH1_spectrum_for_entry5270(2).h5') == '5270'
    assert detector_entry_id('detector.h5') is None


def test_entry_matching_and_fallback(tmp_path):
    master=tmp_path/'master.h5'
    with h5py.File(master,'w') as h:
        for number in (5270,5271):
            g=h.create_group(f'entry{number}')
            g.create_dataset('entry_identifier',data=str(number))
            m=g.create_group('measurement')
            m.create_dataset('pcap_energy_av', data=np.arange(4)+840 if number==5270 else [1,2])
            m.create_dataset('mono_traj_energy',data=np.arange(4)+841)
    got=match_master('spectrum_for_entry5270(2).h5',[str(master)],4)
    assert got.entry == 'entry5270' and got.channel == 'pcap_energy_av'
    assert np.allclose(got.values,[840,841,842,843])
    assert match_master('detector.h5',[str(master)],4) is None
    assert match_master('spectrum_for_entry9999.h5',[str(master)],4) is None
    assert match_master('spectrum_for_entry5271.h5',[str(master)],4).channel=='mono_traj_energy'
    with pytest.raises(ValueError):
        read_energy(str(master),'entry5270',5)
