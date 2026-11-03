"""Layout-aware chunking for knowledge base documents.

Documents are split on section headings first, then packed into overlapping
chunks at paragraph / sentence boundaries. Two things matter for retrieval
quality: chunks never start or end mid-sentence, and every chunk keeps the
section heading it came from so technical context survives the split.
"""

import re
from dataclasses import dataclass

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200

#: A trailing fragment shorter than this is merged into the previous chunk.
MIN_CHUNK_CHARS = 200

_HEADING_MAX_CHARS = 80
_HEADING_MAX_WORDS = 12
_SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
)
#: Split after sentence punctuation, keeping the punctuation on the left side.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class DocumentChunk:
    """A single indexable slice of a knowledge document."""

    index: int
    text: str
    section: str | None


def normalize_text(text: str) -> str:
    """Normalize line endings and whitespace without destroying paragraph breaks."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BLANK_RUN_RE.sub("\n\n", normalized)
    normalized = "\n".join(_WHITESPACE_RE.sub(" ", line).strip() for line in normalized.split("\n"))
    return normalized.strip()


def _clean_heading(line: str) -> str:
    return line.lstrip("#").strip()


def _is_heading(line: str) -> bool:
    """Heuristic heading detection for extracted PDF / plain text layouts."""
    candidate = _clean_heading(line)
    if not 3 <= len(candidate) <= _HEADING_MAX_CHARS:
        return False
    # Headings are labels, not sentences.
    if candidate[-1] in ".!?;,":
        return False
    if len(candidate.split()) > _HEADING_MAX_WORDS:
        return False
    if line.startswith("#"):
        return True
    if candidate.isupper():
        return True

    alpha_words = [word for word in re.split(r"\s+", candidate) if word and word[0].isalpha()]
    if not alpha_words:
        return False
    return all(
        word.lower() in _SMALL_WORDS or word[0].isupper() for word in alpha_words
    )


def _split_sections(text: str) -> list[tuple[str | None, list[str]]]:
    """Group paragraphs under the most recent heading."""
    sections: list[tuple[str | None, list[str]]] = []
    paragraphs: list[str] = []
    buffer: list[str] = []
    title: str | None = None

    def flush_paragraph() -> None:
        if buffer:
            paragraph = " ".join(buffer).strip()
            if paragraph:
                paragraphs.append(paragraph)
            buffer.clear()

    def flush_section(next_title: str | None) -> None:
        nonlocal title, paragraphs
        flush_paragraph()
        if paragraphs:
            sections.append((title, paragraphs))
        paragraphs = []
        title = next_title

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if _is_heading(line):
            flush_section(_clean_heading(line))
            continue
        buffer.append(line)

    flush_section(None)
    return sections


def _hard_split(text: str, chunk_size: int) -> list[str]:
    """Last resort split for text with no usable punctuation."""
    pieces: list[str] = []
    current: list[str] = []
    length = 0

    for word in text.split():
        if current and length + len(word) + 1 > chunk_size:
            pieces.append(" ".join(current))
            current, length = [], 0
        current.append(word)
        length += len(word) + 1

    if current:
        pieces.append(" ".join(current))
    return pieces


def _paragraph_units(paragraph: str, chunk_size: int) -> list[str]:
    """Break an oversized paragraph into sentence units that fit a chunk."""
    if len(paragraph) <= chunk_size:
        return [paragraph]

    units: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        units.extend([sentence] if len(sentence) <= chunk_size else _hard_split(sentence, chunk_size))
    return units


def _overlap_tail(previous: list[str], overlap: int, chunk_size: int) -> list[str]:
    """Trailing units of a finished chunk, reused to start the next one."""
    if overlap <= 0 or len(previous) < 2:
        return []

    tail: list[str] = []
    total = 0
    for unit in reversed(previous[:-1]):
        if total >= overlap:
            break
        tail.insert(0, unit)
        total += len(unit) + 2

    # Never let the overlap eat half a chunk's budget on its own.
    if total > chunk_size // 2:
        return []
    return tail


def _pack(units: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Greedily pack units into size-bounded chunks with a leading overlap."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        if current and current_len + len(unit) + 2 > chunk_size:
            chunks.append(current)
            current = _overlap_tail(current, overlap, chunk_size)
            current_len = sum(len(item) + 2 for item in current)
        current.append(unit)
        current_len += len(unit) + 2

    if current:
        chunks.append(current)

    return ["\n\n".join(chunk) for chunk in chunks]


def _merge_trailing_fragment(chunks: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Fold a short final chunk back into its predecessor when it fits."""
    if len(chunks) < 2:
        return chunks

    last = chunks[-1]
    if len(last) >= MIN_CHUNK_CHARS:
        return chunks
    if len(chunks[-2]) + len(last) + 2 > chunk_size + overlap:
        return chunks

    merged = chunks[:-2] + [f"{chunks[-2]}\n\n{last}"]
    return merged


def chunk_document(
    text: str,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[DocumentChunk]:
    """Split document text into overlapping, section-tagged chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size.")

    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks: list[DocumentChunk] = []
    for section, paragraphs in _split_sections(normalized):
        units: list[str] = []
        for paragraph in paragraphs:
            units.extend(_paragraph_units(paragraph, chunk_size))

        pieces = _merge_trailing_fragment(_pack(units, chunk_size, overlap), chunk_size, overlap)
        for piece in pieces:
            chunks.append(DocumentChunk(index=len(chunks), text=piece, section=section))

    return chunks
