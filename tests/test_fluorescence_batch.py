import numpy as np
from maxiv_exact.fluorescence_map import gaussian_area,fit_fluorescence_batch


def test_batch_independent_areas_and_labels():
    x=np.arange(180,dtype=float)
    peaks=[dict(id='P1',name='first',center=40.,fwhm=16.,area=1000.,free_center=False,free_width=False),
           dict(id='P2',name='second',center=110.,fwhm=20.,area=500.,free_center=False,free_width=False)]
    data=np.array([gaussian_area(x,400+20*i,40,16)+gaussian_area(x,200+5*i,110,20)+2
                   for i in range(12)])
    out=fit_fluorescence_batch(data,x,peaks,fit_slice=(0,180))
    assert out['success'].all()
    np.testing.assert_allclose(out['areas'][:,0],400+20*np.arange(12),atol=.3)
    np.testing.assert_allclose(out['areas'][:,1],200+5*np.arange(12),atol=.3)
    assert out['peaks'][0]['name']=='first'


def test_batch_sums_partial_last_bin():
    x=np.arange(140,dtype=float)
    peaks=[dict(id='P1',name='P1',center=60.,fwhm=19.,area=500.,free_center=False,free_width=False)]
    data=np.array([gaussian_area(x,300,60,19)+1 for _ in range(11)])
    out=fit_fluorescence_batch(data,x,peaks,bin_size=4)
    assert list(out['bin_counts'])==[4,4,3]
    assert len(out['areas'])==3
    np.testing.assert_allclose(out['areas'][:,0],[1200,1200,900],atol=.3)


def test_batch_refinement_is_bounded():
    x=np.arange(130,dtype=float)
    peak=dict(id='P1',name='P1',center=58.,fwhm=18.,area=500.,free_center=True,free_width=True)
    data=np.array([gaussian_area(x,450,61,20)+2 for _ in range(3)])
    out=fit_fluorescence_batch(data,x,[peak],refine_shapes=True,center_tolerance=5,width_fraction=.2)
    assert out['success'].all()
    np.testing.assert_allclose(out['centers'][:,0],61.,atol=.5)


def test_pass1_retained_when_refinement_enabled():
    import numpy as np
    x=np.linspace(300,1000,180)
    peaks=[dict(id='P1',name='A',center=525.,fwhm=85.,area=900.,free_center=True,free_width=True)]
    data=np.stack([gaussian_area(x,a,527.,88.)+3. for a in [500.,850.,1000.,700.]])
    out=fit_fluorescence_batch(data,x,peaks,refine_shapes=True,center_tolerance=4.,width_fraction=.1)
    assert out['pass1']['areas'].shape==(4,1)
    assert out['pass1']['success'].all()
    assert np.allclose(out['pass1']['centers'],527.,atol=.5)
    assert np.isfinite(out['pass1']['deviance']).all()
    assert out['center_tolerance']==4.
    assert out['width_fraction']==.1


def test_fixed_pass_retained_for_map_reconstruction():
    import numpy as np
    from maxiv_exact.fluorescence_map import evaluate_model
    x=np.linspace(400,900,180)
    peaks=[dict(id='P1',name='O',center=525.,fwhm=80.,area=500.,free_center=False,free_width=False)]
    data=np.stack([gaussian_area(x,a,525.,80.)+1. for a in [200.,300.,400.,500.,600.]])
    out=fit_fluorescence_batch(data,x,peaks,bin_size=2,refine_shapes=True)
    assert out['pass1']['areas'].shape==(3,1)
    for i in range(3):
        pp=[dict(peaks[0],area=out['pass1']['areas'][i,0],center=out['pass1']['centers'][i,0],fwhm=out['pass1']['widths'][i,0])]
        fit,_=evaluate_model(x,pp,*out['pass1']['background'][i])
        assert fit.shape==x.shape
        assert np.all(np.isfinite(fit))


def test_trend_constrained_second_pass_preserves_free_areas():
    from maxiv_exact.fluorescence_map import fit_polynomial_trend
    x=np.linspace(400,800,250)
    peak=dict(id='P1',name='P1',center=527.,fwhm=47.,area=1200.,free_center=True,free_width=False)
    centers=526+np.linspace(0,3,8)
    areas=500+np.arange(8)*100
    data=np.stack([gaussian_area(x,a,c,47.)+2 for a,c in zip(areas,centers)])
    first=fit_fluorescence_batch(data,x,[peak])
    assert np.ptp(first['centers'][:,0])>2.
    second=fit_fluorescence_batch(data,x,[peak],refine_shapes=True,
       trend_constraints={(0,'center'):1},prior_result=first)
    assert second['refined']
    np.testing.assert_allclose(second['centers'][:,0],centers,atol=.4)
    np.testing.assert_allclose(second['areas'][:,0],areas,atol=1.5)
    assert np.array_equal(second['pass1']['centers'],first['pass1']['centers'])

def test_fixed_centers_honored_in_independent_pass():
    x=np.arange(200,dtype=float)
    p=dict(id='P1',name='P1',center=80.,fwhm=25.,area=800.,free_center=False,free_width=False)
    dat=np.stack([gaussian_area(x,500,83.,25.)+1 for _ in range(5)])
    fit=fit_fluorescence_batch(dat,x,[p])
    assert np.all(fit['centers']==80.)
