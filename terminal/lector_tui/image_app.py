"""Keep native graphics in the same terminal transaction as text layout."""

from textual._compositor import CompositorUpdate
from textual.app import App
from textual.binding import Binding


class ImageApp(App):
    BINDINGS = [Binding("ctrl+l", "refresh_images", "重绘图片", show=False)]

    def action_refresh_images(self) -> None:
        """Restore images that a multiplexer/window redraw may have erased."""
        from lector_tui.image_widget import _WholeSixels

        for widget in self.screen.query(_WholeSixels):
            widget._placement = None
        self.screen.refresh()

    def on_app_focus(self) -> None:
        # tmux focus-events sends this when returning to a window or pane.
        # Keep decoded pixels and bitmap caches; only invalidate placements.
        self.action_refresh_images()

    def _display(self, screen, renderable) -> None:
        if isinstance(renderable, CompositorUpdate):
            # Importing the graphical UI must remain behind CLI argument parsing.
            from lector_tui.image_widget import image_frame

            if getattr(self, "_image_screen", None) is not screen:
                from lector_tui.image_widget import _WholeSixels

                for widget in screen.query(_WholeSixels):
                    widget._placement = None
                self._image_screen = screen
            renderable = image_frame(screen, renderable)
        super()._display(screen, renderable)
