// A pinch-to-zoom image for the file viewer. Reports when it is zoomed in so
// the gallery can stop paging: a drag then pans the image instead.

import 'dart:typed_data';

import 'package:flutter/material.dart';

class ZoomableImage extends StatefulWidget {
  const ZoomableImage({super.key, required this.bytes, this.onZoomChanged});

  final Uint8List bytes;
  final ValueChanged<bool>? onZoomChanged;

  @override
  State<ZoomableImage> createState() => _ZoomableImageState();
}

class _ZoomableImageState extends State<ZoomableImage> {
  final TransformationController _transform = TransformationController();
  bool _zoomed = false;

  @override
  void initState() {
    super.initState();
    _transform.addListener(_onTransform);
  }

  void _onTransform() {
    final zoomed = _transform.value.getMaxScaleOnAxis() > 1.01;
    if (zoomed == _zoomed) return;
    _zoomed = zoomed;
    widget.onZoomChanged?.call(zoomed);
  }

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Decode at twice the screen's pixel width, not full size: a 12 MP
        // photo is ~48 MB as a bitmap. The 2x keeps it sharp when zoomed.
        // Never upscales a smaller image (ResizeImage's default).
        final width = constraints.maxWidth.isFinite ? (constraints.maxWidth * MediaQuery.devicePixelRatioOf(context) * 2).round() : null;
        return InteractiveViewer(
          transformationController: _transform,
          child: Center(child: Image.memory(widget.bytes, fit: BoxFit.contain, cacheWidth: width, gaplessPlayback: true)),
        );
      },
    );
  }
}
