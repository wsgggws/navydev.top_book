"""Pydantic DTOs.

Field names here mirror ``docs/API.md`` one-for-one and carry no aliases, so a
JSON body produced by the client is the JSON body the contract describes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TtsState = Literal["pending", "partial", "ready", "failed"]
Granularity = Literal["word", "sentence"]
UpdatedBy = Literal["web", "terminal", "api"]
BlockType = Literal["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "img", "hr", "pre"]


class Sentence(BaseModel):
    """One sentence inside a block."""

    id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class Block(BaseModel):
    """A block of chapter content: a paragraph, heading, image, and so on."""

    type: BlockType
    id: str
    sentences: list[Sentence] = Field(default_factory=list)
    anchor: str | None = None
    anchors: list[str] = Field(default_factory=list)
    alt: str | None = None
    src: str | None = None


class Chapter(BaseModel):
    """A spine-ordered chapter."""

    chapter_id: str
    index: int
    title: str
    blocks: list[Block] = Field(default_factory=list)
    sentence_count: int = 0
    word_count: int = 0
    audio_duration: float = 0.0
    tts_state: TtsState = "pending"


class TocNode(BaseModel):
    """A navigation node.

    ``id`` identifies the node itself and carries no locating power; ``chapter_id``
    plus ``anchor`` are what a client resolves to a position.
    """

    id: str
    title: str
    chapter_id: str
    anchor: str | None = None
    children: list["TocNode"] = Field(default_factory=list)


class TocResponse(BaseModel):
    toc: list[TocNode] = Field(default_factory=list)


class Book(BaseModel):
    """Library record for one uploaded EPUB."""

    book_id: str
    title: str
    author: str | None = None
    language: str | None = None
    sha256: str
    size_bytes: int
    cover_url: str | None = None
    chapter_count: int = 0
    sentence_count: int = 0
    tts_state: TtsState = "pending"
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    book: Book
    duplicate: bool = False


class BookDetailResponse(BaseModel):
    book: Book
    progress: "Progress"


class ChapterResponse(BaseModel):
    chapter: Chapter
    prev_chapter_id: str | None = None
    next_chapter_id: str | None = None


class Cursor(BaseModel):
    """The one and only position representation in the system."""

    book_id: str
    chapter_id: str
    sentence_id: str
    word_index: int | None = None


class ProgressCursor(BaseModel):
    """Cursor fields as stored per book (the book id lives in the path)."""

    chapter_id: str
    sentence_id: str
    word_index: int | None = None


class Progress(BaseModel):
    book_id: str
    cursor: ProgressCursor | None = None
    percent: float = 0.0
    updated_at: str
    updated_by: UpdatedBy = "api"
    device_label: str | None = None


class ProgressUpdate(BaseModel):
    """Body of ``PUT /books/{id}/progress``."""

    chapter_id: str
    sentence_id: str
    word_index: int | None = None
    device_label: str | None = None


class Voice(BaseModel):
    voice_id: str
    name: str
    locale: str
    gender: str
    engine: str


class VoicesResponse(BaseModel):
    engine: str
    voices: list[Voice] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    parser_version: int
    tts: "TtsHealth"
    books: int = 0


class TtsHealth(BaseModel):
    engine: str
    available: bool
    voice_count: int = 0


class WordBoundary(BaseModel):
    """Timing of one word inside a sentence, relative to the sentence start."""

    text: str
    start: float
    end: float


class WordsResponse(BaseModel):
    sentence_id: str
    duration: float
    words: list[WordBoundary] = Field(default_factory=list)
    granularity: Granularity


class TimelineEntry(BaseModel):
    sentence_id: str
    start: float
    end: float
    audio_url: str
    word_count: int = 0


class TimelineResponse(BaseModel):
    chapter_id: str
    duration: float
    sentences: list[TimelineEntry] = Field(default_factory=list)
    tts_state: TtsState = "pending"


class WarmRequest(BaseModel):
    chapter_id: str | None = None
    voice_id: str | None = None
    rate: str = "+0%"
    limit: int | None = Field(None, ge=1, description="一次最多预热多少句")


class WarmResponse(BaseModel):
    queued: int = 0
    ready: int = 0
    failed: int = 0
    state: TtsState = "pending"


class ShortCodeRequest(BaseModel):
    book_id: str
    chapter_id: str
    sentence_id: str
    word_index: int | None = None


class ShortCodeResponse(BaseModel):
    code: str
    url: str


class SearchResult(BaseModel):
    sentence_id: str
    chapter_id: str
    chapter_title: str
    snippet: str
    before: str
    after: str


class SearchResponse(BaseModel):
    query: str
    total: int = 0
    results: list[SearchResult] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class BookList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    books: list[Book] = Field(default_factory=list)


class StatusResponse(BaseModel):
    status: str


BookDetailResponse.model_rebuild()
HealthResponse.model_rebuild()
TocNode.model_rebuild()
