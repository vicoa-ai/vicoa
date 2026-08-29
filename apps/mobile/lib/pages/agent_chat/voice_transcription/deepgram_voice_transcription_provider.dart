import 'dart:io';

import '/app_state.dart';
import '/custom_code/actions/index.dart';
import '/custom_code/utils/deepgram_language_registry.dart';
import '/custom_code/utils/deepgram_transcription_service.dart';
import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'voice_transcription_types.dart';

class DeepgramVoiceTranscriptionProvider implements VoiceTranscriptionProvider {
  DeepgramVoiceTranscriptionProvider({
    RecorderController? recorderController,
    DeepgramTranscriptionService? transcriptionService,
  })  : _recorderController = recorderController ?? RecorderController(),
        _transcriptionService =
            transcriptionService ?? const DeepgramTranscriptionService();

  VoiceResultCallback? _onResult;
  VoiceStatusCallback? _onStatus;
  VoiceErrorCallback? _onError;
  bool _isListening = false;
  bool _isDisposed = false;
  String? _recordedFilePath;
  String? _temporaryToken;
  final RecorderController _recorderController;
  final DeepgramTranscriptionService _transcriptionService;

  @override
  String get providerId => 'deepgram';

  @override
  bool get isListening => _isListening;

  @override
  RecorderController get recorderController => _recorderController;

  @override
  Future<bool> initialize() async {
    return _ensurePermissions(reportErrors: false);
  }

  @override
  Future<bool> start({
    required VoiceResultCallback onResult,
    required VoiceStatusCallback onStatus,
    required VoiceErrorCallback onError,
  }) async {
    _onResult = onResult;
    _onStatus = onStatus;
    _onError = onError;
    _temporaryToken = null;
    await _deleteRecordedFile();

    final hasPermissions = await _ensurePermissions(reportErrors: true);
    if (!hasPermissions) {
      return false;
    }

    _temporaryToken = await _fetchTemporaryToken();
    if (_temporaryToken == null) {
      return false;
    }

    try {
      final directory = await getApplicationDocumentsDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final filePath = '${directory.path}/voice_dictation_$timestamp.m4a';
      _recordedFilePath = filePath;
      _recorderController.overrideAudioSession = true;
      await _recorderController.record(
        path: filePath,
        recorderSettings: const RecorderSettings(
          sampleRate: 44100,
          bitRate: 128000,
        ),
      );
    } catch (error) {
      final details = error.toString().trim();
      _emitError(
        VoiceTranscriptionError(
          details.isNotEmpty &&
                  details != 'Failed to start recording' &&
                  details != 'Exception: Failed to start recording'
              ? 'Unable to start microphone recording: $details'
              : 'Unable to start microphone recording. Please try again.',
        ),
      );
      await _cleanupRecording();
      return false;
    }

    _isListening = true;
    _onStatus?.call(VoiceTranscriptionStatus.listening);
    return true;
  }

  @override
  Future<void> stop() async {
    if (!_isListening && _recordedFilePath == null) {
      return;
    }

    _isListening = false;

    String? stoppedPath;
    try {
      stoppedPath = await _recorderController.stop();
    } catch (_) {
      _emitError(
        const VoiceTranscriptionError(
          'Unable to finish the audio recording. Please try again.',
        ),
      );
      await _cleanupRecording();
      return;
    }

    final token = _temporaryToken ?? await _fetchTemporaryToken();
    if (token == null) {
      await _cleanupRecording();
      return;
    }

    final path = stoppedPath ?? _recordedFilePath;
    if (path == null) {
      _emitError(
        const VoiceTranscriptionError(
          'No audio recording was captured. Please try again.',
        ),
      );
      return;
    }

    final file = File(path);
    if (!await file.exists()) {
      _emitError(
        const VoiceTranscriptionError(
          'No audio recording was captured. Please try again.',
        ),
      );
      await _cleanupRecording();
      return;
    }

    try {
      final bytes = await file.readAsBytes();
      final languageOption = deepgramLanguageForTag(
        FFAppState().voiceTranscriptionLanguageTag,
      );
      final text = await _transcriptionService.transcribePrerecordedAudio(
        audioBytes: bytes,
        token: token,
        model: languageOption.recommendedModel,
        languageTag: languageOption.tag,
      );

      _onResult?.call(VoiceTranscriptionResult(text: text, isFinal: true));
      _onStatus?.call(VoiceTranscriptionStatus.done);
    } on DeepgramTranscriptionException catch (error) {
      _emitError(_mapDeepgramError(error));
    } on SocketException {
      _emitError(
        const VoiceTranscriptionError(
          'A network connection is required for voice dictation.',
        ),
      );
    } catch (_) {
      _emitError(
        const VoiceTranscriptionError(
          'Unable to transcribe the recording. Please try again.',
        ),
      );
    } finally {
      await _cleanupRecording();
    }
  }

