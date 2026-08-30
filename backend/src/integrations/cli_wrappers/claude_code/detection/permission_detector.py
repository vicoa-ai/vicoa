"""Permission prompt detector for Claude CLI.

This detector identifies standard permission prompts when Claude
requests permission to perform actions (e.g., file operations).
"""

import re
from typing import Dict, List, Optional

from .base import BaseDetector, DetectionResult


class PermissionDetector(BaseDetector):
    """Detects permission prompts in terminal output.

    Permission prompts typically show:
    - A question starting with "Do you want..." or "What do you want to do..."
    - Numbered options (typically 3):
      1. Yes
      2. Yes, and don't ask again this session
      3. No
    - "(esc to cancel)" or "(escape to cancel)" hint
    """

    # Primary keywords that indicate a permission prompt
    # Expanded to cover more prompt variations (e.g., "Would you like to proceed?")
    PRIMARY_KEYWORDS = [
        "Do you want",
        "Would you like",
        "What do you want to do",
    ]

    def __init__(self):
        """Initialize permission detector."""
        super().__init__()
        self._question_line_idx = 0

    # Escape hint that's typically present
    ESC_HINT = "(esc"
    ESC_CANCEL = "esc to cancel"
    ESCAPE_CANCEL = "escape to cancel"

    # Pattern to match numbered options with optional non-digit prefix
    OPTION_PATTERN = re.compile(r"^[^\d]*(\d+)[\.)]\s+(.+)")

    # Default options if extraction fails
    DEFAULT_OPTIONS = {
        "1": "1. Yes",
        "2": "2. Yes, and don't ask again this session",
        "3": "3. No",
    }

    # Unicode characters to clean
    BORDER_CHAR = "\u2502"  # │

    # Separator line detection (box drawing / dash heavy)
    SEPARATOR_PATTERN = re.compile(
        r"^[\s\-\u2500\u2501\u2504\u2505\u2508\u2509\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c]+$"
    )

    # Selection markers that can prefix the focused option
    SELECTION_MARKER_PATTERN = re.compile(
        r"^[\s\u200b\u200e\u200f\u2060]*(?:[❯>▶▸›»]+)\s*"
    )

    def detect(self, clean_buffer: str) -> bool:
        """Check if a permission prompt is present in the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            True if permission prompt detected, False otherwise
        """
        # A real Claude permission modal ALWAYS renders a selection cursor
        # (❯/▶/▸/›/») on the highlighted numbered option. That marker —
        # sitting directly before a "1./2./3." line — is the load-bearing
        # signal. A bare numbered list in prose ("Want me to: 1. … 2. …
        # 3. Both") has no such cursor, so it must not match even if a
        # keyword like "Would you like" appears elsewhere in scrollback.
        # Keyword presence alone is not enough; it only helps pick which
        # line is the question once we already know a modal is rendered.
        if not self._has_numbered_options(clean_buffer):
            return False
        if not self._has_marked_option(clean_buffer):
            return False
        if any(kw in clean_buffer for kw in self.PRIMARY_KEYWORDS):
            return True
        normalized = clean_buffer.replace("\r", "\n")
        lines = normalized.split("\n")
        return self._build_question_from_content_block(lines) is not None

    def extract(self, clean_buffer: str) -> DetectionResult:
        """Extract question and options from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            DetectionResult with permission data, or not_detected
        """
        if not self.detect(clean_buffer):
            return DetectionResult.not_detected()

        # Reset question line index for fresh extraction
        self._question_line_idx = 0

        # Extract question
        question = self._extract_question(clean_buffer)

        # Extract options
        options_dict = self._extract_options(clean_buffer)

        # Validate extraction
        if not question:
            question = "Permission required"

        if not options_dict or len(options_dict) < 2:
            return DetectionResult.not_detected()

        options_list = [
            options_dict[key]
            for key in sorted(options_dict.keys(), key=lambda item: int(item))
        ]

        # Build options mapping (option text -> number)
        options_map = {}
        for option_num, option_text in options_dict.items():
            clean_text = option_text.strip()
            options_map[clean_text] = option_num
            if ". " in clean_text:
                _, stripped = clean_text.split(". ", 1)
                stripped = stripped.strip()
                if stripped:
                    options_map[stripped] = option_num

        data = {
            "question": question,
            "options": options_list,
            "options_map": options_map,
            "type": "permission",
        }

        return DetectionResult.success(data)

    def _extract_question(self, clean_buffer: str) -> str:
        """Extract the question text from the buffer, including context.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            Extracted question text with context, or empty string if not found
        """
        normalized_buffer = clean_buffer.replace("\r", "\n")
        lines = normalized_buffer.split("\n")
        best_question = ""
        best_score = float("-inf")
        best_index = 0

        # Look for "Do you want" line - search from end to get most recent
        for i in range(len(lines) - 1, -1, -1):
            raw_line = lines[i]
            line_clean = raw_line.strip().replace(self.BORDER_CHAR, "").strip()
            if self._is_separator_line(line_clean):
                continue

            if any(kw in line_clean for kw in self.PRIMARY_KEYWORDS):
                candidate = self._normalize_question_text(
                    self._extract_question_text(line_clean)
                )
                score = self._question_quality_score(candidate)
                # Prefer better quality; break ties in favor of more recent lines
                if score >= best_score:
                    best_score = score
                    best_question = candidate
                    best_index = i

        if best_question:
            self._question_line_idx = best_index
            # Extract context from lines above the question
            context = self._extract_context_above_question(lines, best_index)
            if context:
                return f"{context}\n\n{best_question}"
            return best_question

        # Fallback: no question phrase. Use the raw content block above the
        # options as the question. Generic — works for any tool/MCP server.
        fallback = self._build_question_from_content_block(lines)
        if fallback:
            content_start_idx, content = fallback
            self._question_line_idx = content_start_idx
            return content
        return ""

    def _extract_context_above_question(
        self, lines: List[str], question_idx: int
    ) -> str:
        """Extract meaningful context lines above the question.

        This captures rich context from the terminal that isn't in JSONL,
        such as skill descriptions, command details, etc.

        Args:
            lines: All buffer lines
            question_idx: Index of the question line

        Returns:
            Context text, or empty string if none found
        """
        context_lines: List[str] = []

        # Walk up to the box top — bounded by the outer separator, not a fixed
        # line count. Diffs can be 10-30 lines; capping at 3 would truncate
        # the box header and earlier diff hunks.
        start_idx = max(0, question_idx - 200)

        for i in range(question_idx - 1, start_idx - 1, -1):
            line = lines[i].strip().replace(self.BORDER_CHAR, "").strip()

            # Stop at the box-top separator (─). Pass through inner section
            # dividers (╌) — they sit between the tool header, optional diff/
            # content preview, and the question, and we want all sections.
            if self._is_separator_line(line) and len(line) > 20:
                if self._is_inner_separator_line(line):
                    continue
                break

            # Skip empty lines
            if not line:
                continue

            # Skip escape hints and navigation hints
            if any(
                hint in line.lower()
                for hint in [
                    "esc to cancel",
                    "tab to amend",
                    "escape to cancel",
                    "enter to select",
                    "tab/arrow keys",
                ]
            ):
                continue

            # Skip selection markers lines (options are handled separately)
            if line.startswith("❯") or line.startswith("▶"):
                continue

            # Don't filter generic OPTION_PATTERN matches here — content like
            # "1. First item" inside a file diff looks like an option but
            # isn't. Real options sit BELOW the question (we're walking up),
            # so we won't encounter them on this scan anyway.

            # Skip status indicators like "⏺ Skill(...)" or "⎿ Initializing"
            if line.startswith("⏺") or line.startswith("⎿"):
                continue

            # Keep diff/code content — for Edit/Overwrite permission prompts
            # this IS the meaningful context. Code-block formatting is applied
            # below in _format_lines_with_code_blocks.

            context_lines.insert(0, line)

        if context_lines:
            return self._format_lines_with_code_blocks(context_lines)

        return ""

    def _extract_options(self, clean_buffer: str) -> Dict[str, str]:
        """Extract numbered options from the buffer.

        Args:
            clean_buffer: Terminal buffer with ANSI codes removed

        Returns:
            Dictionary mapping option numbers to option text
        """
        normalized_buffer = clean_buffer.replace("\r", "\n")
        lines = normalized_buffer.split("\n")
        options_dict = {}

        # Scan a small look-behind window above the question line because terminal
        # redraws can place "1. Yes" immediately before the latest rendered question.
        question_idx = getattr(self, "_question_line_idx", 0)
        start_idx = max(0, question_idx - 4)

        # Look ahead up to 15 lines after the question (permission prompts are compact)
        end_idx = min(len(lines), question_idx + 15)

        # Find lines that look like numbered options within the relevant region.
        for i in range(start_idx, end_idx):
            line = lines[i]
            # Clean the line
            cleaned = line.strip().replace(self.BORDER_CHAR, "").strip()
            cleaned = self._strip_selection_marker(cleaned)
            if self._is_separator_line(cleaned):
                continue

            # Try to match numbered option pattern
            match = self.OPTION_PATTERN.match(cleaned)
            if match:
                option_num = match.group(1)
                option_text = self._normalize_option_text(match.group(2).strip())
                option_text = self._strip_trailing_prompt_hints(option_text)

                # Skip if this looks like metadata (e.g., "1. 2024-01-19")
                if option_text and not option_text[0].isdigit():
                    options_dict[option_num] = f"{option_num}. {option_text}"

        # Fallback for redraw artifacts where multiple numbered options can end up
        # on one physical line, or where direct scan misses option "1".
        if len(options_dict) < 2 or "1" not in options_dict:
            options_dict = self._extract_numbered_options_from_region(
                lines, start_idx, end_idx
            )

        # Final safeguard: if parsed options start from "2" for the canonical
        # permission menu, restore the missing primary "1. Yes" option.
        options_dict = self._ensure_primary_yes_option(options_dict)

        return options_dict

    def _extract_question_text(self, line: str) -> str:
        """Extract the question sentence from a noisy line."""
        for keyword in self.PRIMARY_KEYWORDS:
            if keyword in line:
                start_idx = line.find(keyword)
                if start_idx == -1:
                    continue
                candidate = line[start_idx:].strip()
                question_match = re.search(r"^.*?\?", candidate)
                return question_match.group(0).strip() if question_match else candidate
        return line.strip()

    def _normalize_question_text(self, text: str) -> str:
        """Normalize and repair common prompt corruption from terminal redraws."""
        cleaned = re.sub(r"\s+", " ", text).strip()

        # Fix common missing space before file path token
        cleaned = re.sub(
            r"\bto([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)\??$", r"to \1?", cleaned
        )

        # Terminal rendering should handle garbled text at the source
        # This normalization is only for minor cleanup

        return cleaned

    def _question_quality_score(self, question: str) -> float:
        """Score question candidates to avoid choosing corrupted redraw fragments."""
        if not question:
            return float("-inf")
        tokens = [token for token in question.split(" ") if token]
        long_joined_words = len(re.findall(r"[A-Za-z]{12,}", question))
        score = float(len(tokens))
        if question.endswith("?"):
            score += 10
        if "Do you want to " in question:
            score += 10
        if " make this edit to " in question:
            score += 10
        score -= long_joined_words * 3
        return score

    def _normalize_option_text(self, text: str) -> str:
        """Normalize option text and repair common spacing corruption."""
        cleaned = re.sub(r"\s+", " ", text).strip()
        collapsed = re.sub(r"\s+", "", cleaned)
        lowered_collapsed = collapsed.lower()
        # Preserve original casing while restoring spaces around punctuation.
        cleaned = re.sub(r",(?=\S)", ", ", cleaned)
        cleaned = re.sub(r"(?<=\w)\((?=\w)", " (", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if "allowalleditsduringthissession" in lowered_collapsed:
            if "shift+tab" in lowered_collapsed:
                return "Yes, allow all edits during this session (shift+tab)"
            return "Yes, allow all edits during this session"
        if not cleaned and collapsed:
            return collapsed
        return cleaned

    def _is_separator_line(self, line: str) -> bool:
        """Return True if the line is just a separator."""
        if not line:
            return True
        if self.SEPARATOR_PATTERN.match(line):
            return True
        alnum_count = sum(1 for c in line if c.isalnum())
        return alnum_count == 0 and len(line) > 10

    # Inner section dividers used INSIDE a permission box (e.g., between the
    # tool header, a diff preview, and the question). Distinct from the
    # box-top/bottom rule which uses ─. Passing through these during upward
    # scans lets us read all sections of the box.
    INNER_SEPARATOR_CHARS = frozenset("╌╍┄┅┈┉")

    def _is_inner_separator_line(self, line: str) -> bool:
        """Return True for inner section dividers (╌) — passable during upward scans."""
        if not line:
            return False
        return any(c in self.INNER_SEPARATOR_CHARS for c in line)

    # Recognises Claude CLI's line-numbered content lines (diff previews or
    # file-content panels, e.g., ``1 -Hi`` / ``2 +Hello`` / bare ``2`` for a
    # context-empty diff line).
    NUMBERED_CONTENT_PATTERN = re.compile(r"^\s*\d+(?:\s|$)")
    # Strips the leading "<line-number><optional-single-space>" prefix. The
    # ``\s?`` keeps additional indentation (e.g., the two-space indent on
    # "No newline at end of file" sub-notes) intact, and strips a bare line
    # number cleanly to an empty string.
    NUMBERED_PREFIX_STRIP = re.compile(r"^\s*\d+\s?")

    def _looks_like_file_path(self, line: str) -> bool:
        """Heuristic for whether a single line is a file path.

        File paths have no whitespace and contain at least one separator
        (``/`` or ``\\``) or extension dot. Used to attach a target path to
        the "Using tool: … - `path`" header when the tool header line ends
        with ``file``.
        """
        if not line:
            return False
        if any(c.isspace() for c in line):
            return False
        return "/" in line or "\\" in line or "." in line

    def _format_lines_with_code_blocks(self, lines: List[str]) -> str:
        """Format the box content with a tool-use header + single code block.

        Layout:
        - First line: ``🔧 Using tool: {first_line}``
        - If ``{first_line}`` ends with ``file`` and the second line looks
          like a file path, the path is appended as `` - `{path}` `` and
          excluded from the body so it doesn't clutter the code block.
        - Everything else goes into ONE contiguous code block. Numbered
          prefixes are stripped per line; non-numbered lines (sub-notes,
          descriptions, blank context lines) stay in the same block instead
          of breaking it into fragments. The fence is ``​```diff`` when any
          body line starts with ``+`` or ``-``, otherwise plain ``​````.
        """
        if not lines:
            return ""

        first_line = lines[0]
        header = f"🔧 Using tool: {first_line}"
        rest_start = 1

        if first_line.endswith("file") and len(lines) > 1:
            second = lines[1]
            if self._looks_like_file_path(second):
                header = f"🔧 Using tool: {first_line} - `{second}`"
                rest_start = 2

        remaining = lines[rest_start:]
        if not remaining:
            return header

        body: List[str] = []
        for line in remaining:
            if self.NUMBERED_CONTENT_PATTERN.match(line):
                body.append(self.NUMBERED_PREFIX_STRIP.sub("", line, count=1))
            else:
                body.append(line)

        fence_lang = "diff" if any(ln.startswith(("+", "-")) for ln in body) else ""
        return f"{header}\n```{fence_lang}\n" + "\n".join(body) + "\n```"

    def _strip_selection_marker(self, line: str) -> str:
        """Strip known selection markers from the start of an option line."""
        cleaned = self.SELECTION_MARKER_PATTERN.sub("", line)
        return cleaned.strip()

    def _has_numbered_options(self, clean_buffer: str) -> bool:
        """Check if the buffer contains at least two numbered options."""
        normalized_buffer = clean_buffer.replace("\r", "\n")
        lines = normalized_buffer.split("\n")
        found_numbers: set[str] = set()
        for line in lines:
            cleaned = line.strip().replace(self.BORDER_CHAR, "").strip()
            cleaned = self._strip_selection_marker(cleaned)
            if self._is_separator_line(cleaned):
                continue
            match = self.OPTION_PATTERN.match(cleaned)
            if match:
                found_numbers.add(match.group(1))
                if len(found_numbers) >= 2:
                    return True

        # Fallback for redraw artifacts where several numbered options share one line.
        region_numbers = re.findall(r"(?:^|\s)(\d+)[\.)]\s+", normalized_buffer)
        return len(set(region_numbers)) >= 2

    # The cursor indicator characters Claude CLI uses on a permission modal's
    # highlighted option. ASCII ``>`` is intentionally excluded — it appears
    # routinely as a prompt indicator and in prose, and would cause false
    # positives if checked at the buffer level.
    OPTION_MARKER_CHARS = frozenset("❯▶▸›»")

    # A real marked option for a permission modal is specifically ``❯ 1.`` —
    # Claude CLI always renders the modal with the cursor on option 1. The
    # user's input box also uses ``❯`` as a prompt indicator, so when they
    # type a line starting with a number it looks identical. By requiring
    # the marker to sit on ``1`` specifically, common cases like the user
    # typing ``3. Both`` are rejected outright (the rendered ``❯ 3. Both``
    # fails to match). Real-modal navigation (user pressing ↓ to highlight
    # 2/3) is rare in practice because the wrapper forwards selections via
    # the UI before the user can navigate.
    MARKED_OPTION_PATTERN = re.compile(r"^[\s​‎‏⁠]*[❯▶▸›»]+\s*1[\.)]\s+\S")

    # Companion check: a real modal has option ``2.`` immediately following
    # option 1 (only blank/separator lines between). User-typed ``❯ 1. foo``
    # in the input box does not.
    OPTION_2_PATTERN = re.compile(r"^[\s​‎‏⁠]*2[\.)]\s+\S")

    # Outer box corner chars used to bound the modal/input box. Hitting one
    # during the contiguity walk means we crossed the enclosing box's edge.
    BOX_CORNER_CHARS = frozenset("╭╮╰╯┌┐└┘")

    def _has_marked_option(self, clean_buffer: str) -> bool:
        """Return True only if a real permission modal is rendered.

        Three rules — all required:

        1. The ``❯`` marker sits on option **1** specifically. User input
           that happens to start with another digit (``❯ 3. Both`` from
           the user typing ``3. Both``) is rejected.
        2. Option ``2.`` follows within 5 lines below, before hitting a
           box corner. A real modal has at least two options; the input
           box has one user line.
        3. A question line — containing a primary keyword
           (``Do you want`` / ``Would you like`` / ``What do you want
           to do``) or ending with ``?`` — sits within 5 lines above the
           marker, before hitting a box corner. The user's input box has
           no question above the marker, just the box's top corner.

        Trade-off: misses modals where the user has navigated the cursor
        off option 1 (uncommon — the wrapper usually forwards a selection
        from the UI before the user touches the keyboard), and misses
        modals without a ``?``/keyword question (Write/Create variants
        that show only a tool header). Strict false-positive prevention
        is worth those misses because false positives silently corrupt
        the user's chat (their reply gets rewritten to an option number).
        """
        normalized = clean_buffer.replace("\r", "\n")
        lines = normalized.split("\n")
        for i, raw_line in enumerate(lines):
            cleaned = raw_line.strip().replace(self.BORDER_CHAR, "").strip()
            if not self.MARKED_OPTION_PATTERN.match(cleaned):
                continue
            if not self._has_option_2_below(lines, i):
                continue
            if not self._has_question_above(lines, i):
                continue
            return True
        return False

    def _has_option_2_below(self, lines: List[str], idx: int) -> bool:
        """Within 5 lines below ``idx``, find a line matching ``2. <text>``
        before hitting an outer box corner."""
        for j in range(idx + 1, min(len(lines), idx + 6)):
            line = lines[j].strip().replace(self.BORDER_CHAR, "").strip()
            if not line:
                continue
            if any(c in self.BOX_CORNER_CHARS for c in line):
                return False
            if self.OPTION_2_PATTERN.match(line):
                return True
        return False

    def _has_question_above(self, lines: List[str], idx: int) -> bool:
        """Within 5 lines above ``idx``, find a question line (PRIMARY
        keyword match or trailing ``?``) before hitting an outer box
        corner."""
        for j in range(idx - 1, max(-1, idx - 6), -1):
            line = lines[j].strip().replace(self.BORDER_CHAR, "").strip()
            if not line:
                continue
            if any(c in self.BOX_CORNER_CHARS for c in line):
                return False
            if any(kw in line for kw in self.PRIMARY_KEYWORDS):
                return True
            if line.rstrip().endswith("?"):
                return True
        return False

    def _extract_numbered_options_from_region(
        self, lines: List[str], start_idx: int, end_idx: int
    ) -> Dict[str, str]:
        """Fallback parser that extracts numbered options from a text region."""
        region = "\n".join(lines[start_idx:end_idx])
        region = region.replace(self.BORDER_CHAR, " ")
        region = self.SELECTION_MARKER_PATTERN.sub("", region)
        region = re.sub(r"\s+", " ", region)

        matches = list(re.finditer(r"(?:^|\s)(\d+)[\.)]\s+", region))
        if not matches:
            return {}

        parsed: Dict[str, str] = {}
        for idx, match in enumerate(matches):
            number = match.group(1)
            value_start = match.end()
            value_end = (
                matches[idx + 1].start() if idx + 1 < len(matches) else len(region)
            )
            option_text = region[value_start:value_end].strip()
            option_text = self._normalize_option_text(option_text)
            option_text = self._strip_trailing_prompt_hints(option_text)
            if option_text and not option_text[0].isdigit():
                parsed[number] = f"{number}. {option_text}"

        return parsed

    def _ensure_primary_yes_option(
        self, options_dict: Dict[str, str]
    ) -> Dict[str, str]:
        """Add missing option 1 only when options clearly start from 2 for permission UI."""
        if "1" in options_dict or "2" not in options_dict:
            return options_dict

        numeric_keys = sorted(
            [int(key) for key in options_dict.keys() if str(key).isdigit()]
        )
        if not numeric_keys or numeric_keys[0] != 2:
            return options_dict

        option2 = options_dict.get("2", "").lower()
        option3 = options_dict.get("3", "").lower()
        option2_matches = option2.startswith("2. yes")
        option3_matches = (not option3) or option3.startswith("3. no")
        if option2_matches and option3_matches:
            options_dict["1"] = "1. Yes"

        return options_dict

    def _strip_trailing_prompt_hints(self, text: str) -> str:
        """Strip terminal hint suffixes accidentally captured in option text."""
        lowered = text.lower()
        compact = re.sub(r"[^a-z0-9]+", "", lowered)
        for marker in (
            "(esc to cancel)",
            "(escape to cancel)",
            "esc to cancel",
            "escape to cancel",
            "enter to select",
            "tab/arrow keys to navigate",
            "tab to amend",
        ):
            idx = lowered.find(marker)
            if idx != -1:
                return text[:idx].strip()
        # Handle redraw artifacts where whitespace/punctuation is stripped.
        compact_markers = (
            "esctocancel",
            "escapetocancel",
            "entertoselect",
            "tabarrowkeystonavigate",
            "tabtoamend",
        )
        cut_points = [compact.find(marker) for marker in compact_markers]
        cut_points = [pos for pos in cut_points if pos != -1]
        if cut_points:
            first = min(cut_points)
            # Build a compact->original index map and cut at matching original char
            map_idx: list[int] = []
            for i, ch in enumerate(text):
                if ch.isalnum():
                    map_idx.append(i)
            if first < len(map_idx):
                return text[: map_idx[first]].strip()
        return text

    def _build_question_from_content_block(
        self, lines: List[str]
    ) -> Optional[tuple[int, str]]:
        """Extract the content block above the options as the question.

        Used when no question phrase is present (e.g., Write/Create permission
        prompts that render only a tool header + target above the options).
        Generic — no enumeration of tool names. Walks upward from the first
        option line, skipping blanks/hints/option markers, and stops at the
        first separator row.

        Returns:
            (content_start_idx, content_text) or None if no usable block.
        """
        # Anchor on the most recent option line.
        options_anchor = None
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip().replace(self.BORDER_CHAR, "").strip()
            line = self._strip_selection_marker(line)
            if self.OPTION_PATTERN.match(line):
                options_anchor = i
                break
        if options_anchor is None:
            return None

        # Walk past contiguous options/blanks to find the FIRST option line.
        first_option_idx = options_anchor
        for i in range(options_anchor - 1, max(-1, options_anchor - 10), -1):
            line = lines[i].strip().replace(self.BORDER_CHAR, "").strip()
            if not line:
                continue
            stripped = self._strip_selection_marker(line)
            if self.OPTION_PATTERN.match(stripped):
                first_option_idx = i
                continue
            break

        # Collect content above the options, stopping at a separator row.
        content_lines: List[str] = []
        content_start_idx = first_option_idx
        hint_markers = (
            "esc to cancel",
            "tab to amend",
            "escape to cancel",
            "enter to select",
            "tab/arrow keys",
        )
        for i in range(first_option_idx - 1, max(-1, first_option_idx - 40), -1):
            line = lines[i].strip().replace(self.BORDER_CHAR, "").strip()
            if not line:
                continue
            if self._is_separator_line(line) and len(line) > 20:
                # Inner section dividers (╌) sit between sections of the box
                # (header, diff preview, file content). Always pass through.
                if self._is_inner_separator_line(line):
                    continue
                # Outer separator (─) = top of box. If we have no content yet
                # this is a degenerate case; either way we stop here.
                if content_lines:
                    content_start_idx = i + 1
                break
            # Real options are recognised by the selection-marker prefix (❯/▶).
            # Generic OPTION_PATTERN matches (e.g., "1. First item" inside a
            # file diff) shouldn't be filtered — we're already above
            # first_option_idx, so the real option block is out of range.
            if line.startswith("❯") or line.startswith("▶"):
                continue
            if any(hint in line.lower() for hint in hint_markers):
                continue
            content_lines.insert(0, line)
            if len(content_lines) >= 20:  # safety cap
                break

        if not content_lines:
            return None

        return content_start_idx, self._format_lines_with_code_blocks(content_lines)

    def _find_question_line_index(self, lines: List[str]) -> Optional[int]:
        """Find the index of the line containing the question.

        Args:
            lines: List of buffer lines

        Returns:
            Index of question line, or None if not found
        """
        for i in range(len(lines) - 1, -1, -1):
            line_clean = lines[i].strip().replace(self.BORDER_CHAR, "").strip()
            if any(kw in line_clean for kw in self.PRIMARY_KEYWORDS):
                return i
        return None

    def _find_options_region(
        self, lines: List[str], question_idx: int
    ) -> Optional[tuple[int, int]]:
        """Find the region containing option lines.

        Args:
            lines: List of buffer lines
            question_idx: Index of the question line

        Returns:
            Tuple of (start_idx, end_idx) for options region, or None
        """
        # Look for options after the question (up to 10 lines)
        start_idx = question_idx + 1
        end_idx = min(len(lines), question_idx + 11)

        # Verify we have at least one option in this region
        for i in range(start_idx, end_idx):
            cleaned = lines[i].strip().replace(self.BORDER_CHAR, "").strip()
            if self.OPTION_PATTERN.match(cleaned):
                return (start_idx, end_idx)

        return None

    def get_patterns(self) -> Dict[str, str]:
        """Get the patterns used by this detector.

        Returns:
            Dictionary of pattern names to pattern strings
        """
        return {
            "primary_keywords": str(self.PRIMARY_KEYWORDS),
            "esc_hint": self.ESC_HINT,
            "esc_cancel": self.ESC_CANCEL,
            "escape_cancel": self.ESCAPE_CANCEL,
            "option_pattern": self.OPTION_PATTERN.pattern,
        }
