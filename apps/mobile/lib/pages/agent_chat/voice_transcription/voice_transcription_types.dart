import 'package:audio_waveforms/audio_waveforms.dart';

enum VoiceTranscriptionStatus {
  listening,
  done,
  notListening,
}

class VoiceTranscriptionError {
  const VoiceTranscriptionError(this.message,
      {this.shouldOpenSettings = false});

  final String message;
  final bool shouldOpenSettings;
}

class VoiceTranscriptionResult {
  const VoiceTranscriptionResult({
    required this.text,
    required this.isFinal,
    this.clearInterim = false,
  });

  final String text;
  final bool isFinal;
  final bool clearInterim;
}

typedef VoiceResultCallback = void Function(VoiceTranscriptionResult result);
typedef VoiceStatusCallback = void Function(VoiceTranscriptionStatus status);
typedef VoiceErrorCallback = void Function(VoiceTranscriptionError error);

abstract class VoiceTranscriptionProvider {
  Future<bool> initialize();
  Future<bool> start({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  });
  Future<void> stop();
  Future<void> cancel();
  Future<void> dispose();
  bool get isListening;
  String get providerId;
  RecorderController? get recorderController;
}
