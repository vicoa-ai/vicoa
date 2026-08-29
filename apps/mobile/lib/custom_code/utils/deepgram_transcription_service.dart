import 'dart:convert';

import 'package:http/http.dart' as http;

class DeepgramTranscriptionService {
  const DeepgramTranscriptionService();

  Future<String> transcribePrerecordedAudio({
    required List<int> audioBytes,
    required String token,
    required String model,
    required String languageTag,
    String contentType = 'audio/mp4',
  }) async {
    final queryParameters = <String, String>{
      'model': model,
      'punctuate': 'true',
      'smart_format': 'true',
      'language': languageTag,
    };

    final response = await http.post(
      Uri.https('api.deepgram.com', '/v1/listen', queryParameters),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': contentType,
      },
      body: audioBytes,
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw DeepgramTranscriptionException.requestFailed(response.statusCode);
    }

    final payload = jsonDecode(utf8.decode(response.bodyBytes));
    if (payload is! Map<String, dynamic>) {
      throw const DeepgramTranscriptionException.invalidResponse();
    }

    final results = payload['results'];
    final channels =
        results is Map<String, dynamic> ? results['channels'] : null;
    final firstChannel =
        channels is List && channels.isNotEmpty ? channels.first : null;
    final alternatives = firstChannel is Map<String, dynamic>
        ? firstChannel['alternatives']
        : null;
    final firstAlternative = alternatives is List && alternatives.isNotEmpty
        ? alternatives.first
        : null;
    final transcript = firstAlternative is Map<String, dynamic>
        ? (firstAlternative['transcript']?.toString() ?? '').trim()
        : '';

    if (transcript.isEmpty) {
      throw const DeepgramTranscriptionException.noTranscript();
    }

    return transcript;
  }
}

class DeepgramTranscriptionException implements Exception {
  const DeepgramTranscriptionException._(this.code, [this.statusCode]);

  const DeepgramTranscriptionException.requestFailed(int statusCode)
      : this._('request_failed', statusCode);

  const DeepgramTranscriptionException.invalidResponse()
      : this._('invalid_response');

  const DeepgramTranscriptionException.noTranscript() : this._('no_transcript');

  final String code;
  final int? statusCode;
}
