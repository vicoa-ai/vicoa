import 'dart:async';

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'principal_avatar.dart';

/// The signed-in user's own avatar.
///
/// `FFAppState().user` (a FlutterFlow struct) carries no avatar field, and the
/// picture lives in our backend rather than in Supabase, so this reads
/// `GET /api/v1/auth/me` once on mount. Until it answers — and whenever the
/// account has no stored image — `PrincipalAvatar` shows initials, so there is
/// no spinner and no layout shift.
class SelfAvatar extends StatefulWidget {
  const SelfAvatar({super.key, this.size = PrincipalAvatarSize.lg});

  final PrincipalAvatarSize size;

  @override
  State<SelfAvatar> createState() => _SelfAvatarState();
}

class _SelfAvatarState extends State<SelfAvatar> {
  String? _avatarImageUri;
  String? _avatarEmoji;
  String? _updatedAt;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final profile = await vicoaApiRequest('get', '/api/v1/auth/me', null);
      if (!mounted || profile is! Map) return;
      setState(() {
        _avatarImageUri = profile['avatar_image_uri'] as String?;
        _avatarEmoji = profile['avatar_emoji'] as String?;
        _updatedAt = profile['updated_at'] as String?;
      });
    } catch (_) {
      // Best-effort: no avatar just means initials.
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = FFAppState().user;
    return PrincipalAvatar(
      type: PrincipalType.user,
      id: user.id,
      // Falls back to the email only to derive an initial; the widget never
      // renders it.
      name: user.name.isNotEmpty ? user.name : user.email,
      avatarImageUri: _avatarImageUri,
      emoji: _avatarEmoji,
      updatedAt: _updatedAt,
      size: widget.size,
    );
  }
}