  @override
  Future<void> cancel() async {
    _isListening = false;
    try {
      if (!_recorderController.recorderState.isStopped) {
        await _recorderController.stop();
      }
    } catch (_) {
      // Ignore cancellation failures during cleanup.
    }
    await _cleanupRecording();
  }

  @override
  Future<void> dispose() async {
    _isDisposed = true;
    await cancel();
    _recorderController.dispose();
  }

  Future<String?> _fetchTemporaryToken() async {
    try {
      return await apiGetDeepgramToken();
    } on AuthenticationException {
      _emitError(
        const VoiceTranscriptionError(
          'Please sign in again to use voice dictation.',
        ),
      );
    } on ApiException {
      _emitError(
        const VoiceTranscriptionError(
          'Voice transcription is temporarily unavailable.',
        ),
      );
    } on NetworkException {
      _emitError(
        const VoiceTranscriptionError(
          'A network connection is required for voice dictation.',
        ),
      );
    } on ServiceUnavailableException {
      _emitError(
        const VoiceTranscriptionError(
          'Voice transcription is temporarily unavailable.',
        ),
      );
    } catch (_) {
      _emitError(
        const VoiceTranscriptionError(
          'Unable to fetch a voice session token. Please try again.',
        ),
      );
    }
    return null;
  }

  Future<bool> _ensurePermissions({required bool reportErrors}) async {
    final micStatus = await _ensurePermission(Permission.microphone);
    if (_isGrantedStatus(micStatus)) {
      return true;
    }
    if (reportErrors) {
      _emitError(
        VoiceTranscriptionError(
          'Microphone permission is required for voice input. Enable it in Settings.',
          shouldOpenSettings: _shouldOpenSettings(micStatus),
        ),
      );
    }
    return false;
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

  bool _shouldOpenSettings(PermissionStatus status) {
    return status == PermissionStatus.permanentlyDenied ||
        status == PermissionStatus.denied ||
        status == PermissionStatus.restricted;
  }

  Future<void> _deleteRecordedFile() async {
    final path = _recordedFilePath;
    _recordedFilePath = null;
    if (path == null) {
      return;
    }
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }

  Future<void> _cleanupRecording() async {
    _temporaryToken = null;
    await _deleteRecordedFile();
  }

  VoiceTranscriptionError _mapDeepgramError(
    DeepgramTranscriptionException error,
  ) {
    switch (error.code) {
      case 'invalid_response':
        return const VoiceTranscriptionError(
          'Voice transcription returned an invalid response.',
        );
      case 'no_transcript':
        return const VoiceTranscriptionError(
          'No transcript was returned. Please try again.',
        );
      case 'request_failed':
      default:
        return const VoiceTranscriptionError(
          'Unable to transcribe the recording. Please try again.',
        );
    }
  }

  void _emitError(VoiceTranscriptionError error) {
    if (_isDisposed) {
      return;
    }
    _onError?.call(error);
  }
}
