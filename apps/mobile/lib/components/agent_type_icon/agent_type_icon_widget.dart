import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '/backend/acp_provider_icons.dart';
import '/flutter_flow/flutter_flow_theme.dart';

// Luminance-weighted grayscale; paired with 50% opacity to gray out the logo of
// a closed/archived session (mirrors the web's `opacity-50 grayscale`).
const List<double> _grayscaleMatrix = <double>[
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0, 0, 0, 1, 0, //
];

const _agentLogos = [
  _AgentLogo(match: 'claude', asset: 'assets/images/integrations/claude-color.svg', invertInDark: false),
  _AgentLogo(match: 'codex', asset: 'assets/images/integrations/openai.svg', invertInDark: true),
  _AgentLogo(match: 'opencode', asset: 'assets/images/integrations/opencode.svg', lightAsset: 'assets/images/integrations/opencode-logo-light.svg', invertInDark: false),
  _AgentLogo(match: 'gemini', asset: 'assets/images/integrations/gemini-color.svg', invertInDark: false),
  _AgentLogo(match: 'cursor', asset: 'assets/images/integrations/cursor.svg', invertInDark: true),
  _AgentLogo(match: 'copilot', asset: 'assets/images/integrations/copilot.svg', invertInDark: true),
  _AgentLogo(match: 'kimi', asset: 'assets/images/integrations/kimi-color.svg', invertInDark: false),
  // Hermes is a dark `currentColor` glyph: render it as-is (dark, no
  // background) in light mode, and on a white rounded-square chip in dark mode
  // — instead of inverting it to a bare white glyph that loses its detail.
  _AgentLogo(match: 'hermes', asset: 'assets/images/integrations/hermes.svg', invertInDark: false, boxedWhiteInDark: true),
  // ORDER MATTERS BELOW. Matching is `name.contains(logo.match)` over this list
  // in order, and 'pi' is a substring of 'copilot' — a bare 'pi' entry placed
  // any earlier would swallow Copilot. Keep 'omp'/'oh my pi' ahead of it, and
  // keep 'pi' LAST. Mirrors the same ordering rule in the web's AGENT_LOGOS.
  _AgentLogo(match: 'oh my pi', asset: 'assets/images/integrations/omp.svg', invertInDark: true),
  _AgentLogo(match: 'omp', asset: 'assets/images/integrations/omp.svg', invertInDark: true),
  _AgentLogo(match: 'pi', asset: 'assets/images/integrations/pi.svg', invertInDark: true),
];

class _AgentLogo {
  final String match;
  final String asset;
  final String? lightAsset;
  final bool invertInDark;
  // When true, in dark mode the (non-inverted) glyph is centered on a white
  // rounded square so a dark logo stays legible against the dark UI.
  final bool boxedWhiteInDark;
  const _AgentLogo({required this.match, required this.asset, this.lightAsset, required this.invertInDark, this.boxedWhiteInDark = false});
}

_AgentLogo? _getLogo(String? agentTypeName) {
  if (agentTypeName == null) return null;
  final name = agentTypeName.toLowerCase();
  for (final logo in _agentLogos) {
    if (name.contains(logo.match)) return logo;
  }
  return null;
}

