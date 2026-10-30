"""Numerical regression tests for build 15 fluorescence-map extraction."""
import numpy as np
from maxiv_exact.fluorescence_map import (
    gaussian_area, fit_fluorescence_batch, extract_fitted_fy, reconstruct_component,
    evaluate_model,
)


def test_fy_export_uses_actual_bin_count_including_partial_last_bin():
    x=np.linspace(400,900,260)
    p=dict(id='P1',name='O Kα',center=525.,fwhm=120.,area=800.,free_center=False,free_width=False)
    data=np.stack([gaussian_area(x,400.+i*20.,525.,120.)+2. for i in range(5)])
    result=fit_fluorescence_batch(data,x,[p],bin_size=2)
    incident=np.linspace(840,890,5)
    mid,area,err=extract_fitted_fy(result,incident)
    np.testing.assert_allclose(mid,[846.25,871.25,890.])
    np.testing.assert_allclose(area[:,0],[410,450,480],atol=.5)
    assert np.isfinite(err).all()
    assert list(result['bin_counts'])==[2,2,1]


def test_component_map_excludes_background_and_other_peaks():
    x=np.linspace(300,1000,350)
    peaks=[dict(id=f'P{i}',name=f'Peak{i}',center=c,fwhm=100.,area=1000.,free_center=False,free_width=False)
           for i,c in enumerate([525.,850.],1)]
    data=np.stack([gaussian_area(x,300,525,100)+gaussian_area(x,500,850,100)+3. for _ in range(3)])
    result=fit_fluorescence_batch(data,x,peaks,fit_slice=(10,340))
    first=reconstruct_component(result,x,0)
    second=reconstruct_component(result,x,1)
    assert np.isnan(first[:,0]).all()
    fit,_=evaluate_model(x[10:340], [dict(peaks[j],area=result['areas'][0,j]) for j in range(2)], *result['background'][0])
    np.testing.assert_allclose(first[0,10:340]+second[0,10:340]+result['background'][0,0],fit,rtol=1e-7,atol=1e-7)
