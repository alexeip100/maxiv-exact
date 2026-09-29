"""Annotation/hover interaction mixin (Phase 3).

Moved from maxiv_exact.plotting.PlottingMixin.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QToolTip
from PyQt6.QtGui import QCursor


class AnnotationsMixin:
    def _default_plotted_annotation_style(self):
        """Default style for the Plotted Data annotation."""
        return {
            "fontsize": 12,
            "bold": False,
            "italic": False,
            "underline": False,
            "font_color": "#000000",
            "bg_enabled": True,
            "bg_color": "#FFFFFF",
            "border_enabled": True,
            "border_color": "#000000",
            "border_width": 0.8,
            "pad": 0.30,
        }

    def _get_plotted_annotation_style(self):
        """Get persisted style for the Plotted Data annotation."""
        try:
            st = getattr(self, "plotted_annotation_style", None)
        except Exception:
            st = None
        if not isinstance(st, dict):
            st = {}
        base = self._default_plotted_annotation_style()
        base.update({k: v for k, v in st.items() if k in base})
        return base


    def _build_plotted_annotation_bbox(self, style: dict):
        """Build a matplotlib bbox dict (or None) from a style dict."""
        try:
            enabled = bool(style.get("bg_enabled", True))
        except Exception:
            enabled = True
        if not enabled:
            return None
        try:
            pad = float(style.get("pad", 0.30))
        except Exception:
            pad = 0.30
        try:
            fc = style.get("bg_color", "#FFFFFF") or "#FFFFFF"
        except Exception:
            fc = "#FFFFFF"
        # Border options
        try:
            border_enabled = bool(style.get("border_enabled", True))
        except Exception:
            border_enabled = True
        try:
            bc = style.get("border_color", "#000000") or "#000000"
        except Exception:
            bc = "#000000"
        try:
            bw = float(style.get("border_width", 0.8))
        except Exception:
            bw = 0.8
        ec = bc if border_enabled else "none"
        lw = bw if border_enabled else 0.0
        return dict(boxstyle=f"round,pad={pad}", fc=fc, ec=ec, lw=lw)

    def _apply_plotted_annotation_style(self, ann, style: dict):
        """Apply style dict to a matplotlib Text annotation."""
        if ann is None:
            return
        try:
            ann.set_fontsize(int(style.get("fontsize", 12)))
        except Exception:
            pass
        try:
            ann.set_fontweight("bold" if bool(style.get("bold", False)) else "normal")
        except Exception:
            pass
        try:
            ann.set_fontstyle("italic" if bool(style.get("italic", False)) else "normal")
        except Exception:
            pass
        try:
            ann.set_underline(bool(style.get("underline", False)))
        except Exception:
            pass
        try:
            ann.set_color(style.get("font_color", "#000000"))
        except Exception:
            pass
        try:
            ann.set_bbox(self._build_plotted_annotation_bbox(style))
        except Exception:
            pass


    def toggle_plotted_annotation(self, visible: bool):
        """Show or hide the the annotation text box on the Plotted Data axes."""
        ax = getattr(self, "plotted_ax", None)
        if ax is None:
            return

        ann = getattr(self, "plotted_annotation", None)

        if visible:
            # Create annotation if it doesn't exist yet
            if ann is None:
                text = getattr(self, "plotted_annotation_text", "") or "Right-click to edit"
                try:
                    style = self._get_plotted_annotation_style()
                    bbox = self._build_plotted_annotation_bbox(style)
                    ann = ax.text(
                        0.02,
                        0.98,
                        text,
                        transform=ax.transAxes,
                        va="top",
                        ha="left",
                        bbox=bbox,
                    )
                    ann.set_picker(True)
                    try:
                        ann.set_draggable(True)
                    except Exception:
                        pass
                    # Ensure drag event handlers are connected once
                    try:
                        if not hasattr(self, "_annot_drag_cids"):
                            cids = []
                            if hasattr(self, "canvas_plotted"):
                                canvas = self.canvas_plotted
                                cids.append(canvas.mpl_connect("button_press_event", self._on_annotation_press))
                                cids.append(canvas.mpl_connect("motion_notify_event", self._on_annotation_motion))
                                cids.append(canvas.mpl_connect("button_release_event", self._on_annotation_release))
                            self._annot_drag_cids = tuple(cids)
                    except Exception:
                        pass
                    self.plotted_annotation = ann
                    try:
                        self.plotted_annotation_style = style
                    except Exception:
                        self.plotted_annotation_style = style
                    try:
                        self._apply_plotted_annotation_style(ann, style)
                    except Exception:
                        pass
                except Exception:
                    ann = None
                    self.plotted_annotation = None
            else:
                try:
                    ann.set_visible(True)
                except Exception:
                    pass
        else:
            if ann is not None:
                try:
                    ann.set_visible(False)
                except Exception:
                    pass

        try:
            if hasattr(self, "canvas_plotted"):
                self.canvas_plotted.draw()
        except Exception:
            pass
    def _on_annotation_press(self, event):
        """Start dragging the annotation text (left mouse button on the annotation)."""
        ax = getattr(self, "plotted_ax", None)
        ann = getattr(self, "plotted_annotation", None)
        if ax is None or ann is None:
            return
        if event.inaxes is not ax:
            return
        # Only react to left mouse button
        if getattr(event, "button", None) not in (1,):
            return
        contains, _ = ann.contains(event)
        if not contains:
            return
        try:
            # Current annotation position in display coordinates
            pos = ann.get_position()
            disp = ax.transAxes.transform(pos)
            self._annot_drag_active = True
            self._annot_drag_offset = (disp[0] - event.x, disp[1] - event.y)
        except Exception:
            self._annot_drag_active = False
            self._annot_drag_offset = None


    def _on_plotted_hover_hint(self, event):
        """Show a tooltip when hovering over editable items in the Plotted Data axes.

        Tooltip text is context-aware:
        - Annotation: right-click edits the annotation text/style
        - Legend:
            * User-defined legend mode: left-click renames curves, right-click edits legend style
            * Entry number legend mode: right-click edits legend style
        """
        try:
            ax = getattr(self, "plotted_ax", None)
            if ax is None or event is None or event.inaxes is not ax:
                # Hide when leaving the axes
                if getattr(self, "_annot_tooltip_active", False) or getattr(self, "_legend_tooltip_active", False):
                    QToolTip.hideText()
                    self._annot_tooltip_active = False
                    self._legend_tooltip_active = False
                    self._hover_tip_text = ""
                return

            # Determine hover target
            ann = getattr(self, "plotted_annotation", None)
            inside_ann = False
            if ann is not None:
                try:
                    inside_ann = bool(ann.contains(event)[0])
                except Exception:
                    inside_ann = False

            try:
                leg = ax.get_legend()
            except Exception:
                leg = None
            inside_leg = False
            if leg is not None:
                try:
                    inside_leg = bool(leg.contains(event)[0])
                except Exception:
                    inside_leg = False

            # Prefer annotation hover when both are true
            if inside_ann:
                inside_leg = False

            target = "ann" if inside_ann else ("leg" if inside_leg else None)

            # Determine tooltip text
            desired_text = ""
            if target == "ann":
                desired_text = "Right click to edit"
            elif target == "leg":
                mode = ""
                try:
                    mode = self._get_plotted_legend_mode()
                except Exception:
                    mode = ""
                if str(mode).strip().lower().startswith("user"):
                    desired_text = "Left click to rename (user-defined)  •  Right click to edit legend style"
                else:
                    desired_text = "Right click to edit legend style"

            annot_tip_active = getattr(self, "_annot_tooltip_active", False)
            legend_tip_active = getattr(self, "_legend_tooltip_active", False)
            tip_text_active = str(getattr(self, "_hover_tip_text", "") or "")

            if target is None:
                if annot_tip_active or legend_tip_active:
                    QToolTip.hideText()
                    self._annot_tooltip_active = False
                    self._legend_tooltip_active = False
                    self._hover_tip_text = ""
                return

            # Show or update tooltip if needed (new target or changed text)
            need_update = (not (annot_tip_active or legend_tip_active)) or (desired_text and desired_text != tip_text_active)                 or (self._annot_tooltip_active != (target == "ann")) or (self._legend_tooltip_active != (target == "leg"))

            if need_update:
                ge = getattr(event, "guiEvent", None)
                pos = None
                if ge is not None:
                    try:
                        pos = ge.globalPosition().toPoint()
                    except Exception:
                        pos = None
                if pos is None:
                    pos = QCursor.pos()
                owner = getattr(self, "canvas_plotted", None) or self
                QToolTip.showText(pos, desired_text, owner)
                self._hover_tip_text = desired_text
                self._annot_tooltip_active = (target == "ann")
                self._legend_tooltip_active = (target == "leg")
        except Exception:
            pass

    def _on_annotation_motion(self, event):
        """Update annotation position while dragging."""
        if not getattr(self, "_annot_drag_active", False):
            return
        ax = getattr(self, "plotted_ax", None)
        ann = getattr(self, "plotted_annotation", None)
        if ax is None or ann is None:
            return
        if event.inaxes is not ax:
            return
        try:
            dx, dy = self._annot_drag_offset
        except Exception:
            dx, dy = 0.0, 0.0
        try:
            new_disp = (event.x + dx, event.y + dy)
            new_axes = ax.transAxes.inverted().transform(new_disp)
            ann.set_position(new_axes)
            if hasattr(self, "canvas_plotted"):
                self.canvas_plotted.draw_idle()
        except Exception:
            pass

    def _on_annotation_release(self, event):
        """Finish dragging the annotation."""
        if getattr(self, "_annot_drag_active", False):
            self._annot_drag_active = False
            self._annot_drag_offset = None

