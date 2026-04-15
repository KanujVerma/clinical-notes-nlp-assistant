from dataclasses import dataclass


@dataclass
class PreprocessResult:
    clean_text: str
    raw_text: str
    offset_map: list[tuple[int, int]]  # (clean_pos, raw_pos) for each char in clean_text

    def remap(self, clean_pos: int) -> int:
        """Return the raw_text character offset for a clean_text position."""
        if clean_pos >= len(self.offset_map):
            return len(self.raw_text)
        return self.offset_map[clean_pos][1]

    def remap_span(self, clean_start: int, clean_end: int) -> tuple[int, int]:
        raw_start = self.remap(clean_start)
        if clean_end >= len(self.offset_map):
            raw_end = len(self.raw_text)
        else:
            raw_end = self.offset_map[clean_end][1]
        return raw_start, raw_end


def preprocess(raw_text: str) -> PreprocessResult:
    """
    Clean the text for NLP while building a character-level offset map
    from clean positions back to raw positions.
    """
    clean_chars: list[str] = []
    offset_map: list[tuple[int, int]] = []

    raw_pos = 0
    while raw_pos < len(raw_text):
        ch = raw_text[raw_pos]
        if ch == "\n":
            # Collapse runs of newlines to at most 2
            newline_count = 0
            start = raw_pos
            while raw_pos < len(raw_text) and raw_text[raw_pos] == "\n":
                newline_count += 1
                raw_pos += 1
            emit = min(newline_count, 2)
            for i in range(emit):
                offset_map.append((len(clean_chars), start + i))
                clean_chars.append("\n")
        else:
            offset_map.append((len(clean_chars), raw_pos))
            clean_chars.append(ch)
            raw_pos += 1

    return PreprocessResult(
        clean_text="".join(clean_chars),
        raw_text=raw_text,
        offset_map=offset_map,
    )
