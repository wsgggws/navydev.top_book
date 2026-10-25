"""Images that survive Textual's partial row repaints.

Sixel pixels are not terminal characters. Each strip must carry its own pixels:
putting an entire bitmap on the last strip leaves holes when other rows repaint.
The small adapter uses textual-image 0.14's scaling and Sixel encoder; tests lock
its crop/strip contract because the implementation hook is private upstream.
"""

from __future__ import annotations

from PIL import Image as PILImage
from rich.control import Control
from rich.segment import ControlType, Segment
from rich.style import Style
from textual.app import ComposeResult
from textual.dom import NoScreen
from textual.geometry import Region, Size
from textual.strip import Strip
from textual.widgets import Static
from textual_image._geometry import ImageSize
from textual_image._pixeldata import PixelData
from textual_image._terminal import CellSize, get_cell_size
from textual_image.widget import HalfcellImage, Image, SixelImage, UnicodeImage
from textual_image.widget.sixel import _ImageSixelImpl


class _RowSixels(_ImageSixelImpl):
    """Cache scaled pixels and encode independent terminal rows on demand."""

    def _scale_image(self, image_data: PixelData, terminal_sizes: CellSize) -> PixelData:
        width, height = self.parent._get_styled_size()
        pixels = ImageSize(image_data.width, image_data.height, width, height).get_pixel_size(
            self.content_size.width,
            self.content_size.height,
            terminal_sizes,
        )
        # A 1px-wide tall image can expand enormously at terminal width even
        # when the source passed Pillow's pixel limit.
        if pixels[0] * pixels[1] > 16_000_000:
            raise ValueError("图片缩放超过像素上限")
        scaled = image_data.scaled(*pixels)
        canvas_size = (self.content_size.width * terminal_sizes.width, self.content_size.height * terminal_sizes.height)
        if pixels != canvas_size:
            if canvas_size[0] * canvas_size[1] > 16_000_000:
                raise ValueError("图片缩放超过像素上限")
            r, g, b, _ = self._get_background_rgba()
            canvas = PILImage.new("RGB", canvas_size, (r, g, b))
            canvas.paste(scaled.pil_image, ((canvas_size[0] - pixels[0]) // 2, 0))
            return PixelData(canvas)
        return scaled

    def render_lines(self, crop: Region) -> list[Strip]:
        try:
            if not self.image or not self.screen.is_active or not crop:
                return []
        except NoScreen:
            return []
        cells = get_cell_size()
        background = self._get_background_rgba()
        key = (id(self.image), self.content_size, cells, background)
        if getattr(self, "_pixel_key", None) != key:
            try:
                self._pixels = self._scale_image(PixelData(self.image), cells)
            except (OSError, ValueError) as exc:
                self.post_message(self.Failed(exc))
                return []
            self._pixel_key = key
            self._rows: dict[tuple[int, int, int], str] = {}
        lines: list[Strip] = []
        clear = Segment(" " * crop.width, style=self._get_clear_style())
        for y in range(crop.y, crop.bottom):
            row_key = (crop.x, y, crop.width)
            data = self._rows.get(row_key)
            if data is None:
                pixels = self._crop_image(self._pixels, Region(crop.x, y, crop.width, 1), cells)
                data = self._image_to_sixels(pixels.pil_image, self._sixel_options, background)
                if len(self._rows) >= 256:
                    self._rows.pop(next(iter(self._rows)))
                self._rows[row_key] = data
            # Use the requested row, not the visible image's top-left: partial
            # repaint and top-clipped scroll regions have different origins.
            x_screen = self.region.x + crop.x
            y_screen = self.region.y + y
            lines.append(
                Strip(
                    [
                        clear,
                        Control.move_to(x_screen, y_screen).segment,
                        Segment(data, style=Style(), control=((ControlType.CURSOR_FORWARD, 0),)),
                        Control.move_to(x_screen + crop.width, y_screen).segment,
                    ],
                    cell_length=crop.width,
                )
            )
        return lines


class RowSixelImage(SixelImage, Renderable=SixelImage._Renderable):
    """A native Sixel image with independent, correctly positioned row strips."""

    def compose(self) -> ComposeResult:
        yield _RowSixels(self.image, self._sixel_options)


def image_error(exc: Exception) -> Static:
    """A broken image should leave the rest of the chapter readable."""
    return Static("图片无法显示", markup=False)


# Unicode fallback discards colour; half cells retain the book's colours.
if Image is SixelImage:
    _ImageRenderer = RowSixelImage
elif Image._Renderable is UnicodeImage._Renderable:
    _ImageRenderer = HalfcellImage
else:
    _ImageRenderer = Image


class TerminalImage(_ImageRenderer, Renderable=_ImageRenderer._Renderable):
    """Fit chapter illustrations into a complete preview, preserving aspect."""

    def _get_styled_size(self):
        if self.has_class("chapter-image"):
            return "auto", "auto"
        return super()._get_styled_size()

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        if not self.has_class("chapter-image"):
            return super().get_content_height(container, viewport, width)
        cells = get_cell_size()
        available_rows = max(1, min(28, self.app.size.height - 8))
        # Tiny inline glyphs should not grow to page-width illustrations.
        available_width = min(width, max(1, (self._image_width + cells.width - 1) // cells.width))
        _, height = ImageSize(self._image_width, self._image_height, "auto", "auto").get_cell_size(
            available_width,
            available_rows,
            cells,
        )
        return max(1, height) if self.image is not None else 0
