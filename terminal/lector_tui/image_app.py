"""Keep native graphics in the same terminal transaction as text layout."""

from textual._compositor import CompositorUpdate
from textual.app import App


class ImageApp(App):
    def _display(self, screen, renderable) -> None:
        if isinstance(renderable, CompositorUpdate):
            # Importing the graphical UI must remain behind CLI argument parsing.
            from lector_tui.image_widget import image_frame

            renderable = image_frame(screen, renderable)
        super()._display(screen, renderable)
