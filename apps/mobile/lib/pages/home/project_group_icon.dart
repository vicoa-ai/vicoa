import 'package:flutter/material.dart';

import '/components/principal_avatar/principal_avatar.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/pages/tasks/task_glyphs.dart';
import 'project_groups.dart';

/// The leading icon of a Home project group header, as the web sidebar draws
/// it: the project's image or emoji, else a folder that opens with the group,
/// a dashed square for No project, and — on a project someone else owns — the
/// owner's avatar tucked into the corner (the web's `ProjectIconWithOwner`).
class ProjectGroupIcon extends StatelessWidget {
  const ProjectGroupIcon({
    super.key,
    required this.group,
    required this.open,
    this.size = 18.0,
  });

  final SessionGroup group;
  final bool open;
  final double size;

  @override
  Widget build(BuildContext context) {
    // A bare folder no project claims still reads as a folder; only the
    // no-folder group gets the dashed square.
    final project = group.isNoProject
        ? null
        : (group.project ?? <String, dynamic>{'name': group.label});
    final icon = TaskProjectIcon(project: project, size: size, open: open);
    final owner = group.project?['owner'];
    if (owner is! Map) return icon;

    final badge = size * 0.6;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          icon,
          Positioned(
            right: -badge * 0.35,
            bottom: -badge * 0.35,
            child: Container(
              width: badge,
              height: badge,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: FlutterFlowTheme.of(context).secondaryBackground,
                  width: 1.0,
                ),
              ),
              child: FittedBox(
                child: PrincipalAvatar(
                  type: _principalType(owner['type']?.toString()),
                  id: owner['id']?.toString(),
                  name: owner['name']?.toString(),
                  avatarImageUri: owner['avatar_image_uri']?.toString(),
                  emoji: owner['emoji']?.toString(),
                  updatedAt: owner['updated_at']?.toString(),
                  size: PrincipalAvatarSize.xs,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 'system' is an actor, not a principal with an avatar; like the web it
  /// falls back to the agent glyph.
  static PrincipalType _principalType(String? type) {
    switch (type) {
      case 'team':
        return PrincipalType.team;
      case 'agent':
      case 'system':
        return PrincipalType.agent;
      default:
        return PrincipalType.user;
    }
  }
}
