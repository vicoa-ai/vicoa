import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';

/// A file (image or otherwise) picked for the next message: local file
/// immediately, server attachment id once the upload completes. `meta` holds
/// the backend's `{id, mime_type, size_bytes, width, height, filename}`
/// response, which doubles as the optimistic message_metadata entry.
class PendingAttachment {
  PendingAttachment({required this.localPath, this.filename, this.isImage = true});

  final String localPath;
  // Original filename, preserved for non-image files so the backend resolves
  // the right type/extension from the multipart part. Null for camera/gallery
  // picks (the path basename is enough there).
  final String? filename;
  // Renders as a thumbnail when true, a file chip when false.
  final bool isImage;
  String? id;
  bool uploading = false;
  bool failed = false;
  Map<String, dynamic>? meta;
}

const Set<String> _imageExtensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'};

bool isImageFilename(String name) {
  final dot = name.lastIndexOf('.');
  if (dot < 0) return false;
  return _imageExtensions.contains(name.substring(dot + 1).toLowerCase());
}

/// Horizontal strip of attachments picked for the next message. Images show a
/// thumbnail, other files show a chip. Spinner overlay while uploading, warning
/// tint + tap-to-retry on failure, × badge removes the pick. Model-agnostic:
/// callers pass the list plus remove/retry callbacks so both the chat input and
/// the new-session prompt can share it.
class PendingAttachmentStrip extends StatelessWidget {
  const PendingAttachmentStrip({
    super.key,
    required this.attachments,
    required this.onRemove,
    this.onRetry,
  });

  final List<PendingAttachment> attachments;
  final void Function(PendingAttachment) onRemove;
  // Null on surfaces where upload only happens later (new-session defers upload
  // to submit time, so there's nothing to retry in the strip).
  final void Function(PendingAttachment)? onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return SizedBox(
      height: 64.0,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 4.0),
        itemCount: attachments.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8.0),
        itemBuilder: (context, index) {
          final attachment = attachments[index];
          return Stack(
            clipBehavior: Clip.none,
            children: [
              GestureDetector(
                onTap: attachment.failed && onRetry != null
                    ? () => onRetry!(attachment)
                    : null,
                child: attachment.isImage
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(10.0),
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            Image.file(
                              File(attachment.localPath),
                              width: 56.0,
                              height: 56.0,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(
                                width: 56.0,
                                height: 56.0,
                                color: theme.alternate,
                                child: Icon(Icons.broken_image_outlined,
                                    color: theme.secondaryText, size: 20.0),
                              ),
                            ),
                            if (attachment.uploading)
                              Container(
                                width: 56.0,
                                height: 56.0,
                                color: Colors.black.withValues(alpha: 0.4),
                                child: const Center(
                                  child: SizedBox(
                                    width: 18.0,
                                    height: 18.0,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2.0,
                                      valueColor: AlwaysStoppedAnimation<Color>(
                                          Colors.white),
                                    ),
                                  ),
                                ),
                              ),
                            if (attachment.failed)
                              Container(
                                width: 56.0,
                                height: 56.0,
                                color: Colors.black.withValues(alpha: 0.5),
                                child: const Center(
                                  child: Icon(Icons.refresh_rounded,
                                      color: Colors.white, size: 22.0),
                                ),
                              ),
                          ],
                        ),
                      )
                    : _PendingFileChip(attachment: attachment),
              ),
              Positioned(
                top: -6.0,
                right: -6.0,
                child: GestureDetector(
                  onTap: () {
                    HapticFeedback.lightImpact();
                    onRemove(attachment);
                  },
                  child: Container(
                    width: 20.0,
                    height: 20.0,
                    decoration: BoxDecoration(
                      color: theme.secondaryBackground,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.secondaryText.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Icon(Icons.close_rounded,
                        size: 14.0, color: theme.secondaryText),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// File chip shown in the pending strip for non-image attachments (images use
/// the thumbnail). The leading icon reflects upload state; tap-to-retry on
/// failure is handled by the enclosing GestureDetector.
class _PendingFileChip extends StatelessWidget {
  const _PendingFileChip({required this.attachment});
  final PendingAttachment attachment;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final name = attachment.filename ?? attachment.localPath.split('/').last;
    final Widget leading;
    if (attachment.uploading) {
      leading = SizedBox(
        width: 16.0,
        height: 16.0,
        child: CircularProgressIndicator(
          strokeWidth: 2.0,
          valueColor: AlwaysStoppedAnimation<Color>(theme.secondaryText),
        ),
      );
    } else if (attachment.failed) {
      leading =
          Icon(Icons.refresh_rounded, color: theme.secondaryText, size: 18.0);
    } else {
      leading = Icon(Icons.insert_drive_file_outlined,
          color: theme.secondaryText, size: 18.0);
    }
    return Container(
      width: 150.0,
      height: 56.0,
      padding: const EdgeInsetsDirectional.fromSTEB(10.0, 0, 10.0, 0),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: BorderRadius.circular(10.0),
        border: Border.all(color: theme.secondaryText.withValues(alpha: 0.2)),
      ),
      child: Row(children: [
        leading,
        const SizedBox(width: 8.0),
        Expanded(
          child: Text(
            name,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.bodyMedium.override(fontSize: 12.0),
          ),
        ),
      ]),
    );
  }
}
