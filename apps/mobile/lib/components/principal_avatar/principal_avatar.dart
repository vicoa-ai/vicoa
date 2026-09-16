import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '/backend/supabase/supabase.dart';
import '/custom_code/actions/vicoa_api_config.dart';
import '/flutter_flow/flutter_flow_theme.dart';

/// PrincipalAvatar — the Flutter twin of
/// `apps/web/components/ui/principal-avatar.tsx` (collaboration P0).
///
/// One widget, three principal types (user, team, agent), three fallback
/// levels:
///   1. the stored image, fetched from our own backend with the session bearer;
///   2. initials on the deterministic hash-palette color;
///   3. a generic per-type glyph, when there is no name to make initials from.
///
/// The palette and the hash are copied verbatim from
/// `apps/web/lib/project-icons.ts`, so a principal gets the same color on every
/// platform. Nothing else in the app should draw an avatar.
enum PrincipalType { user, team, agent }

/// Web's `xs | sm | md | lg | xl`, in logical pixels.
enum PrincipalAvatarSize { xs, sm, md, lg, xl }

/// Box size, plus the initial's and the emoji's type sizes, mirroring the SIZES
/// table in
/// apps/web/components/ui/principal-avatar.tsx one-for-one. The letter runs
/// ~0.25-0.30 of the box (higher at the small end only because 16px has a
/// legibility floor) so the monogram reads as a mark rather than filling the
/// circle. Change one table, change the other.
/// An emoji is a picture, not a letter: it reads at roughly twice the type size
/// a monogram wants, so it gets its own column.
const Map<PrincipalAvatarSize, ({double box, double text, double emoji})>
    _metrics = {
  PrincipalAvatarSize.xs: (box: 16.0, text: 8.0, emoji: 10.0),
  PrincipalAvatarSize.sm: (box: 24.0, text: 9.0, emoji: 14.0),
  PrincipalAvatarSize.md: (box: 32.0, text: 11.0, emoji: 18.0),
  PrincipalAvatarSize.lg: (box: 56.0, text: 16.0, emoji: 30.0),
  PrincipalAvatarSize.xl: (box: 80.0, text: 20.0, emoji: 48.0),
};

/// paseo's IDENTITY_COLORS — muted tones tuned for a white letter on top.
/// Keep in sync with PROJECT_AVATAR_PALETTE in apps/web/lib/project-icons.ts.
const List<Color> kIdentityPalette = [
  Color(0xFF7A6AA8), // violet
  Color(0xFF3D7EA6), // sky
  Color(0xFF388068), // emerald
  Color(0xFFA4673A), // orange
  Color(0xFFB05C80), // pink
  Color(0xFF6A70B8), // indigo
  Color(0xFF368080), // teal
  Color(0xFFB06260), // red
  Color(0xFF8F7838), // amber
  Color(0xFF5179B0), // blue
];

/// paseo's hashIdentityKey (hash*31 + charCode, unsigned 32-bit) — the web
/// version relies on JS `>>> 0`, so mask to 32 bits here to match exactly.
int _hashString(String seed) {
  int hash = 0;
  for (final unit in seed.runes) {
    hash = (hash * 31 + unit) & 0xFFFFFFFF;
  }
  return hash;
}

Color identityColor(String seed) =>
    kIdentityPalette[_hashString(seed) % kIdentityPalette.length];

/// A principal's single initial, or null when there is no name.
///
/// One letter, not two: a monogram reads as a mark at any size, while "AL" in a
/// 24px circle is two shapes fighting for the same space. `runes` (not
/// `codeUnits`) so an emoji or an astral-plane name is not sliced in half.
String? principalInitial(String? name) {
  final trimmed = (name ?? '').trim();
  if (trimmed.isEmpty) return null;
  return String.fromCharCode(trimmed.runes.first).toUpperCase();
}

class PrincipalAvatar extends StatelessWidget {
  const PrincipalAvatar({
    super.key,
    required this.type,
    this.id,
    this.name,
    this.avatarImageUri,
    this.emoji,
    this.updatedAt,
    this.size = PrincipalAvatarSize.md,
  });

