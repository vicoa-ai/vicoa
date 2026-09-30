// FileVideoControls — the Files tab video player's controls, passed to chewie as
// `customControls`. Chewie's built-in sets hardcode their button and bar
// shapes, so the viewer draws its own: square top buttons and a full-width
// bottom bar.

import 'dart:async';
import 'dart:ui' show FontFeature, ImageFilter;

import 'package:chewie/chewie.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '/l10n/app_localizations.dart';

// Chewie's iOS palette, which the first version of the player shipped with.
const Color _background = Color.fromRGBO(41, 41, 41, 0.7);
const Color _foreground = Color.fromARGB(255, 200, 200, 200);
const Duration _fade = Duration(milliseconds: 300);
const Duration _autoHide = Duration(seconds: 3);
const Duration _skipBy = Duration(seconds: 15);

class FileVideoControls extends StatefulWidget {
  const FileVideoControls({super.key});

  @override
  State<FileVideoControls> createState() => _FileVideoControlsState();
}

class _FileVideoControlsState extends State<FileVideoControls> {
  ChewieController? _chewie;
  Timer? _hideTimer;
  bool _visible = true;
  double _unmutedVolume = 1.0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _chewie = ChewieController.of(context);
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    super.dispose();
  }

  // Show the controls and restart the auto-hide countdown. The countdown only
  // matters while playing: paused controls stay up regardless.
  void _poke() {
    _hideTimer?.cancel();
    setState(() => _visible = true);
    _hideTimer = Timer(_autoHide, () {
      if (mounted) setState(() => _visible = false);
    });
  }

  void _onTapVideo(bool showing, bool playing) {
    if (showing && playing) {
      _hideTimer?.cancel();
      setState(() => _visible = false);
    } else {
      _poke();
    }
  }

  Future<void> _playPause(VideoPlayerValue value) async {
    final video = _chewie!.videoPlayerController;
    _poke();
    if (value.isPlaying) {
      await video.pause();
    } else {
      if (_isFinished(value)) await video.seekTo(Duration.zero);
      await video.play();
    }
  }

  Future<void> _skip(VideoPlayerValue value, Duration delta) async {
    _poke();
    final target = value.position + delta;
    await _chewie!.videoPlayerController.seekTo(target < Duration.zero ? Duration.zero : (target > value.duration ? value.duration : target));
  }

  Future<void> _pickSpeed(VideoPlayerValue value) async {
    final chewie = _chewie!;
    // Keep the controls up while the sheet is open.
    _hideTimer?.cancel();
    final speed = await showCupertinoModalPopup<double>(
      context: context,
      useRootNavigator: chewie.useRootNavigator,
      builder: (context) => _SpeedSheet(speeds: chewie.playbackSpeeds, selected: value.playbackSpeed),
    );
    if (speed != null) await chewie.videoPlayerController.setPlaybackSpeed(speed);
    if (mounted) _poke();
  }

  void _toggleMute(VideoPlayerValue value) {
    final video = _chewie!.videoPlayerController;
    _poke();
    if (value.volume > 0) {
      _unmutedVolume = value.volume;
      video.setVolume(0.0);
    } else {
      video.setVolume(_unmutedVolume);
    }
  }

  @override
  Widget build(BuildContext context) {
    final chewie = _chewie!;
    final video = chewie.videoPlayerController;
    return ValueListenableBuilder<VideoPlayerValue>(
      valueListenable: video,
      builder: (context, value, _) {
        final showing = _visible || !value.isPlaying;
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => _onTapVideo(showing, value.isPlaying),
              ),
            ),
            if (!value.isPlaying)
              Center(
                child: _Fade(
                  showing: showing,
                  child: _CenterPlayButton(finished: _isFinished(value), onTap: () => _playPause(value)),
                ),
              ),
            Positioned(
              top: 12,
              left: 16,
              right: 16,
              child: _Fade(
                showing: showing,
                child: Row(
                  children: [
                    _SquareButton(
                      icon: chewie.isFullScreen ? CupertinoIcons.arrow_down_right_arrow_up_left : CupertinoIcons.arrow_up_left_arrow_down_right,
                      onTap: () {
                        _poke();
                        chewie.toggleFullScreen();
                      },
                    ),
                    const Spacer(),
                    _SquareButton(icon: value.volume > 0 ? Icons.volume_up_rounded : Icons.volume_off_rounded, onTap: () => _toggleMute(value)),
                  ],
                ),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _Fade(
                showing: showing,
                child: _BottomBar(
                  video: video,
                  value: value,
                  onPlayPause: () => _playPause(value),
                  onSkipBack: () => _skip(value, -_skipBy),
                  onSkipForward: () => _skip(value, _skipBy),
                  onSpeed: () => _pickSpeed(value),
                  onScrub: _poke,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

bool _isFinished(VideoPlayerValue value) => value.duration > Duration.zero && value.position >= value.duration;

class _Fade extends StatelessWidget {
  const _Fade({required this.showing, required this.child});
  final bool showing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !showing,
      child: AnimatedOpacity(opacity: showing ? 1.0 : 0.0, duration: _fade, child: child),
    );
  }
}

class _Blurred extends StatelessWidget {
  const _Blurred({required this.child, this.borderRadius = BorderRadius.zero});
  final Widget child;
  final BorderRadius borderRadius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: borderRadius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10.0, sigmaY: 10.0),
        child: ColoredBox(color: _background, child: child),
      ),
    );
  }
}

