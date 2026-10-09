import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import 'home_model.dart' show localizedFilterLabel;
import 'project_group_icon.dart';
import 'project_groups.dart';

/// The tappable header above each Home group: a project group leads with its
/// icon (see [ProjectGroupIcon]), then the title and a chevron that turns as
/// the group collapses. [large] is the Project/Status size.
class HomeGroupHeader extends StatelessWidget {
  const HomeGroupHeader({
    super.key,
    required this.group,
    required this.collapsed,
    required this.large,
    required this.onTap,
  });

  final SessionGroup group;
  final bool collapsed;
  final bool large;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    // A project's name is shown as is; the fixed group names (time, status,
    // Pinned, No project) are translated.
    final title = group.isProject && !group.isNoProject
        ? group.label
        : localizedFilterLabel(group.label);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(6.0, 6.0, 0.0, 8.0),
        child: Row(
          children: [
            if (group.isProject) ...[
              ProjectGroupIcon(group: group, open: !collapsed),
              const SizedBox(width: 8.0),
            ],
            Flexible(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.titleMedium.override(
                  fontSize: large ? 17.0 : 16.0,
                  color: theme.secondaryText,
                ),
              ),
            ),
            const SizedBox(width: 4.0),
            AnimatedRotation(
              turns: collapsed ? -0.25 : 0.0,
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              child: Icon(
                Icons.expand_more_rounded,
                color: theme.secondaryText,
                size: large ? 20.0 : 18.0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
