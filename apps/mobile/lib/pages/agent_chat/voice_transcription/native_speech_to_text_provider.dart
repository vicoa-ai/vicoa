import 'voice_transcription_types.dart';

/*
import 'dart:io';

import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class NativeSpeechToTextProvider implements VoiceTranscriptionProvider {
  NativeSpeechToTextProvider({stt.SpeechToText? speechToText})
      : _speechToText = speechToText ?? stt.SpeechToText();

  final stt.SpeechToText _speechToText;
  bool _isInitializing = false;
  bool _isAvailable = false;
  VoiceErrorCallback? _onError;
  VoiceStatusCallback? _onStatus;

  @override
  String get providerId => 'native';

  @override
  bool get isListening => _speechToText.isListening;

  @override
  get recorderController => null;

  @override
  Future<bool> initialize() async {
    if (_isInitializing) {
      return false;
    }
    _isInitializing = true;
    try {
      final hasPermissions = await _ensurePermissions();
      if (!hasPermissions) {
        return false;
      }
      if (!_speechToText.isAvailable) {
        final available = await _speechToText.initialize(
          onStatus: _handleStatus,
          onError: (error) {
            if (error.errorMsg == 'error_no_match') {
              return;
            }
            _onError?.call(
              const VoiceTranscriptionError(
                'Something went wrong with speech recognition. Please try again.',
              ),
            );
          },
        );
        _isAvailable = available;
      } else {
        _isAvailable = true;
      }
      if (!_isAvailable) {
        _onError?.call(
          const VoiceTranscriptionError('Speech recognition is unavailable.'),
        );
      }
      return _isAvailable;
    } catch (_) {
      _onError?.call(
        const VoiceTranscriptionError(
          'Unable to initialize speech recognition. Please try again.',
        ),
      );
      return false;
    } finally {
      _isInitializing = false;
    }
  }

  @override
  Future<bool> start({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  }) async {
    _onError = onError;
    _onStatus = onStatus;
    final ready = await initialize();
    if (!ready) {
      return false;
    }
    try {
      final started = await _speechToText.listen(
        onResult: (SpeechRecognitionResult result) {
          final recognized = result.recognizedWords.trim();
          if (recognized.isEmpty) {
            return;
          }
          onResult(
            VoiceTranscriptionResult(
              text: recognized,
              isFinal: result.finalResult,
            ),
          );
        },
        listenFor: const Duration(seconds: 45),
        pauseFor: const Duration(seconds: 5),
        listenOptions: stt.SpeechListenOptions(
          partialResults: true,
          cancelOnError: true,
          listenMode: stt.ListenMode.dictation,
          autoPunctuation: true,
        ),
      );
      return (started == true) || (started == null);
    } catch (error) {
      _onError?.call(
        VoiceTranscriptionError('Failed to start voice input: $error'),
      );
      return false;
    }
  }

  @override
  Future<void> stop() async {
    await _speechToText.stop();
  }

  @override
  Future<void> cancel() async {
    await _speechToText.cancel();
  }

  @override
  Future<void> dispose() async {
    await _speechToText.stop();
  }

  void _handleStatus(String rawStatus) {
    final status = rawStatus.toLowerCase();
    if (status == 'listening') {
      _onStatus?.call(VoiceTranscriptionStatus.listening);
      return;
    }
    if (status == 'done') {
      _onStatus?.call(VoiceTranscriptionStatus.done);
      return;
    }
    if (status == 'notlistening') {
      _onStatus?.call(VoiceTranscriptionStatus.notListening);
    }
  }

  Future<bool> _ensurePermissions() async {
    final micStatus = await _ensurePermission(Permission.microphone);
    if (!_isGrantedStatus(micStatus)) {
      return _reportPermissionError(micStatus);
    }
    if (Platform.isIOS) {
      final speechStatus = await _ensurePermission(Permission.speech);
      if (!_isGrantedStatus(speechStatus)) {
        return _reportPermissionError(speechStatus);
      }
    }
    return true;
  }

  Future<PermissionStatus> _ensurePermission(Permission permission) async {
    final currentStatus = await permission.status;
    if (_isGrantedStatus(currentStatus)) {
      return currentStatus;
    }
    return permission.request();
  }

  bool _isGrantedStatus(PermissionStatus status) {
    return status == PermissionStatus.granted ||
        status == PermissionStatus.limited;
  }

  bool _reportPermissionError(PermissionStatus status) {
    _onError?.call(
      VoiceTranscriptionError(
        'Microphone and speech recognition permissions are required for voice input. Enable them in Settings.',
        shouldOpenSettings: _shouldOpenSettings(status),
      ),
    );
    return false;
  }

  bool _shouldOpenSettings(PermissionStatus status) {
    return status == PermissionStatus.permanentlyDenied ||
        status == PermissionStatus.denied ||
        status == PermissionStatus.restricted;
  }
}
*/

class NativeSpeechToTextProvider implements VoiceTranscriptionProvider {
  NativeSpeechToTextProvider();

  @override
  String get providerId => 'native';

  @override
  bool get isListening => false;

  @override
  get recorderController => null;

  @override
  Future<bool> initialize() async => false;

  @override
  Future<bool> start({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  }) async {
    onError(
      const VoiceTranscriptionError(
        'Native speech recognition is temporarily disabled in this build.',
      ),
    );
    return false;
  }

  @override
  Future<void> stop() async {}

  @override
  Future<void> cancel() async {}

  @override
  Future<void> dispose() async {}
}
