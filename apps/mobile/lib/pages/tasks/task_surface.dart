import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';

/// The chat page's neutral surface, for the task sheet's tags, pills and
/// comment box: the fill and edge of the chat's input area and send button
/// (`chat_input_area.dart`, `composer_primary_button.dart`), in the theme's
/// plain text colours and no accent hue. [strong] is the selected state (a
/// reaction you added): the same surface, a step darker.
BoxDecoration taskChatSurface(FlutterFlowTheme theme, {double radius = 10.0, bool strong = false}) => BoxDecoration(
      color: theme.secondaryText.withValues(alpha: strong ? 0.14 : 0.05),
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(color: theme.secondaryText.withValues(alpha: strong ? 0.4 : 0.2), width: 1.0),
    );
