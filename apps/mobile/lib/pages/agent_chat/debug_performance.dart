import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

/// Debug widget to measure frame rendering time during keyboard animations
class PerformanceDebugger extends StatefulWidget {
  final Widget child;

  const PerformanceDebugger({Key? key, required this.child}) : super(key: key);

  @override
  State<PerformanceDebugger> createState() => _PerformanceDebuggerState();
}

class _PerformanceDebuggerState extends State<PerformanceDebugger> with WidgetsBindingObserver {
  int _frameCount = 0;
  int _expensiveFrames = 0;
  double _lastKeyboardHeight = 0;
  DateTime? _lastFrameTime;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback(_onFrame);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _onFrame(Duration timestamp) {
    if (!mounted) return;

    final now = DateTime.now();
    if (_lastFrameTime != null) {
      final frameTime = now.difference(_lastFrameTime!).inMilliseconds;
      if (frameTime > 16) {  // Dropped frame (60fps = 16.67ms budget)
        _expensiveFrames++;
        print('⚠️ DROPPED FRAME: ${frameTime}ms (frame $_frameCount)');
      }
    }
    _lastFrameTime = now;
    _frameCount++;

    WidgetsBinding.instance.addPostFrameCallback(_onFrame);
  }

  @override
  void didChangeMetrics() {
    final keyboardHeight = View.of(context).viewInsets.bottom / View.of(context).devicePixelRatio;

    if ((keyboardHeight - _lastKeyboardHeight).abs() > 5) {
      print('📱 Keyboard: ${_lastKeyboardHeight.toInt()}px → ${keyboardHeight.toInt()}px | Frames: $_frameCount | Dropped: $_expensiveFrames');
      _lastKeyboardHeight = keyboardHeight;
      _frameCount = 0;
      _expensiveFrames = 0;
    }
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
