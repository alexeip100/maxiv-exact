import numpy as np
from maxiv_exact.fluorescence_map import batch_row_for_incident


def test_batch_cursor_stays_in_the_containing_bin():
    starts=np.array([0, 5, 10, 15])
    assert [batch_row_for_incident(starts,i) for i in (0, 4, 5, 9, 10, 14, 15, 17)] == [0,0,1,1,2,2,3,3]


def test_single_scan_bins_follow_cursor():
    assert [batch_row_for_incident(np.arange(20), i) for i in (0,5,11,19)] == [0,5,11,19]
