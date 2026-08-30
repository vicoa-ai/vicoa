import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

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

/// Whether [AgentTypeIconWidget] has an actual rounded logo for
/// [agentTypeName] — i.e. whether it would render something rather than
/// [SizedBox.shrink]. Lets callers fall back to a generic icon instead of
/// rendering nothing when the agent type is unknown.
bool agentTypeHasLogo(String? agentTypeName) => _getLogo(agentTypeName) != null;

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
    final logo = _getLogo(agentTypeName);
    if (logo == null) return const SizedBox.shrink();

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

    final svg = muted
        ? Opacity(
            opacity: 0.5,
            child: ColorFiltered(
              colorFilter: const ColorFilter.matrix(_grayscaleMatrix),
              child: baseSvg,
            ),
          )
        : baseSvg;

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
