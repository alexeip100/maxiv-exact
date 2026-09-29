"""Plotting subsystem.

The plotting functionality is implemented as a set of mixins that are combined
into :class:`~maxiv_exact.plotting.PlottingMixin`. This keeps responsibilities
separated (styles, legend, interactions, pipelines, etc.) while allowing the
main UI class to inherit a single mixin.
"""

from .mixin_waterfall import WaterfallMixin
from .mixin_grid_axes import GridAxesMixin
from .mixin_styles import StylesMixin
from .mixin_legend import LegendMixin
from .mixin_annotations import AnnotationsMixin
from .mixin_preedge_vline import PreedgeVlineMixin
from .mixin_raw_plot import RawPlotMixin
from .mixin_processed_plot import ProcessedPlotMixin
from .mixin_group_bg import GroupBackgroundMixin
from .mixin_core import CorePlottingMixin
from .mixin_qt_shims import QtShimsMixin


class PlottingMixin(
    WaterfallMixin,
    GridAxesMixin,
    StylesMixin,
    LegendMixin,
    AnnotationsMixin,
    PreedgeVlineMixin,
    GroupBackgroundMixin,
    RawPlotMixin,
    ProcessedPlotMixin,
    CorePlottingMixin,
    QtShimsMixin,
):
    """Composite plotting mixin used by the main Qt window."""
    pass
