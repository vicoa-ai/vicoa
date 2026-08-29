import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '/backend/supabase/supabase.dart';
import '/custom_code/actions/vicoa_api_config.dart';
import '/flutter_flow/flutter_flow_theme.dart';

const Set<String> _rasterImageTypes = {
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
};

/// Raster images render inline; everything else (and legacy rows with no mime
/// are images) shows as a file chip. Mirrors the backend/web inline allowlist.
bool _isImageMeta(Map meta) {
  final mime = meta['mime_type'];
  return mime == null || (mime is String && _rasterImageTypes.contains(mime));
}

String _formatBytes(int bytes) {
  if (bytes < 1024) return '$bytes B';
  const units = ['KB', 'MB', 'GB'];
  var size = bytes / 1024;
  var unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  return '${size < 10 ? size.toStringAsFixed(1) : size.round()} ${units[unit]}';
}

/// Attachments inside a chat bubble, rendered above the message text.
///
/// Each entry of [attachments] is a `message_metadata.attachments` map
/// (`{id, mime_type, width, height, filename, ...}`). Raster images render as
/// a tappable thumbnail (full-screen pinch-zoom on tap); other files render as
/// a chip with the filename and size. [localPaths] maps attachment id →
/// on-device file for just-sent messages, so an image bubble renders from disk
/// instead of re-downloading the upload.
class MessageAttachments extends StatelessWidget {
  const MessageAttachments({
    super.key,
    required this.attachments,
    this.localPaths = const {},
    this.alignEnd = false,
  });

  final List<dynamic> attachments;
  final Map<String, String> localPaths;
  // Right-align images (user messages render them outside the bubble,
  // aligned like the user's own message box).
  final bool alignEnd;

  @override
  Widget build(BuildContext context) {
    final items = [
      for (final a in attachments)
        if (a is Map && a['id'] != null) a,
    ];
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment:
          alignEnd ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) const SizedBox(height: 6.0),
          _isImageMeta(items[i])
              ? _AttachmentImage(
                  meta: items[i],
                  localPath: localPaths[items[i]['id'].toString()],
                )
              : _AttachmentFileChip(meta: items[i]),
        ],
      ],
    );
  }
}

class _AttachmentImage extends StatelessWidget {
  const _AttachmentImage({required this.meta, this.localPath});

  final Map meta;
  final String? localPath;

  double get _aspectRatio {
    final width = meta['width'];
    final height = meta['height'];
    if (width is num && height is num && width > 0 && height > 0) {
      return width / height;
    }
    return 4 / 3;
  }

  Widget _image(BuildContext context, {required BoxFit fit}) {
    final theme = FlutterFlowTheme.of(context);
    final local = localPath;
    if (local != null && File(local).existsSync()) {
      return Image.file(File(local), fit: fit);
    }
    final id = meta['id'].toString();
    // Stable per-attachment URL → disk cache key. The bearer token only
    // matters on first fetch; the immutable response stays cached after.
    final url = '${getVicoaApiBaseUrl()}/api/v1/attachments/$id';
    final token = SupaFlow.client.auth.currentSession?.accessToken ?? '';
    return CachedNetworkImage(
      imageUrl: url,
      httpHeaders: {'Authorization': 'Bearer $token'},
      fit: fit,
      placeholder: (context, _) => Container(
        color: theme.alternate.withValues(alpha: 0.4),
        child: const Center(
          child: SizedBox(
            width: 20.0,
            height: 20.0,
            child: CircularProgressIndicator(strokeWidth: 2.0),
          ),
        ),
      ),
      errorWidget: (context, _, __) => Container(
        color: theme.alternate.withValues(alpha: 0.4),
        child: Icon(
          Icons.broken_image_outlined,
          color: theme.secondaryText,
          size: 24.0,
        ),
      ),
    );
  }

  void _openViewer(BuildContext context) {
    showDialog<void>(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.9),
      // showDialog does not provide a Material ancestor by itself; without
      // one the close IconButton asserts ("No Material widget found").
      builder: (dialogContext) => Material(
        type: MaterialType.transparency,
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                onTap: () => Navigator.of(dialogContext).pop(),
                child: InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 5.0,
                  child:
                      Center(child: _image(dialogContext, fit: BoxFit.contain)),
                ),
              ),
            ),
            Positioned(
              top: MediaQuery.of(dialogContext).padding.top + 8.0,
              right: 16.0,
              child: IconButton(
                icon: const Icon(Icons.close_rounded, color: Colors.white),
                onPressed: () => Navigator.of(dialogContext).pop(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _openViewer(context),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12.0),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 240.0, maxHeight: 280.0),
          child: AspectRatio(
            aspectRatio: _aspectRatio,
            child: _image(context, fit: BoxFit.cover),
          ),
        ),
      ),
    );
  }
}

/// Non-image attachment inside a chat bubble: an icon + filename + size chip.
/// The user uploaded it, so there's no viewer — the chip just shows what was
/// attached.
class _AttachmentFileChip extends StatelessWidget {
  const _AttachmentFileChip({required this.meta});

  final Map meta;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final name = (meta['filename'] as String?) ?? 'File';
    final size = meta['size_bytes'];
    return Container(
      constraints: const BoxConstraints(maxWidth: 240.0),
      padding: const EdgeInsetsDirectional.fromSTEB(12.0, 10.0, 12.0, 10.0),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(color: theme.secondaryText.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.insert_drive_file_outlined,
              color: theme.secondaryText, size: 22.0),
          const SizedBox(width: 10.0),
          Flexible(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(fontSize: 14.0),
                ),
                if (size is num)
                  Text(
                    _formatBytes(size.toInt()),
                    style: theme.bodyMedium.override(
                      fontSize: 11.0,
                      color: theme.secondaryText,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
