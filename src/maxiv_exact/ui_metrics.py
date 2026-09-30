from __future__ import annotations

"""Shared UI geometry for EXACT.

These metrics keep generic Qt geometry coherent when the user enlarges the UI
font. Scientific/plot geometry remains owned by the individual feature.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class UiMetrics:
    panel_margin: int = 8
    layout_spacing: int = 6
    compact_spacing: int = 5
    standard_control_height: int = 28
    small_row_height: int = 34
    settings_button_size: int = 30
    main_tree_min_width: int = 250
    raw_tree_min_width: int = 180
    processed_tree_min_width: int = 200
    plotted_list_min_width: int = 180
    combo_min_width: int = 150
    tab_v_padding: int = 4
    tab_h_padding: int = 10
    tab_gap: int = 2
    item_v_padding: int = 1
    menu_v_padding: int = 3


BASE_METRICS = UiMetrics()


def metrics_for_font_offset(font_offset_pt: int = 0) -> UiMetrics:
    """Expand generic geometry for +1/+2 pt accessibility font settings."""
    try:
        offset = max(0, min(2, int(font_offset_pt)))
    except Exception:
        offset = 0
    if offset == 0:
        return BASE_METRICS
    return replace(
        BASE_METRICS,
        panel_margin=BASE_METRICS.panel_margin + offset,
        layout_spacing=BASE_METRICS.layout_spacing + offset,
        compact_spacing=BASE_METRICS.compact_spacing + offset,
        standard_control_height=BASE_METRICS.standard_control_height + 3 * offset,
        small_row_height=BASE_METRICS.small_row_height + 3 * offset,
        settings_button_size=BASE_METRICS.settings_button_size + 3 * offset,
        main_tree_min_width=BASE_METRICS.main_tree_min_width + 18 * offset,
        raw_tree_min_width=BASE_METRICS.raw_tree_min_width + 14 * offset,
        processed_tree_min_width=BASE_METRICS.processed_tree_min_width + 14 * offset,
        plotted_list_min_width=BASE_METRICS.plotted_list_min_width + 14 * offset,
        combo_min_width=BASE_METRICS.combo_min_width + 10 * offset,
        tab_v_padding=BASE_METRICS.tab_v_padding + offset,
        tab_h_padding=BASE_METRICS.tab_h_padding + 2 * offset,
        tab_gap=BASE_METRICS.tab_gap,
        item_v_padding=BASE_METRICS.item_v_padding + offset,
        menu_v_padding=BASE_METRICS.menu_v_padding + offset,
    )
