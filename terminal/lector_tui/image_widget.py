"""Native images painted as whole bitmaps after Textual's text composition.

Widgets reserve cells; ImageApp commits one bitmap per affected image after
text layout. Neither dirty rows nor scrolling split the bitmap.
"""

from __future__ import annotations

from collections import OrderedDict
import base64
from io import BytesIO
import secrets

from PIL import Image as PILImage, ImageDraw
from rich.control import Control
from rich.segment import Segment
from textual._compositor import ChopsUpdate, CompositorUpdate, LayoutUpdate
from textual.app import ComposeResult
from textual.geometry import Region, Size
from textual.strip import Strip
from textual.widgets import Static
from lector_tui import terminal_graphics
from lector_tui.terminal_graphics import configure_graphics
from lector_tui.tmux_images import pane_geometry, passthrough

# Seed the library's capability cache before its import-time auto selection.
configure_graphics()

from textual_image._geometry import ImageSize
from textual_image._pixeldata import PixelData
from textual_image._terminal import CellSize, get_cell_size
from textual_image.widget import HalfcellImage, Image, SixelImage, UnicodeImage
from textual_image.widget._base import Image as BaseImage
from textual_image.widget.sixel import _ImageSixelImpl


class _WholeSixels(_ImageSixelImpl):
    """Reserve text cells and cache complete, viewport-cropped bitmaps."""

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
        scaled = PixelData(image_data.pil_image.resize(pixels, PILImage.Resampling.LANCZOS))
        canvas_size = (self.content_size.width * terminal_sizes.width, self.content_size.height * terminal_sizes.height)
        if pixels != canvas_size:
            if canvas_size[0] * canvas_size[1] > 16_000_000:
                raise ValueError("图片缩放超过像素上限")
            r, g, b, _ = self._get_background_rgba()
            canvas = PILImage.new("RGB", canvas_size, (r, g, b))
            canvas.paste(
                scaled.pil_image, ((canvas_size[0] - pixels[0]) // 2, 0),
                scaled.pil_image if scaled.pil_image.mode == "RGBA" else None,
            )
            return PixelData(canvas)
        return scaled

    def render_lines(self, crop: Region) -> list[Strip]:
        clear = Strip([Segment(" " * crop.width, self._get_clear_style())], crop.width)
        return [clear] * crop.height

    def bitmap(self, crop: Region, occlusions: tuple[Region, ...]) -> str:
        cells = get_cell_size()
        background = self._get_background_rgba()
        key = (id(self.image), self.content_size, cells, background, self._sixel_options)
        if getattr(self, "_pixel_key", None) != key:
            self._pixels = self._scale_image(PixelData(self.image), cells)
            self._pixel_key = key
            self._bitmaps: OrderedDict[tuple, str] = OrderedDict()
            self._bitmap_bytes = 0
        cache_key = (crop, occlusions)
        if cache_key in self._bitmaps:
            self._bitmaps.move_to_end(cache_key)
            return self._bitmaps[cache_key]
        pixels = self._crop_image(self._pixels, crop, cells).pil_image
        if occlusions:
            # A notification/menu may cover only part of an image. Transparent
            # pixels preserve that text while the image remains a single bitmap.
            pixels = pixels.convert("RGBA")
            draw = ImageDraw.Draw(pixels)
            for area in occlusions:
                draw.rectangle(
                    (area.x * cells.width, area.y * cells.height,
                     area.right * cells.width - 1, area.bottom * cells.height - 1),
                    fill=(0, 0, 0, 0),
                )
        data = self.encode_bitmap(pixels, background, crop)
        while self._bitmaps and (len(self._bitmaps) >= 8 or self._bitmap_bytes + len(data) > 8 * 1024 * 1024):
            _, evicted = self._bitmaps.popitem(last=False)
            self._bitmap_bytes -= len(evicted)
        if len(data) <= 8 * 1024 * 1024:
            self._bitmaps[cache_key] = data
            self._bitmap_bytes += len(data)
        return data

    def encode_bitmap(self, pixels, background, crop: Region) -> str:
        return self._image_to_sixels(pixels, self._sixel_options, background)


class _WholeInlinePNG(_WholeSixels):
    """Lossless, full-pixel images; never quantize to character cells."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_id = secrets.randbelow(2**32 - 1) + 1

    def delete(self) -> str:
        # Only remove this widget's owned image, never other terminal graphics.
        return f"\x1b_Ga=d,d=I,i={self.image_id},q=2\x1b\\"

    def encode_bitmap(self, pixels, background, crop: Region) -> str:
        buffer = BytesIO()
        pixels.save(buffer, format="PNG")
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        chunks = []
        for start in range(0, len(data), 4096):
            chunk = data[start:start + 4096]
            more = int(start + 4096 < len(data))
            header = f"a=T,f=100,i={self.image_id},c={crop.width},r={crop.height},C=1," if start == 0 else ""
            chunks.append(f"\x1b_G{header}q=2,m={more};{chunk}\x1b\\")
        return self.delete() + "".join(chunks)


class WholeSixelImage(SixelImage, Renderable=SixelImage._Renderable):
    """Keep a stable child when an asynchronous download replaces an image."""

    @BaseImage.image.setter
    def image(self, value) -> None:
        self._error_widget = None
        self._is_failed = False
        BaseImage.image.fset(self, value)
        if self._error_widget is not None:
            self.refresh(recompose=True)
            return
        children = self.query(_WholeSixels)
        for child in children:
            child.image = self.image
            child.refresh()
        if self.is_mounted and not children:
            self.refresh(recompose=True)

    def compose(self) -> ComposeResult:
        if self._error_widget is not None:
            yield self._error_widget
        else:
            yield _WholeSixels(self.image, self._sixel_options)


class WholeInlineImage(WholeSixelImage, Renderable=SixelImage._Renderable):
    def compose(self) -> ComposeResult:
        if self._error_widget is not None:
            yield self._error_widget
        else:
            yield _WholeInlinePNG(self.image, self._sixel_options)


def _updated_regions(update: CompositorUpdate) -> list[Region]:
    if isinstance(update, LayoutUpdate):
        return [update.region]
    if isinstance(update, ChopsUpdate):
        # ChopsUpdate may write from a strip's start, before span.x1.
        return [
            Region(x, y, min(end, x2) - x, 1)
            for y, x1, x2 in update.spans
            for end, (x, strip) in zip(update.chop_ends[y], update.chops[y].items())
            if strip is not None and x < x2 and end > x1
        ]
    return []


def _erase_bitmap(widget, visible: Region, masks: tuple[Region, ...], console) -> str:
    """Release retained native layers even if Textual elides unchanged spaces.

    tmux stores Sixel layers separately from the text grid. Another bitmap at
    the same position adds a layer rather than replacing it. Explicit ECH runs
    retire those layers; skip foreground overlays so their text stays intact.
    """
    erase = []
    style = widget._get_clear_style()
    for y in range(visible.y, visible.bottom):
        x = visible.x
        blocked = sorted((area.x, area.right) for area in masks if area.y <= y < area.bottom)
        for left, right in [*blocked, (visible.right, visible.right)]:
            if left > x:
                erase.append(Control.move_to(x, y).segment.text)
                erase.append(style.render(f"\x1b[{left - x}X", color_system=console._color_system))
            x = max(x, right)
    return "".join(erase)


class _ImageFrame(CompositorUpdate):
    def __init__(self, screen, update: CompositorUpdate) -> None:
        self.screen, self.update = screen, update

    def render_segments(self, console) -> str:
        text = self.update.render_segments(console)
        dirty = _updated_regions(self.update)
        graphics = []
        geometry = pane_geometry() if terminal_graphics.inline_png else None
        current_inline = set()
        if terminal_graphics.inline_png:
            self.screen.app.begin_inline_frame()
        covered: list[Region] = []
        # This is the compositor's own front-to-back paint order and clipping.
        for widget, (region, clip) in self.screen._compositor.visible_widgets.items():
            visible = region.intersection(clip).intersection(self.screen.size.region)
            if isinstance(widget, _WholeSixels) and widget.image and visible:
                inline = isinstance(widget, _WholeInlinePNG)
                if inline and geometry is None:
                    widget._placement = None
                    continue
                if inline:
                    visible = visible.intersection(Region(0, 0, geometry.width, geometry.height))
                    if not visible:
                        continue
                masks = tuple(sorted({area.intersection(visible) for area in covered if area.overlaps(visible)}))
                if visible not in masks:
                    if inline:
                        current_inline.add(widget)
                    state = (visible, masks, id(widget.image), widget.content_size, widget._get_background_rgba(), geometry)
                    if getattr(widget, "_placement", None) != state or any(area.overlaps(visible) for area in dirty):
                        crop = visible.translate(-region.offset)
                        relative_masks = tuple(area.translate(-visible.offset) for area in masks)
                        try:
                            data = widget.bitmap(crop, relative_masks)
                        except (OSError, ValueError) as exc:
                            widget.post_message(widget.Failed(exc))
                        else:
                            if inline:
                                outer = visible.translate((geometry.left, geometry.top))
                                command = passthrough(
                                    Control.move_to(outer.x, outer.y).segment.text + data
                                )
                                self.screen.app.queue_inline_image(widget, state, geometry, command)
                            else:
                                graphics.append(
                                    _erase_bitmap(widget, visible, masks, console)
                                    + Control.move_to(visible.x, visible.y).segment.text + data
                                )
                                widget._placement = state
            if visible:
                covered.append(visible)
        if terminal_graphics.inline_png:
            text = self.screen.app.retire_inline_images(current_inline, geometry) + text
        if graphics:
            # Textual moves the cursor after this frame. Synchronize the clear
            # and complete image even before Textual's mode negotiation finishes.
            frame = text + "".join(graphics)
            if not self.screen.app._sync_available:
                frame = "\x1b[?2026h" + frame + "\x1b[?2026l"
            return frame
        return text


def image_frame(screen, update: CompositorUpdate) -> CompositorUpdate:
    if terminal_graphics.inline_png or any(isinstance(widget, _WholeSixels) for widget in screen._compositor.visible_widgets):
        return _ImageFrame(screen, update)
    return update


def image_error(exc: Exception) -> Static:
    """A broken image should leave the rest of the chapter readable."""
    return Static("图片无法显示", markup=False)


# Unicode fallback discards colour; half cells retain the book's colours.
if terminal_graphics.inline_png:
    _ImageRenderer = WholeInlineImage
elif Image is SixelImage:
    _ImageRenderer = WholeSixelImage
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