// Generated fallback for a user-defined provider (`agents.providers` in
// ~/.vicoa/config.json). Those agents have no brand mark and never will — the
// point of the feature is that adding one costs no client release. Palette and
// hash mirror `apps/web/lib/project-icons.ts` exactly, so the same custom agent
// gets the same colour on web and mobile.
const List<Color> _generatedAvatarPalette = <Color>[
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

// paseo's hashIdentityKey (hash*31 + charCode), masked to 32 bits unsigned to
// match JavaScript's `>>> 0`.
int _hashIdentity(String seed) {
  var hash = 0;
  for (final unit in seed.runes) {
    hash = (hash * 31 + unit) & 0xFFFFFFFF;
  }
  return hash;
}

Color _generatedAvatarColor(String seed) =>
    _generatedAvatarPalette[_hashIdentity(seed) % _generatedAvatarPalette.length];

String _generatedInitial(String name) {
  final trimmed = name.trim();
  return trimmed.isEmpty ? '\u00B7' : String.fromCharCode(trimmed.runes.first).toUpperCase();
}

/// Whether [AgentTypeIconWidget] has an actual rounded logo for
/// [agentTypeName] — i.e. whether it would render something rather than
/// [SizedBox.shrink]. Lets callers fall back to a generic icon instead of
/// rendering nothing when the agent type is unknown.
bool agentTypeHasLogo(String? agentTypeName) =>
    _getLogo(agentTypeName) != null || acpIconAsset(agentTypeName) != null;

/// Displays an agent type logo (Claude, Codex, OpenCode).
/// Pass [spinning] = true for active sessions to render a thin rotating arc
/// around the logo. Pass [withBackground] = true to wrap the logo in a subtle
/// circular avatar background; the ring (when spinning) hugs that circle's edge.
/// Pass [muted] = true to gray out the glyph (grayscale + 50% opacity) for a
/// closed/archived session.
class AgentTypeIconWidget extends StatelessWidget {
  const AgentTypeIconWidget({
    super.key,
    required this.agentTypeName,
    this.size = 14.0,
    this.spinning = false,
    this.withBackground = false,
    this.muted = false,
  });

  final String? agentTypeName;
  final double size;
  final bool spinning;
  final bool withBackground;
  final bool muted;

  static const double ringPadding = 13.0;
  static const double _ringStroke = 1.5;

  @override
  Widget build(BuildContext context) {
    // Catalog agents first, and by EXACT key: `_agentLogos` matches on
    // `name.contains`, which is fine for ten hand-picked marks and would not be
    // for another thirty — `kilo`/`kiro`, `nova` and `grok` are all substrings
    // waiting to collide.
    final acpAsset = acpIconAsset(agentTypeName);
    if (acpAsset != null) {
      // Single-colour glyphs authored with `fill="currentColor"`, which
      // flutter_svg renders black; tint them with the body text colour so they
      // read on both themes, matching the web's CSS-mask treatment.
      return _buildWrapped(
        context,
        SvgPicture.asset(
          acpAsset,
          width: size,
          height: size,
          colorFilter: ColorFilter.mode(
            FlutterFlowTheme.of(context).primaryText,
            BlendMode.srcIn,
          ),
        ),
      );
    }

    final logo = _getLogo(agentTypeName);
    if (logo == null) {
      final name = agentTypeName;
      if (name == null || name.trim().isEmpty) return const SizedBox.shrink();
      return _buildWrapped(
        context,
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: _generatedAvatarColor(name.toLowerCase()),
            borderRadius: BorderRadius.circular(size * 0.24),
          ),
          child: Text(
            _generatedInitial(name),
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: size * 0.56,
              height: 1,
            ),
          ),
        ),
      );
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final needsInvert = logo.invertInDark && isDark;
    final boxedWhite = logo.boxedWhiteInDark && isDark;
    final resolvedAsset = (!isDark && logo.lightAsset != null) ? logo.lightAsset! : logo.asset;

    // Shrink the glyph inside the white chip so it keeps a little breathing
    // room from the rounded edges; otherwise the logo fills `size` as usual.
    final glyphSize = boxedWhite ? size * 0.82 : size;

    final rawSvg = SvgPicture.asset(
      resolvedAsset,
      width: glyphSize,
      height: glyphSize,
      colorFilter: needsInvert
          ? const ColorFilter.matrix([
              -1, 0, 0, 0, 255,
              0, -1, 0, 0, 255,
              0, 0, -1, 0, 255,
              0, 0, 0, 1, 0,
            ])
          : null,
    );

    final baseSvg = boxedWhite
        ? Container(
            width: size,
            height: size,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(size * 0.24),
            ),
            child: rawSvg,
          )
        : rawSvg;

    return _buildWrapped(context, baseSvg);
  }

  /// Applies the shared presentation — muted grayscale, the avatar circle and
  /// the spinning ring — to [glyph]. Shared by the real logos and by the
  /// generated initial-square a user-defined provider falls back to, so the two
  /// can never drift apart.
  Widget _buildWrapped(BuildContext context, Widget glyph) {
    final svg = muted
        ? Opacity(
            opacity: 0.5,
            child: ColorFiltered(
              colorFilter: const ColorFilter.matrix(_grayscaleMatrix),
              child: glyph,
            ),
          )
        : glyph;

    if (withBackground) {
      final circleSize = size + ringPadding * 2;
      return SizedBox(
        width: circleSize,
        height: circleSize,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Container(
              width: circleSize,
              height: circleSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: FlutterFlowTheme.of(context)
                    .primaryText
                    .withValues(alpha: 0.06),
              ),
            ),
            svg,
            if (spinning)
              SizedBox(
                width: circleSize,
                height: circleSize,
                child: CircularProgressIndicator(
                  strokeWidth: _ringStroke,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    FlutterFlowTheme.of(context).secondaryText.withValues(
                          alpha: Theme.of(context).brightness == Brightness.light
                              ? 0.4
                              : 0.6,
                        ),
                  ),
                ),
              ),
          ],
        ),
      );
    }

    if (!spinning) return svg;

    final outerSize = size + ringPadding * 2;
    return SizedBox(
      width: outerSize,
      height: outerSize,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: outerSize,
            height: outerSize,
            child: CircularProgressIndicator(
              strokeWidth: _ringStroke,
              valueColor: AlwaysStoppedAnimation<Color>(
                FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.4),
              ),
            ),
          ),
          svg,
        ],
      ),
    );
  }
}
