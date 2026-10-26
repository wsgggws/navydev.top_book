"""Coordinate whole-image drawing with Textual and tmux text transactions."""

from textual._compositor import CompositorUpdate
from textual.app import App
from textual.binding import Binding
from lector_tui import terminal_graphics


class ImageApp(App):
    BINDINGS = [Binding("ctrl+l", "refresh_images", "重绘图片", show=False)]

    def _begin_update(self) -> None:
        # tmux's synchronized text mode repaints whole dirty lines, erasing
        # passthrough PNG cells even when the compositor leaves them untouched.
        # Native Sixel and other terminals keep Textual's normal transaction.
        if not terminal_graphics.inline_png:
            super()._begin_update()

    def _end_update(self) -> None:
        if not terminal_graphics.inline_png:
            super()._end_update()

    def begin_inline_frame(self) -> None:
        self._inline_pending = {}
        if not hasattr(self, "_inline_drawn"):
            self._inline_drawn = set()

    def retire_inline_images(self, current, geometry) -> str:
        from lector_tui.tmux_images import passthrough

        retired = self._inline_drawn - current
        self._inline_drawn -= retired
        for widget in retired:
            widget._placement = None
        # Never send deletion to another tmux window. Its redraw already clears
        # the old screen; returning focus invalidates these placements.
        return passthrough("".join(widget.delete() for widget in retired)) if retired and geometry else ""

    def queue_inline_image(self, widget, state, geometry, command) -> None:
        """tmux must finish its text transaction before direct PNG delivery.

        Passthrough is emitted immediately, whereas tmux can defer text until
        the end of synchronized updates. Sending both in one transaction lets
        a late text erase wipe the newly drawn image. Coalesce image work after
        that transaction; only the latest placement of a live widget is sent.
        """
        # Until PNG delivery completes, an unrelated footer frame must still
        # regard this placement as dirty, preserving a queued move/forced redraw.
        widget._placement = None
        self._inline_pending[widget] = (state, geometry, command)
        if getattr(self, "_inline_timer", None) is None:
            self._inline_timer = self.set_timer(.04, self._flush_inline_images)

    def _flush_inline_images(self) -> None:
        from lector_tui.tmux_images import pane_geometry

        self._inline_timer = None
        geometry = pane_geometry()
        commands = []
        pending = self._inline_pending
        self._inline_pending = {}
        for widget, (state, expected, command) in pending.items():
            if geometry == expected and widget.is_mounted and widget.screen is self.screen:
                commands.append(command)
                widget._placement = state
                self._inline_drawn.add(widget)
        if commands and self._driver is not None:
            self._driver.write("".join(commands))
            self._driver.flush()

    def on_unmount(self) -> None:
        """Release owned terminal image data before returning to the shell."""
        timer = getattr(self, "_inline_timer", None)
        if timer is not None:
            timer.stop()
        if getattr(self, "_inline_drawn", None) and self._driver is not None:
            from lector_tui.tmux_images import pane_geometry

            command = self.retire_inline_images(set(), pane_geometry())
            if command:
                self._driver.write(command)
                self._driver.flush()

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
