import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

enum VoiceDictationUiState {
  starting,
  listening,
  processing,
}

class VoiceDictationBar extends StatelessWidget {
  const VoiceDictationBar({
    super.key,
    required this.state,
    required this.elapsed,
    required this.recorderController,
    required this.onCancel,
    required this.onConfirm,
    this.confirmEnabled = true,
  });

  final VoiceDictationUiState state;
  final Duration elapsed;
  final RecorderController? recorderController;
  final VoidCallback onCancel;
  final VoidCallback onConfirm;
  final bool confirmEnabled;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final isProcessing = state == VoiceDictationUiState.processing;

    return Container(
      margin: const EdgeInsetsDirectional.fromSTEB(8.0, 0, 8.0, 12.0),
      padding: const EdgeInsetsDirectional.fromSTEB(12.0, 10.0, 12.0, 12.0),
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(28.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (isProcessing)
            SizedBox(
              height: 40.0,
              child: Center(
                child: Text(
                  AppLocalizations.of(context).agentChatTranscribing,
                  style: theme.bodyMedium.override(
                    color: theme.primaryText.withValues(alpha: 0.9),
                    fontSize: 16.0,
                  ),
                ),
              ),
            )
          else
            Row(
              children: [
                _VoiceActionButton(
                  icon: Icons.close_rounded,
                  onTap: onCancel,
                  backgroundColor: theme.primaryText.withValues(alpha: 0.12),
                  iconColor: theme.primaryText,
                ),
                const SizedBox(width: 12.0),
                Expanded(
                  child: _WaveformStrip(
                    recorderController: recorderController,
                  ),
                ),
                const SizedBox(width: 12.0),
                Text(
                  _formatDuration(elapsed),
                  style: theme.bodyMedium.override(
                    color: theme.secondaryText,
                    fontSize: 16.0,
                  ),
                ),
                const SizedBox(width: 12.0),
                _VoiceActionButton(
                  icon: Icons.check_rounded,
                  onTap: confirmEnabled ? onConfirm : null,
                  backgroundColor: confirmEnabled
                      ? const Color(0xFF2383E2)
                      : Colors.white.withValues(alpha: 0.12),
                  iconColor: Colors.white,
                ),
              ],
            ),
        ],
      ),
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _VoiceActionButton extends StatelessWidget {
  const _VoiceActionButton({
    required this.icon,
    required this.onTap,
    required this.backgroundColor,
    required this.iconColor,
  });

  final IconData icon;
  final VoidCallback? onTap;
  final Color backgroundColor;
  final Color iconColor;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(24.0),
        onTap: onTap,
        child: Opacity(
          opacity: onTap == null ? 0.5 : 1,
          child: Container(
            width: 40.0,
            height: 40.0,
            decoration: BoxDecoration(
              color: backgroundColor,
              borderRadius: BorderRadius.circular(20.0),
            ),
            alignment: Alignment.center,
            child: Icon(
              icon,
              color: iconColor,
              size: 22.0,
            ),
          ),
        ),
      ),
    );
  }
}

class _WaveformStrip extends StatelessWidget {
  const _WaveformStrip({
    required this.recorderController,
  });

  final RecorderController? recorderController;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return SizedBox(
      height: 28.0,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final controller = recorderController;
          if (controller == null) {
            return const SizedBox.shrink();
          }
          return AudioWaveforms(
            size: Size(constraints.maxWidth, 28.0),
            recorderController: controller,
            waveStyle: WaveStyle(
              waveColor: theme.primaryText.withValues(alpha: 0.72),
              gradient: null,
              extendWaveform: true,
              showMiddleLine: false,
              showDurationLabel: false,
              waveformRenderMode: WaveformRenderMode.rtl,
              spacing: 4.0,
              waveThickness: 2.6,
              scaleFactor: 48.0,
              waveCap: StrokeCap.round,
            ),
          );
        },
      ),
    );
  }
}