  final PrincipalType type;

  /// Stable id — seeds the fallback color and addresses the stored image.
  final String? id;

  /// Display name — the seed for initials. On a shared or public surface this
  /// must be a display name and nothing else: an email may never appear there
  /// (P0 privacy rule). In the signed-in user's own chrome, falling back to
  /// their own email for an initial is fine.
  final String? name;

  /// Backend-relative served URL (e.g. `users.avatar_image_uri`), or null.
  final String? avatarImageUri;

  /// A picked emoji, rendered when there is no image — between the image and
  /// the generated initial, so clearing a photo reveals an emoji chosen
  /// earlier rather than discarding it.
  final String? emoji;

  /// Cache-buster — the row's `updated_at`; the avatar URL itself is stable.
  final String? updatedAt;

  final PrincipalAvatarSize size;

  double get _px => _metrics[size]!.box;
  double get _textPx => _metrics[size]!.text;
  double get _emojiPx => _metrics[size]!.emoji;

  /// Every principal is a circle. Agents used to be square-ish ("a thing, not a
  /// face"), but every editor affordance drawn on an avatar is round, so the
  /// distinction only produced a hover state that did not fit. Web made the
  /// same change — keep the two in step.
  BorderRadius get _radius => BorderRadius.circular(_px / 2);

  IconData get _glyph {
    switch (type) {
      case PrincipalType.team:
        return Icons.groups_rounded;
      case PrincipalType.agent:
        return Icons.smart_toy_outlined;
      case PrincipalType.user:
        return Icons.person_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: _radius,
      child: SizedBox(
        width: _px,
        height: _px,
        child: _content(context),
      ),
    );
  }

  Widget _content(BuildContext context) {
    // Only users have stored images today; teams (P3) and agents (P1) reuse
    // this widget for their initials/glyph until they do.
    if (type == PrincipalType.user && id != null && (avatarImageUri ?? '').isNotEmpty) {
      // The URL is stable across replacements, so `updated_at` is both the
      // cache-buster and the disk-cache key.
      final version = updatedAt == null ? '' : '?v=${Uri.encodeComponent(updatedAt!)}';
      final url = '${getVicoaApiBaseUrl()}/api/v1/users/$id/avatar$version';
      final token = SupaFlow.client.auth.currentSession?.accessToken ?? '';
      return CachedNetworkImage(
        imageUrl: url,
        httpHeaders: {'Authorization': 'Bearer $token'},
        fit: BoxFit.cover,
        placeholder: (context, _) => _fallback(context),
        errorWidget: (context, _, __) => _fallback(context),
      );
    }
    return _fallback(context);
  }

  Widget _fallback(BuildContext context) {
    final pickedEmoji = (emoji ?? '').trim();
    if (pickedEmoji.isNotEmpty) {
      // Neutral, not the hash-palette colour the initial uses: an emoji already
      // carries its own colour. Matches the web.
      return Container(
        color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.4),
        alignment: Alignment.center,
        child: Text(
          pickedEmoji,
          style: TextStyle(height: 1.0, fontSize: _emojiPx),
        ),
      );
    }
    final initial = principalInitial(name);
    if (initial != null) {
      return Container(
        color: identityColor(id?.isNotEmpty == true ? id! : name!),
        alignment: Alignment.center,
        child: Text(
          initial,
          style: TextStyle(
            color: Colors.white,
            // Matches the web's font-normal — a heavier monogram reads as a
            // badge rather than as identity.
            fontWeight: FontWeight.w400,
            height: 1.0,
            fontSize: _textPx,
          ),
        ),
      );
    }
    final theme = FlutterFlowTheme.of(context);
    return Container(
      color: theme.alternate.withValues(alpha: 0.4),
      alignment: Alignment.center,
      child: Icon(_glyph, size: _px * 0.55, color: theme.secondaryText),
    );
  }
}
