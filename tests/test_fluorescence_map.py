"""Build 13 standalone FY map/fitter checks (no Qt required)."""
import numpy as np
import h5py
from maxiv_exact.fluorescence_map import (load_fluorescence_map,gaussian_area,
                                          evaluate_model,fit_detector_spectrum,
                                          save_fit_configuration,load_fit_configuration)


def test_map_xspress3_shape(tmp_path):
    p=tmp_path/'example.h5'
    with h5py.File(p,'w') as f:
        f.create_dataset('entry/instrument/xspress3/data',data=np.ones((11,1,512),dtype='uint32'))
    m=load_fluorescence_map(p)
    assert m.counts.shape==(11,512)
    assert m.incident_label=='Incident scan index'
    assert m.incident[0]==0 and m.incident[-1]==10


def test_gaussian_area_and_fit():
    x=np.arange(50.,1050.)
    peaks=[dict(name='O',area=25000.,center=525.,fwhm=95.,free_center=True,free_width=True)]
    y,_=evaluate_model(x,peaks,5.,0.)
    result=fit_detector_spectrum(x,y, [dict(peaks[0],area=20000.,center=520.,fwhm=85.)],3.,0.,linear_background=False)
    assert result['success']
    assert abs(result['peaks'][0]['center']-525.)<.1
    assert abs(result['peaks'][0]['area']-25000.)<30.
    assert abs(result['peaks'][0]['fwhm']-95.)<.1
    assert np.max(np.abs(result['residual']))<.05


def test_fit_config_roundtrip(tmp_path):
    p=tmp_path/'cfg.json'
    peaks=[dict(name='Ni L',center=851.5,area=100.,fwhm=75.,free_center=False,free_width=True)]
    save_fit_configuration(p,peaks,3.,0.)
    obj=load_fit_configuration(p)
    assert obj['peaks']==peaks
