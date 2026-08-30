// Floating bottom tab bar in the current Apple style: a translucent,
// heavily-rounded capsule that floats above the content with a blurred
// glass background and a sliding highlight behind the selected tab.
// Content scrolls behind it; scrollables on tab pages should pad their
// bottom by [floatingTabBarBottomInset].

import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';

const double kFloatingTabBarHeight = 62.0;
const double kFloatingTabBarBottomMargin = 10.0;

/// Fixed width per tab — the bar shrink-wraps to its items instead of
/// stretching edge-to-edge.
const double _kTabItemWidth = 64.0;

/// Bottom padding a scrollable needs so its last item can clear the floating
/// bar (bar height + margins + home-indicator inset + breathing room).
double floatingTabBarBottomInset(BuildContext context) =>
    kFloatingTabBarHeight +
    kFloatingTabBarBottomMargin +
    MediaQuery.of(context).padding.bottom +
    16.0;

class FloatingTabItem {
  const FloatingTabItem({
    required this.icon,
    required this.selectedIcon,
    required this.label,
    this.iconSize = 24.0,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;

  /// Per-item icon size. Lets a heavier glyph (e.g. a FontAwesome icon) be
  /// dialed down so it reads at the same optical size as the Material icons.
  final double iconSize;
}

class FloatingTabBar extends StatelessWidget {
  const FloatingTabBar({
    super.key,
    required this.items,
    required this.currentIndex,
    required this.onTap,
  });

  final List<FloatingTabItem> items;
  final int currentIndex;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    const radius = kFloatingTabBarHeight / 2;

    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        0.0,
        0.0,
        0.0,
        kFloatingTabBarBottomMargin + MediaQuery.of(context).padding.bottom,
      ),
      child: Container(
        height: kFloatingTabBarHeight,
        width: _kTabItemWidth * items.length + 10.0,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(radius),
          boxShadow: [
            // Tight contact shadow — keeps the pill's edge crisp even when a
            // same-colored session/task card scrolls directly behind it.
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.5 : 0.16),
              blurRadius: 10.0,
              offset: const Offset(0.0, 4.0),
            ),
            // Ambient shadow — the soft "float".
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.32 : 0.1),
              blurRadius: 30.0,
              offset: const Offset(0.0, 14.0),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(radius),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 24.0, sigmaY: 24.0),
            child: Container(
              decoration: BoxDecoration(
                // Dark mode: black blended into the card color for a deep
                // frosted surface. Light mode: near-white glass instead of a
                // black blend — blending black into the pale background read
                // as a muddy grey chip rather than clean frosted glass. The
                // bright rim/dark edge + contact shadow keep the pill
                // separated from any same-colored card scrolling behind.
                color: isDark
                    ? Color.alphaBlend(
                            Colors.black.withValues(alpha: 0.34),
                            theme.primaryBackground)
                        .withValues(alpha: 0.92)
                    : Colors.white.withValues(alpha: 0.82),
                borderRadius: BorderRadius.circular(radius),
                border: Border.all(
                  // Bright rim in dark (catches light like glass); a faint dark
                  // edge in light so the pill reads against grey cards too.
                  color: isDark
                      ? Colors.white.withValues(alpha: 0.16)
                      : Colors.black.withValues(alpha: 0.06),
                  width: 1.0,
                ),
              ),
              padding: const EdgeInsets.all(5.0),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final itemWidth = constraints.maxWidth / items.length;
                  return Stack(
                    children: [
                      // Sliding highlight capsule behind the selected tab —
                      // neutral white/gray (iOS-style thumb), not tinted.
                      AnimatedPositioned(
                        duration: const Duration(milliseconds: 260),
                        curve: Curves.easeOutCubic,
                        left: itemWidth * currentIndex,
                        top: 0.0,
                        bottom: 0.0,
                        width: itemWidth,
                        child: Container(
                          decoration: BoxDecoration(
                            color: isDark
                                ? Colors.white.withValues(alpha: 0.14)
                                : Colors.white.withValues(alpha: 0.85),
                            borderRadius: BorderRadius.circular(radius - 5.0),
                            border: Border.all(
                              color: theme.alternate
                                  .withValues(alpha: isDark ? 0.3 : 0.7),
                              width: 0.5,
                            ),
                            boxShadow: isDark
                                ? null
                                : [
                                    BoxShadow(
                                      color: Colors.black
                                          .withValues(alpha: 0.08),
                                      blurRadius: 6.0,
                                      offset: const Offset(0.0, 2.0),
                                    ),
                                  ],
                          ),
                        ),
                      ),
                      Row(
                        children: [
                          for (var i = 0; i < items.length; i++)
                            Expanded(child: _tabItem(context, theme, i)),
                        ],
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _tabItem(BuildContext context, FlutterFlowTheme theme, int index) {
    final selected = index == currentIndex;
    final color = selected ? theme.primaryText : theme.secondaryText;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        HapticFeedback.selectionClick();
        if (index != currentIndex) onTap(index);
      },
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AnimatedScale(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutBack,
            scale: selected ? 1.06 : 1.0,
            child: Icon(
              selected ? items[index].selectedIcon : items[index].icon,
              size: items[index].iconSize,
              color: color,
            ),
          ),
          // const SizedBox(height: 2.0),
          // Text(
          //   items[index].label,
          //   maxLines: 1,
          //   overflow: TextOverflow.ellipsis,
          //   style: theme.bodySmall.override(
          //     font: GoogleFonts.sourceSans3(),
          //     fontSize: 11.0,
          //     letterSpacing: 0.0,
          //     fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          //     color: color,
          //   ),
          // ),
        ],
      ),
    );
  }
}