class _SquareButton extends StatelessWidget {
  const _SquareButton({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: _Blurred(
        borderRadius: BorderRadius.circular(10.0),
        child: SizedBox(width: 40.0, height: 40.0, child: Icon(icon, color: _foreground, size: 20.0)),
      ),
    );
  }
}

class _CenterPlayButton extends StatelessWidget {
  const _CenterPlayButton({required this.finished, required this.onTap});
  final bool finished;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: _Blurred(
        borderRadius: BorderRadius.circular(32.0),
        child: SizedBox(width: 64.0, height: 64.0, child: Icon(finished ? Icons.replay_rounded : Icons.play_arrow_rounded, color: _foreground, size: 36.0)),
      ),
    );
  }
}

/// Full-width, square-edged bar pinned to the bottom. Its background runs under
/// the home indicator; the controls sit above it.
class _BottomBar extends StatelessWidget {
  const _BottomBar({required this.video, required this.value, required this.onPlayPause, required this.onSkipBack, required this.onSkipForward, required this.onSpeed, required this.onScrub});
  final VideoPlayerController video;
  final VideoPlayerValue value;
  final VoidCallback onPlayPause;
  final VoidCallback onSkipBack;
  final VoidCallback onSkipForward;
  final VoidCallback onSpeed;
  final VoidCallback onScrub;

  @override
  Widget build(BuildContext context) {
    const timeStyle = TextStyle(color: _foreground, fontSize: 12.0, fontFeatures: [FontFeature.tabularFigures()]);
    final remaining = value.duration - value.position;
    return _Blurred(
      child: Padding(
        padding: EdgeInsets.only(left: 4.0, right: 4.0, bottom: MediaQuery.paddingOf(context).bottom),
        child: SizedBox(
          height: 48.0,
          child: Row(
            children: [
              _BarButton(width: 36.0, onTap: onSkipBack, child: const Icon(CupertinoIcons.gobackward_15, color: _foreground, size: 20.0)),
              _BarButton(width: 40.0, onTap: onPlayPause, child: Icon(value.isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded, color: _foreground, size: 26.0)),
              _BarButton(width: 36.0, onTap: onSkipForward, child: const Icon(CupertinoIcons.goforward_15, color: _foreground, size: 20.0)),
              const SizedBox(width: 4.0),
              Text(_formatTime(value.position), style: timeStyle),
              const SizedBox(width: 10.0),
              Expanded(
                // Keeps the controls up while the user is dragging.
                child: Listener(
                  onPointerDown: (_) => onScrub(),
                  onPointerMove: (_) => onScrub(),
                  child: VideoProgressIndicator(
                    video,
                    allowScrubbing: true,
                    padding: const EdgeInsets.symmetric(vertical: 18.0),
                    colors: const VideoProgressColors(playedColor: Colors.white, bufferedColor: Colors.white38, backgroundColor: Colors.white24),
                  ),
                ),
              ),
              const SizedBox(width: 10.0),
              Text('-${_formatTime(remaining.isNegative ? Duration.zero : remaining)}', style: timeStyle),
              _BarButton(width: 44.0, onTap: onSpeed, child: Text(_speedLabel(value.playbackSpeed), style: timeStyle.copyWith(fontSize: 13.0, fontWeight: FontWeight.w600))),
            ],
          ),
        ),
      ),
    );
  }
}

class _BarButton extends StatelessWidget {
  const _BarButton({required this.width, required this.onTap, required this.child});
  final double width;
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(width: width, height: 48.0, child: Center(child: child)),
    );
  }
}

/// Playback speed picker, the same action sheet chewie's iOS controls use.
class _SpeedSheet extends StatelessWidget {
  const _SpeedSheet({required this.speeds, required this.selected});
  final List<double> speeds;
  final double selected;

  @override
  Widget build(BuildContext context) {
    final selectedColor = CupertinoTheme.of(context).primaryColor;
    return CupertinoActionSheet(
      actions: [
        for (final speed in speeds)
          CupertinoActionSheetAction(
            onPressed: () => Navigator.of(context).pop(speed),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (speed == selected) Padding(padding: const EdgeInsets.only(right: 6.0), child: Icon(Icons.check_rounded, size: 20.0, color: selectedColor)),
                Text(_speedLabel(speed)),
              ],
            ),
          ),
      ],
      cancelButton: CupertinoActionSheetAction(
        isDefaultAction: true,
        onPressed: () => Navigator.of(context).pop(),
        child: Text(AppLocalizations.of(context).commonCancel),
      ),
    );
  }
}

String _speedLabel(double speed) => '${speed == speed.roundToDouble() ? speed.toInt() : speed}×';

String _formatTime(Duration d) {
  final seconds = d.inSeconds.remainder(60).toString().padLeft(2, '0');
  if (d.inHours > 0) return '${d.inHours}:${d.inMinutes.remainder(60).toString().padLeft(2, '0')}:$seconds';
  return '${d.inMinutes}:$seconds';
}
