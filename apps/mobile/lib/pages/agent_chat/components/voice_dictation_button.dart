import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_theme.dart';

class VoiceDictationButton extends StatelessWidget {
  const VoiceDictationButton({
    super.key,
    required this.isSpeechInitializing,
    required this.shouldOpenSpeechSettings,
    required this.onPressed,
  });

  final bool isSpeechInitializing;
  final bool shouldOpenSpeechSettings;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final isUnavailable = shouldOpenSpeechSettings && !isSpeechInitializing;
    final containerColor = isUnavailable
        ? theme.secondaryText.withValues(alpha: 0.08)
        : theme.secondaryText.withValues(alpha: 0.05);
    final iconData =
        isUnavailable ? Icons.mic_off_rounded : Icons.mic_none_rounded;
    final iconColor = isUnavailable
        ? theme.secondaryText.withValues(alpha: 0.6)
        : theme.primaryText;

    return Container(
      width: 40.0,
      height: 40.0,
      decoration: BoxDecoration(
        color: containerColor,
        borderRadius: BorderRadius.circular(20.0),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20.0),
          onTap: isSpeechInitializing ? null : onPressed,
          child: isSpeechInitializing
              ? Center(
                  child: SizedBox(
                    width: 18.0,
                    height: 18.0,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.0,
                      valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
                    ),
                  ),
                )
              : Icon(
                  iconData,
                  color: iconColor,
                  size: 22.0,
                ),
        ),
      ),
    );
  }
}
