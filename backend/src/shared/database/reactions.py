"""What counts as an emoji.

`task_reactions.emoji` is a free varchar and the client can send anything the
full Unicode picker offers — skin-tone modifiers, ZWJ sequences, flags. So the
server can't check membership in a list, but it must still check *shape*:
without this, the column accepts "please click here" and the reaction row
becomes a text-injection surface rather than a pill.

The rule is deliberately structural rather than a codepoint whitelist (which
goes stale with every Unicode release): an emoji is short, contains no ASCII
letters, digits or whitespace, and has at least one character outside the
Latin-1 range.
"""

MAX_EMOJI_LENGTH = 16

# Joiners and modifiers that legitimately appear inside a single emoji and are
# themselves below the "must be exotic" bar.
_COMBINING = {
    "‍",  # zero-width joiner (👨‍👩‍👧)
    "️",  # variation selector-16 (❤️)
    "︎",  # variation selector-15
}


def is_emoji(value: str) -> bool:
    """True when `value` is plausibly a single emoji grapheme."""
    if not value or len(value) > MAX_EMOJI_LENGTH:
        return False
    saw_exotic = False
    for char in value:
        if char in _COMBINING:
            continue
        if char.isalnum() and char.isascii():
            return False
        if char.isspace():
            return False
        if ord(char) > 0xFF:
            saw_exotic = True
    return saw_exotic
