// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom widgets
import '/custom_code/actions/index.dart'; // Imports custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom widget code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:visibility_detector/visibility_detector.dart';

class ImageWidget extends StatefulWidget {
  const ImageWidget({
    super.key,
    required this.width,
    required this.height,
    required this.imageUrl,
    this.borderRadius,
  });

  final double width;
  final double height;
  final String imageUrl;
  final double? borderRadius;

  @override
  State<ImageWidget> createState() => _ImageWidgetState();
}

class _ImageWidgetState extends State<ImageWidget> {
  static int _widgetCounter = 0;
  static int _disposeCounter = 0;
  static final Set<String> _loadedImages = <String>{};
  static final Set<String> _preloadedImages = <String>{};

  late String _widgetKey;
  bool _isVisible = false;
  bool _hasBeenVisible = false;
  bool _shouldLoad = false;

  // Optimized cache manager with larger limits for better UX
  static final _cacheManager = CacheManager(
    Config(
      'smooth_scroll_cache',
      stalePeriod: Duration(days: 15), // Keep images longer
      maxNrOfCacheObjects: 300, // Increased for better UX
      repo: JsonCacheInfoRepository(databaseName: 'smooth_scroll'),
    ),
  );

  @override
  void initState() {
    super.initState();
    _widgetKey = 'image_widget_${_widgetCounter++}';

    // Check if image was already loaded
    if (_loadedImages.contains(widget.imageUrl)) {
      _shouldLoad = true;
      _hasBeenVisible = true;
    }
  }

  @override
  void dispose() {
    _disposeCounter++;
    // More conservative cache clearing - only clear when really needed
    if (_disposeCounter % 200 == 0) {
      _clearOldCache();
    }
    super.dispose();
  }

  static void _clearOldCache() async {
    // Clear cache but keep recently viewed images
    final filesToKeep = <String>{};
    filesToKeep.addAll(_loadedImages);
    filesToKeep.addAll(_preloadedImages);

    // Only clear cache if we have too many loaded images
    if (filesToKeep.length > 150) {
      await _cacheManager.emptyCache();
      _loadedImages.clear();
      _preloadedImages.clear();
    }
  }

  void _preloadNearbyImages() {
    // This would ideally be called from parent widget with nearby image URLs
    // For now, just mark current image as preloaded
    _preloadedImages.add(widget.imageUrl);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.imageUrl.isEmpty) {
      return _buildPlaceholder();
    }

    return VisibilityDetector(
      key: Key(_widgetKey),
      onVisibilityChanged: (visibilityInfo) {
        if (!mounted) return;

        final wasVisible = _isVisible;
        _isVisible = visibilityInfo.visibleFraction >
            0.0; // Load when any part is visible

        // More aggressive preloading
        if (visibilityInfo.visibleFraction > 0.3) {
          _preloadNearbyImages();
        }

        if (!wasVisible && _isVisible) {
          // Image is becoming visible
          if (!_hasBeenVisible) {
            _hasBeenVisible = true;
            _shouldLoad = true;
            _loadedImages.add(widget.imageUrl);
          }
        }

        if (wasVisible != _isVisible) {
          setState(() {});
        }
      },
      child: ClipRRect(
        borderRadius: BorderRadius.circular(widget.borderRadius ?? 10.0),
        child: _shouldLoad
            ? CachedNetworkImage(
                cacheManager: _cacheManager,
                fadeInDuration: Duration(milliseconds: 200),
                fadeOutDuration: Duration(milliseconds: 200),
                imageUrl: widget.imageUrl,
                width: widget.width,
                height: widget.height,
                fit: BoxFit.cover,
                // Optimize memory usage by resizing to display size
                memCacheWidth:
                    (widget.width * MediaQuery.of(context).devicePixelRatio)
                        .round(),
                memCacheHeight:
                    (widget.height * MediaQuery.of(context).devicePixelRatio)
                        .round(),
                placeholder: (context, url) => _buildLoadingPlaceholder(),
                errorWidget: (context, url, error) {
                  debugPrint('Error loading image: $error');
                  return _buildErrorPlaceholder();
                },
              )
            : _buildPlaceholder(),
      ),
    );
  }

  Widget _buildPlaceholder() {
    return Container(
      width: widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(widget.borderRadius ?? 10.0),
      ),
      child: Align(
        alignment: AlignmentDirectional(0.0, 0.0),
        child: FaIcon(
          FontAwesomeIcons.microphoneAlt,
          color: FlutterFlowTheme.of(context).secondaryText,
          size: 30.0,
        ),
      ),
    );
  }

  Widget _buildLoadingPlaceholder() {
    return Container(
      width: widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(widget.borderRadius ?? 10.0),
      ),
      child: Align(
        alignment: AlignmentDirectional(0.0, 0.0),
        child: SizedBox(
          width: 20.0,
          height: 20.0,
          child: CircularProgressIndicator(
            strokeWidth: 2.0,
            valueColor: AlwaysStoppedAnimation<Color>(
              FlutterFlowTheme.of(context).tertiaryText,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildErrorPlaceholder() {
    return Container(
      width: widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(widget.borderRadius ?? 10.0),
      ),
      child: Align(
        alignment: AlignmentDirectional(0.0, 0.0),
        child: FaIcon(
          FontAwesomeIcons.exclamationTriangle,
          color: FlutterFlowTheme.of(context).error,
          size: 24.0,
        ),
      ),
    );
  }
}
