import numpy as np
import pytest
from maxiv_exact.fluorescence_map import gaussian_area,fit_detector_spectrum,fit_fluorescence_batch


def test_soft_width_penalty_has_flat_bottom_and_is_finite():
    x=np.linspace(0,300,301)
    data=gaussian_area(x,3000,130,60)+1
    peak=dict(name='P1',area=3000,center=130,fwhm=100,free_center=False,free_width=True)
    result=fit_detector_spectrum(x,data,[peak],width_soft_limits=(80,160),width_softness=40)
    assert result['success']
    assert result['peaks'][0]['fwhm'] < 80 # sufficient data wins over penalty
    assert result['width_penalty'] > 0
    fixed=fit_detector_spectrum(x,data,[dict(peak,free_width=False,fwhm=60)])
    assert fixed['width_penalty']==0


def test_batch_soft_penalty_accepts_electron_volt_settings():
    x=np.linspace(0,300,160)
    peak=dict(name='P1',area=1000,center=150,fwhm=105,free_center=False,free_width=True)
    data=np.stack([gaussian_area(x,2000,150,115)+2]*2)
    result=fit_fluorescence_batch(data,x,[peak],width_soft_limits=(80,160),width_softness=40)
    assert result['success'].all()
    assert np.allclose(result['widths'],115,atol=2)


def test_invalid_soft_limits_rejected():
    x=np.arange(60,dtype=float)
    p=dict(name='P1',area=100,center=25,fwhm=10,free_center=False,free_width=True)
    with pytest.raises(ValueError,match='soft limits'):
        fit_detector_spectrum(x,np.ones(60),[p],width_soft_limits=(160,80))
