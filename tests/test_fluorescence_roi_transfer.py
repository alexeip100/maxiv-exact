import numpy as np
import pytest
from maxiv_exact.fluorescence_map import integrate_fluorescence_roi


def test_roi_integral_inclusive_and_clamped():
    m=np.arange(20,dtype=float).reshape(4,5)
    np.testing.assert_array_equal(integrate_fluorescence_roi(m,2,1),m[:,1:4].sum(axis=1))
    np.testing.assert_array_equal(integrate_fluorescence_roi(m,0,2),m[:,:3].sum(axis=1))


def test_roi_transfer_is_independent_snapshot():
    m=np.ones((3,5))
    snapshot=integrate_fluorescence_roi(m,2,1)
    m[:]=100
    np.testing.assert_array_equal(snapshot,[3,3,3])


def test_missing_map_data_preserves_nan():
    m=np.array([[np.nan,np.nan],[4.,np.nan]])
    np.testing.assert_array_equal(np.isnan(integrate_fluorescence_roi(m,0,1)),[True,False])


def test_bad_roi_parameters():
    with pytest.raises(ValueError):integrate_fluorescence_roi(np.ones((2,3)),3,1)
