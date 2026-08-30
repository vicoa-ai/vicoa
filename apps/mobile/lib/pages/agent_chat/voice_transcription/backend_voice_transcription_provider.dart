import 'voice_transcription_types.dart';

class BackendVoiceTranscriptionProvider implements VoiceTranscriptionProvider {
  BackendVoiceTranscriptionProvider({
    required this.startSession,
    required this.stopSession,
    required this.cancelSession,
    this.disposeSession,
    this.id = 'backend',
  });

  final Future<bool> Function({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  }) startSession;
  final Future<void> Function() stopSession;
  final Future<void> Function() cancelSession;
  final Future<void> Function()? disposeSession;
  final String id;
  bool _isListening = false;

  @override
  String get providerId => id;

  @override
  bool get isListening => _isListening;

  @override
  Future<bool> initialize() async => true;

  @override
  get recorderController => null;

  @override
  Future<bool> start({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  }) async {
    _isListening = await startSession(
      onResult: onResult,
      onStatus: (status) {
        _isListening = status == VoiceTranscriptionStatus.listening;
        onStatus(status);
      },
      onError: onError,
    );
    return _isListening;
  }

  @override
  Future<void> stop() async {
    _isListening = false;
    await stopSession();
  }

  @override
  Future<void> cancel() async {
    _isListening = false;
    await cancelSession();
  }

  @override
  Future<void> dispose() async {
    _isListening = false;
    await disposeSession?.call();
  }
}
