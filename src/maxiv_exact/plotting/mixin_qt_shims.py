from __future__ import annotations

class QtShimsMixin:

    def setGeometry(self, *args, **kwargs):
        """Delegate to the underlying Qt widget implementation.

        A previous no-op stub here prevented QMainWindow.setGeometry() from
        taking effect due to MRO (PlottingMixin appears before QMainWindow).
        """
        try:
            return super().setGeometry(*args, **kwargs)
        except Exception:
            return None
