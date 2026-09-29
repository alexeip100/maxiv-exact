"""Legend interaction mixin (Phase 3).

Moved from maxiv_exact.plotting.PlottingMixin to reduce module size and isolate interactivity.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QInputDialog

try:
    from ..widgets.legend_style_dialog import LegendStyleDialog
except Exception:
    LegendStyleDialog = None

try:
    from ..widgets.annotation_dialog import AnnotationEditDialog
except Exception:
    AnnotationEditDialog = None


class LegendMixin:
    def toggle_plotted_legend(self, visible: bool):
        """Show or hide the legend on the Plotted Data axes."""
        try:
            self.plotted_legend_visible = bool(visible)
        except Exception:
            self.plotted_legend_visible = bool(visible)

        ax = getattr(self, "plotted_ax", None)
        leg = None
        if ax is not None:
            try:
                leg = ax.get_legend()
            except Exception:
                leg = None

        if leg is not None:
            # Just toggle visibility of the existing legend; position is preserved
            try:
                leg.set_visible(self.plotted_legend_visible)
            except Exception:
                pass
        else:
            # No legend yet: create one if we are turning it on
            if self.plotted_legend_visible and hasattr(self, "update_legend"):
                try:
                    self.update_legend()
                except Exception:
                    pass

        if hasattr(self, "canvas_plotted"):
            try:
                self.canvas_plotted.draw()
            except Exception:
                pass


    def _get_plotted_legend_mode(self) -> str:
        """Return the current legend mode for Plotted Data."""
        # Prefer the UI combo box if present
        try:
            cb = getattr(self, "legend_mode_combo", None)
            if cb is not None:
                return str(cb.currentText() or "User-defined")
        except Exception:
            pass
        try:
            return str(getattr(self, "plotted_legend_mode", "User-defined") or "User-defined")
        except Exception:
            return "User-defined"


    def set_plotted_legend_mode(self, mode: str):
        """Set legend mode: None / User-defined / Entry number."""
        try:
            self.plotted_legend_mode = str(mode or "User-defined")
        except Exception:
            self.plotted_legend_mode = "User-defined"

        m = str(self._get_plotted_legend_mode() or "User-defined").strip().lower()
        ax = getattr(self, "plotted_ax", None)
        if ax is None:
            return

        # Remove legend entirely in 'None' mode
        if m in ("none", "off", "no"):
            try:
                self.plotted_legend_visible = False
            except Exception:
                pass
            try:
                leg = ax.get_legend()
                if leg is not None:
                    leg.remove()
            except Exception:
                pass
            try:
                if hasattr(self, "canvas_plotted"):
                    self.canvas_plotted.draw()
            except Exception:
                pass
            return

        # Otherwise ensure legend exists and is visible
        try:
            self.plotted_legend_visible = True
        except Exception:
            pass
        try:
            if hasattr(self, "update_legend"):
                self.update_legend()
        except Exception:
            pass


    def _default_plotted_legend_style(self):
        """Default style for the Plotted Data legend."""
        return {
            "alpha": 1.0,
            "borderpad": 0.4,
            "fontsize": 10,
            "bold": False,
            "italic": False,
            "underline": False,
        }


    def _get_plotted_legend_style(self):
        """Get persisted style for the Plotted Data legend."""
        try:
            st = getattr(self, "plotted_legend_style", None)
        except Exception:
            st = None
        if not isinstance(st, dict):
            st = {}
        base = self._default_plotted_legend_style()
        base.update({k: v for k, v in st.items() if k in base})
        return base


    def _legend_fontprops_from_style(self, style: dict):
        """Return a matplotlib FontProperties from legend style."""
        try:
            from matplotlib.font_manager import FontProperties
        except Exception:
            return None

        try:
            size = int(style.get("fontsize", 10))
        except Exception:
            size = 10
        weight = "bold" if bool(style.get("bold", False)) else "normal"
        fstyle = "italic" if bool(style.get("italic", False)) else "normal"
        try:
            return FontProperties(size=size, weight=weight, style=fstyle)
        except Exception:
            return None


    def _apply_plotted_legend_style(self, leg, style: dict):
        """Apply stored legend style to a matplotlib Legend instance."""
        if leg is None:
            return
        # Frame transparency
        try:
            alpha = float(style.get("alpha", 1.0))
        except Exception:
            alpha = 1.0
        try:
            frame = leg.get_frame()
            if frame is not None:
                frame.set_alpha(alpha)
        except Exception:
            pass

        # Margins (borderpad)
        try:
            pad = float(style.get("borderpad", 0.4))
        except Exception:
            pad = 0.4
        try:
            # Prefer public API when available
            if hasattr(leg, "set_borderpad"):
                leg.set_borderpad(pad)
            else:
                # Fallback: set attribute (works on many matplotlib versions)
                leg.borderpad = pad
        except Exception:
            pass

        # Font
        fp = self._legend_fontprops_from_style(style)
        underline = bool(style.get("underline", False))
        try:
            for t in leg.get_texts() or []:
                if fp is not None:
                    try:
                        t.set_fontproperties(fp)
                    except Exception:
                        # Fallback per-field
                        try:
                            t.set_fontsize(int(style.get("fontsize", 10)))
                        except Exception:
                            pass
                        try:
                            t.set_fontweight("bold" if bool(style.get("bold", False)) else "normal")
                        except Exception:
                            pass
                        try:
                            t.set_fontstyle("italic" if bool(style.get("italic", False)) else "normal")
                        except Exception:
                            pass
                try:
                    t.set_underline(bool(underline))
                except Exception:
                    pass
        except Exception:
            pass

    def on_legend_pick(self, event):
        """
        Handle pick events on the Plotted Data canvas.

        - If the picked artist is the annotation text object, open a dialog to edit it.
        - If the picked artist is a legend text entry, open a dialog to rename the curve.
        """
        artist = getattr(event, "artist", None)

        # 1) Annotation editing
        ann = getattr(self, "plotted_annotation", None)
        if ann is not None and artist is ann:
            mouse = getattr(event, 'mouseevent', None)
            button = getattr(mouse, 'button', None)
            # Only open edit dialog on right-click; left-click is for dragging
            if button not in (3,):
                return

            try:
                old_text = ann.get_text() or ""
            except Exception:
                old_text = ""
            # Use enhanced dialog if available
            if AnnotationEditDialog is not None:
                try:
                    style = self._get_plotted_annotation_style()
                except Exception:
                    style = self._default_plotted_annotation_style()
                try:
                    dlg = AnnotationEditDialog(old_text, style, self)
                    ok = (dlg.exec() == QDialog.DialogCode.Accepted)
                except Exception:
                    dlg = None
                    ok = False

                if ok and dlg is not None:
                    try:
                        text, new_style = dlg.get_text_and_style()
                    except Exception:
                        text, new_style = old_text, style
                    try:
                        ann.set_text(str(text))
                    except Exception:
                        pass
                    try:
                        self.plotted_annotation_text = str(text)
                    except Exception:
                        self.plotted_annotation_text = str(text)
                    try:
                        self.plotted_annotation_style = dict(new_style)
                    except Exception:
                        self.plotted_annotation_style = dict(new_style)
                    try:
                        self._apply_plotted_annotation_style(ann, dict(new_style))
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "canvas_plotted"):
                            self.canvas_plotted.draw()
                    except Exception:
                        pass
                return

            # Fallback: simple text-only dialog
            new_text, ok = QInputDialog.getText(
                self,
                "Edit annotation",
                "Annotation text:",
                text=old_text,
            )
            if ok:
                try:
                    text = str(new_text)
                except Exception:
                    text = old_text
                try:
                    ann.set_text(text)
                except Exception:
                    pass
                try:
                    self.plotted_annotation_text = text
                except Exception:
                    self.plotted_annotation_text = text
                try:
                    if hasattr(self, "canvas_plotted"):
                        self.canvas_plotted.draw()
                except Exception:
                    pass
            return

        # 2) Legend interactions
        ax = getattr(self, "plotted_ax", None)
        if ax is None:
            return
        try:
            leg = ax.get_legend()
        except Exception:
            leg = None
        if leg is None:
            return

        # Right click on legend -> edit legend style (available in any legend mode)
        try:
            mouse = getattr(event, 'mouseevent', None)
            button = getattr(mouse, 'button', None)
        except Exception:
            button = None

        # Accept right-click either on a legend text or on the legend frame
        try:
            frame = leg.get_frame()
        except Exception:
            frame = None

        try:
            legend_texts = list(leg.get_texts() or [])
        except Exception:
            legend_texts = []

        if button in (3,) and (artist in legend_texts or (frame is not None and artist is frame)):
            if LegendStyleDialog is None:
                return
            try:
                style = self._get_plotted_legend_style()
            except Exception:
                style = self._default_plotted_legend_style()
            try:
                dlg = LegendStyleDialog(style, self)
                ok = (dlg.exec() == QDialog.DialogCode.Accepted)
            except Exception:
                ok = False
                dlg = None
            if ok and dlg is not None:
                try:
                    new_style = dlg.get_style()
                except Exception:
                    new_style = style
                try:
                    self.plotted_legend_style = dict(new_style)
                except Exception:
                    self.plotted_legend_style = dict(new_style)
                # Rebuild legend to apply padding/font changes while preserving dragged placement
                try:
                    self.update_legend()
                except Exception:
                    pass
            return

        # 3) Legend text renaming (only in 'User-defined' mode)
        try:
            mode = str(self._get_plotted_legend_mode() or "User-defined").strip().lower()
        except Exception:
            mode = "user-defined"
        if mode not in ("user-defined", "user", "custom"):
            return

        texts = legend_texts
        if artist not in texts:
            # Ignore picks that are not legend text
            return

        # Only open rename dialog on left click
        if button not in (1, None):
            return

        if hasattr(artist, "get_text"):
            old_text = artist.get_text()
            new_text, ok = QInputDialog.getText(
                self,
                "Rename Curve",
                "New legend name:",
                text=old_text,
            )
            if ok and new_text:
                # Map the clicked legend text to the corresponding plotted curve.
                # We use the legend's current ordering (stored when the legend is rebuilt)
                # so renaming is unambiguous even when multiple curves share the same
                # placeholder label (<select curve name>).
                key_to_rename = None
                try:
                    idx_text = texts.index(artist)
                except Exception:
                    idx_text = None
                try:
                    legend_keys = getattr(self, "_legend_keys_in_order", None)
                    if idx_text is not None and isinstance(legend_keys, (list, tuple)) and 0 <= idx_text < len(legend_keys):
                        key_to_rename = str(legend_keys[idx_text])
                except Exception:
                    key_to_rename = None

                if key_to_rename is None:
                    try:
                        for k, ln in getattr(self, "plotted_lines", {}).items():
                            current_label = getattr(self, "custom_labels", {}).get(k)
                            if (current_label is None and old_text == "<select curve name>") or (current_label == old_text):
                                key_to_rename = k
                                break
                    except Exception:
                        key_to_rename = None

                if key_to_rename is not None:
                    try:
                        self.custom_labels[key_to_rename] = str(new_text)
                    except Exception:
                        pass
                    try:
                        ln = getattr(self, "plotted_lines", {}).get(key_to_rename)
                        if ln is not None:
                            ln.set_label(str(new_text))
                    except Exception:
                        pass

                self.update_legend()


    def _keep_legend_inside_axes(self, ax, leg, pad: float = 0.01) -> None:
        """Ensure the legend stays fully inside the Axes without shrinking the plot.

        Matplotlib's draggable legend stores the placement via bbox_to_anchor (often using
        an "upper left" reference point). When legend text changes (e.g. switching legend
        mode), the legend box can grow and protrude outside the Axes, and tight_layout may
        shrink the Axes to make room. Here we (1) exclude the legend from layout and (2)
        nudge its anchor point so the legend bbox fits inside [0, 1]x[0, 1] in Axes coords.
        """
        if ax is None or leg is None:
            return
        # Do not let tight_layout / constrained_layout resize the Axes because of the legend
        try:
            leg.set_in_layout(False)
        except Exception:
            pass

        try:
            fig = ax.figure
            canvas = getattr(fig, "canvas", None)
            if canvas is None:
                return
            # Need a draw to get correct text extents
            try:
                canvas.draw()
            except Exception:
                return
            renderer = canvas.get_renderer()
            bbox_disp = leg.get_window_extent(renderer=renderer)
            bbox_ax = bbox_disp.transformed(ax.transAxes.inverted())

            dx = 0.0
            dy = 0.0
            # Horizontal
            if bbox_ax.x0 < pad:
                dx = pad - bbox_ax.x0
            elif bbox_ax.x1 > 1.0 - pad:
                dx = (1.0 - pad) - bbox_ax.x1
            # Vertical
            if bbox_ax.y0 < pad:
                dy = pad - bbox_ax.y0
            elif bbox_ax.y1 > 1.0 - pad:
                dy = (1.0 - pad) - bbox_ax.y1

            if dx != 0.0 or dy != 0.0:
                # Re-anchor using the legend's current upper-left corner (axes coords)
                ul_x = bbox_ax.x0 + dx
                ul_y = bbox_ax.y1 + dy
                try:
                    # Use 'upper left' anchoring to interpret bbox_to_anchor as UL corner
                    try:
                        leg.set_loc("upper left")
                    except Exception:
                        leg._loc = 2
                    leg.set_bbox_to_anchor((ul_x, ul_y), transform=ax.transAxes)
                except Exception:
                    return

                try:
                    canvas.draw()
                except Exception:
                    pass
        except Exception:
            return
    def update_legend(self):
        """Rebuild the legend so its order follows the Plotted list (visible curves only)."""
        try:
            # Legend mode: None / User-defined / Entry number
            try:
                mode = str(self._get_plotted_legend_mode() or "User-defined").strip().lower()
            except Exception:
                mode = "user-defined"

            # Remove legend entirely in 'None' mode
            if mode in ("none", "off", "no"):
                ax = getattr(self, "plotted_ax", None)
                if ax is not None:
                    try:
                        leg = ax.get_legend()
                        if leg is not None:
                            leg.remove()
                    except Exception:
                        pass
                try:
                    self.plotted_legend_visible = False
                except Exception:
                    pass
                try:
                    if hasattr(self, "canvas_plotted"):
                        self.canvas_plotted.draw()
                except Exception:
                    pass
                return

            order = []
            if hasattr(self, "plotted_list") and self.plotted_list is not None:
                from ..widgets.curve_item import CurveListItemWidget
                for row in range(self.plotted_list.count()):
                    item = self.plotted_list.item(row)
                    if item is None:
                        continue
                    # Retrieve the storage key from the item (set in pass_to_plotted_no_clear / _add_reference_curve_to_plotted)
                    key = item.data(Qt.ItemDataRole.UserRole)
                    if key is not None:
                        key = str(key)

                    # If Qt has detached the row widget (e.g. after drag/drop), recreate it
                    widget = self.plotted_list.itemWidget(item)
                    if widget is None and key:
                        line = getattr(self, "plotted_lines", {}).get(key)
                        if line is not None:
                            origin_label = line.get_label() or key
                            widget = CurveListItemWidget(origin_label, line.get_color(), key)
                            widget.colorChanged.connect(self.change_curve_color)
                            widget.visibilityChanged.connect(self.change_curve_visibility)
                            widget.styleChanged.connect(self.change_curve_style)
                            if hasattr(widget, "removeRequested"):
                                widget.removeRequested.connect(self.on_curve_remove_requested)
                            # For reference curves from the library, disable "Add to library" button again
                            meta = getattr(self, "plotted_metadata", {}).get(key, {}) if hasattr(self, "plotted_metadata") else {}
                            if meta.get("is_reference") and hasattr(widget, "set_add_to_library_enabled"):
                                widget.set_add_to_library_enabled(False)
                            item.setSizeHint(widget.sizeHint())
                            self.plotted_list.setItemWidget(item, widget)

                    if key:
                        order.append(key)

            ax = getattr(self, "plotted_ax", None)
            existing_leg = None
            saved_loc = getattr(self, "_plotted_legend_loc", None)
            saved_bbox = getattr(self, "_plotted_legend_bbox", None)
            if ax is not None:
                try:
                    existing_leg = ax.get_legend()
                except Exception:
                    existing_leg = None
            if existing_leg is not None:
                try:
                    saved_loc = getattr(existing_leg, "_loc", saved_loc)
                except Exception:
                    pass
                try:
                    saved_bbox = existing_leg.get_bbox_to_anchor()
                except Exception:
                    pass
            try:
                self._plotted_legend_loc = saved_loc
            except Exception:
                self._plotted_legend_loc = saved_loc
            try:
                self._plotted_legend_bbox = saved_bbox
            except Exception:
                self._plotted_legend_bbox = saved_bbox

            handles, labels = [], []
            legend_keys_in_order = []  # keys corresponding 1:1 with handles/labels
            entry_mode = mode in ("entry number", "entry", "entry-number", "entry_id", "entry id", "id")
            for key in order:
                line = getattr(self, "plotted_lines", {}).get(key)
                if line is None or (hasattr(line, "get_visible") and not line.get_visible()):
                    continue

                handles.append(line)
                legend_keys_in_order.append(key)

                lbl = None
                if entry_mode:
                    # IMPORTANT: Do NOT overwrite the underlying Line2D label in 'Entry number' mode.
                    # We only change what is displayed in the legend.
                    try:
                        lbl = self._legend_label_from_entry_number(key, line)
                    except Exception:
                        lbl = None
                else:
                    # User-defined mode: use stored custom labels when present,
                    # otherwise show the placeholder.
                    try:
                        lbl = getattr(self, "custom_labels", {}).get(key)
                    except Exception:
                        lbl = None

                    if not lbl:
                        try:
                            current = line.get_label()
                        except Exception:
                            current = None

                        # If the label got corrupted earlier (e.g. overwritten by entry number),
                        # restore to placeholder unless the user explicitly set a label.
                        try:
                            entry_lbl = self._legend_label_from_entry_number(key, line)
                        except Exception:
                            entry_lbl = None

                        if (not current) or (str(current).strip() == ""):
                            lbl = "<select curve name>"
                        else:
                            s = str(current).strip()
                            # Treat as corrupted if it looks like a pure entry number and matches what we'd derive.
                            if entry_lbl and s == str(entry_lbl).strip() and s.isdigit():
                                lbl = "<select curve name>"
                            else:
                                lbl = s

                    # In user-defined mode we keep the underlying label in sync,
                    # because other parts of the UI rely on it.
                    try:
                        line.set_label(lbl)
                    except Exception:
                        pass

                if not lbl:
                    lbl = "<select curve name>"
                labels.append(lbl)

            if not hasattr(self, "plotted_ax"):
                # Nothing to draw the legend on
                if hasattr(self, "canvas_plotted"):
                    try:
                        self.canvas_plotted.draw()
                    except Exception:
                        pass
                return

            ax = self.plotted_ax
            leg = None
            if handles:
                # Legend style (persisted)
                try:
                    leg_style = self._get_plotted_legend_style()
                except Exception:
                    leg_style = self._default_plotted_legend_style()

                legend_kwargs = {}
                try:
                    legend_kwargs["borderpad"] = float(leg_style.get("borderpad", 0.4))
                except Exception:
                    pass
                try:
                    legend_kwargs["framealpha"] = float(leg_style.get("alpha", 1.0))
                except Exception:
                    pass
                try:
                    fp = self._legend_fontprops_from_style(leg_style)
                    if fp is not None:
                        legend_kwargs["prop"] = fp
                except Exception:
                    pass

                # Recreate legend at its previous location if known
                saved_loc = getattr(self, "_plotted_legend_loc", None)

                if saved_loc is not None:
                    # Preserve the user's dragged legend placement when possible.
                    # Matplotlib's draggable legend often stores placement via bbox_to_anchor.
                    saved_bbox = getattr(self, "_plotted_legend_bbox", None)
                    if saved_bbox is not None:
                        try:
                            # Use a plain tuple in Axes coordinates when possible
                            b = getattr(saved_bbox, "bounds", None)
                            if b is not None:
                                leg = ax.legend(handles, labels, loc=saved_loc, bbox_to_anchor=b, bbox_transform=ax.transAxes, **legend_kwargs)
                            else:
                                leg = ax.legend(handles, labels, loc=saved_loc, bbox_to_anchor=saved_bbox, bbox_transform=ax.transAxes, **legend_kwargs)
                        except Exception:
                            leg = ax.legend(handles, labels, loc=saved_loc, **legend_kwargs)
                    else:
                        leg = ax.legend(handles, labels, loc=saved_loc, **legend_kwargs)
                else:
                    leg = ax.legend(handles, labels, **legend_kwargs)
                try:
                    if leg:
                        # Prevent tight_layout from shrinking the axes to "make room" for the legend
                        # (we keep the plot size constant and instead nudge the legend to fit inside the axes).
                        try:
                            leg.set_in_layout(False)
                        except Exception:
                            pass
                        leg.set_draggable(True)
                        # Make the legend frame pickable (for right-click style editing)
                        try:
                            frame = leg.get_frame()
                            if frame is not None:
                                frame.set_picker(5)
                        except Exception:
                            pass
                        for t in leg.get_texts():
                            # Smaller picker tolerance reduces accidental selection of a neighbour entry.
                            try:
                                t.set_picker(5)
                            except Exception:
                                t.set_picker(True)
                except Exception:
                    pass

                # Apply underline (and any post-creation tweaks)
                try:
                    self._apply_plotted_legend_style(leg, leg_style)
                except Exception:
                    pass

            # Store legend ordering for unambiguous renaming in on_legend_pick()
            try:
                self._legend_keys_in_order = list(legend_keys_in_order)
            except Exception:
                self._legend_keys_in_order = legend_keys_in_order
            try:
                self._plotted_legend = leg
            except Exception:
                self._plotted_legend = leg

            # Apply visibility flag so that hiding the legend keeps its position
            try:
                show_legend = getattr(self, "plotted_legend_visible", True)
            except Exception:
                show_legend = True
            if leg is not None:
                try:
                    leg.set_visible(bool(show_legend))
                except Exception:
                    pass

                # Keep the legend fully inside the Axes without shrinking the plot area
                try:
                    self._keep_legend_inside_axes(ax, leg)
                except Exception:
                    pass

            if hasattr(self, "canvas_plotted_fig"):
                try:
                    self.canvas_plotted_fig.tight_layout()
                except Exception:
                    pass
            if hasattr(self, "canvas_plotted"):
                try:
                    self.canvas_plotted.draw()
                except Exception:
                    pass
        except Exception:
            pass
    def visible_curves_count(self):
        return sum(1 for _k, visible in getattr(self, "raw_visibility", {}).items() if visible)


