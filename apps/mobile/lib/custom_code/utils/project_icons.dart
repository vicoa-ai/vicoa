// Project icon helpers — the generated-fallback half of the web's
// `lib/project-icons.ts`, ported so a project looks the same on the phone as
// on the laptop. Pure Dart (no Flutter imports) so it unit-tests cheaply.

/// Fixed palette for the generated initial-square: paseo's `IDENTITY_COLORS`,
/// muted low-chroma tones tuned to one contrast band against a white letter,
/// so the color *identifies* a project without shouting. Order matters — the
/// hash indexes into it and must land on the same entry as the web.
const List<int> kProjectAvatarPalette = [
  0xFF7A6AA8, // violet
  0xFF3D7EA6, // sky
  0xFF388068, // emerald
  0xFFA4673A, // orange
  0xFFB05C80, // pink
  0xFF6A70B8, // indigo
  0xFF368080, // teal
  0xFFB06260, // red
  0xFF8F7838, // amber
  0xFF5179B0, // blue
];

/// paseo's `hashIdentityKey` (`hash * 31 + charCode`, unsigned 32-bit), kept
/// bit-for-bit compatible with the web so the mapping matches. The web walks
/// code points and takes each one's first UTF-16 unit; mirrored here even
/// though a seed is a UUID in practice.
int projectIdentityHash(String seed) {
  var hash = 0;
  for (final rune in seed.runes) {
    final unit = rune > 0xFFFF ? 0xD800 + ((rune - 0x10000) >> 10) : rune;
    hash = (hash * 31 + unit) & 0xFFFFFFFF;
  }
  return hash;
}

/// Deterministic palette color (ARGB) for a project, seeded by its id.
int projectAvatarColor(String seed) =>
    kProjectAvatarPalette[projectIdentityHash(seed) % kProjectAvatarPalette.length];

/// First visible character of a name, uppercased — the generated initial.
/// `·` when there is nothing to show.
String projectInitial(String? name) {
  final trimmed = (name ?? '').trim();
  if (trimmed.isEmpty) return '·';
  return String.fromCharCode(trimmed.runes.first).toUpperCase();
}
