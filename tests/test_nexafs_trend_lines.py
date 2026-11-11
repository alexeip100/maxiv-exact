"""Display lines must preserve the sampled trend and its gaps."""

import numpy as np

from maxiv_exact.widgets.nexafs_trend_lines import trend_lines


def test_trend_lines_sort_samples_and_break_at_missing_or_ambiguous_points():
    x = np.array([6, 2, 0, 4, 5, 8, 9, 9, 10, np.nan, 14, 11, 12], dtype=float)
    y = np.array([.9, .2, .1, np.nan, .7, .95, 2, 3, .5, .1, 1.7, 1.2, 1.3])
    valid = np.isfinite(x) & np.isfinite(y)
    original_x, original_y = x.copy(), y.copy()
    lines = list(trend_lines(x, y, valid))
    assert [xx.tolist() for xx, _ in lines] == [[0, 2], [5, 6, 8], [11, 12, 14]]
    smooth = list(trend_lines(x, y, valid, smooth=True))
    assert len(smooth) == len(lines)
    for (grid, curve), (xx, yy) in zip(smooth, lines):
        assert grid[0] == xx[0] and grid[-1] == xx[-1]
        assert np.all(np.diff(grid) > 0)
        np.testing.assert_allclose(curve[np.searchsorted(grid, xx)], yy)
        assert len(grid) > len(xx) if len(xx) >= 3 else len(grid) == len(xx)
    np.testing.assert_array_equal(x, original_x)
    np.testing.assert_array_equal(y, original_y)
