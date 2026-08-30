// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'vicoa_api_config.dart';

// Custom exceptions for categorizing errors
class AuthenticationException implements Exception {
  final String message;
  final int statusCode;
  AuthenticationException(this.message, this.statusCode);

  @override
  String toString() => 'AuthenticationException: $message (Status: $statusCode)';
}

class NetworkException implements Exception {
  final String message;
  final dynamic originalError;
  NetworkException(this.message, {this.originalError});

  @override
  String toString() => 'NetworkException: $message';
}

class ServiceUnavailableException implements Exception {
  final String message;
  final dynamic originalError;
  ServiceUnavailableException(this.message, {this.originalError});

  @override
  String toString() => 'ServiceUnavailableException: $message';
}

class ApiException implements Exception {
  final String message;
  final int statusCode;
  final dynamic details;
  ApiException(this.message, this.statusCode, {this.details});

  @override
  String toString() => 'ApiException: $message (Status: $statusCode)';
}

// List of endpoints that don't require authentication
final publicEndpoints = [
  '/health',
  '/docs',
  '/openapi.json',
];

bool _isPublicEndpoint(String endpoint) {
  return publicEndpoints
      .any((publicEndpoint) => endpoint.startsWith(publicEndpoint));
}

Future<bool> _hasInternetReachability() async {
  try {
    final result = await InternetAddress.lookup('google.com').timeout(
      const Duration(seconds: 3),
    );
    return result.isNotEmpty && result.first.rawAddress.isNotEmpty;
  } catch (_) {
    return false;
  }
}

/// Sends the HTTP request and applies the shared auth/error semantics that
/// every Vicoa endpoint expects (401 → AuthenticationException, network
/// errors → NetworkException/ServiceUnavailableException, etc.). Returns the
/// raw [http.Response] so callers can choose how to decode the body — on the
/// main isolate via [vicoaApiRequest], or off-thread via
/// [vicoaApiRequestComputed].
Future<http.Response> _vicoaSendRequest(
  String method,
  String endpoint,
  dynamic body,
) async {
  final isPublic = _isPublicEndpoint(endpoint);
  String? userToken;

  if (!isPublic) {
    userToken = await getUserToken();
    if (userToken == null) {
      throw AuthenticationException(
        "User not authenticated. Cannot fetch token.",
        401,
      );
    }
  }

  final baseUrl = getVicoaApiBaseUrl();
  final uri = Uri.parse('$baseUrl$endpoint');

  final headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json; charset=utf-8',
  };
  if (userToken != null) {
    headers['Authorization'] = 'Bearer $userToken';
  }

  http.Response response;

  try {
    switch (method.toLowerCase()) {
      case 'get':
        response = await http.get(uri, headers: headers);
        break;
      case 'post':
        response = await http.post(
          uri,
          headers: headers,
          body: json.encode(body, toEncodable: _encodeFallback),
        );
        break;
      case 'put':
        response = await http.put(
          uri,
          headers: headers,
          body: json.encode(body, toEncodable: _encodeFallback),
        );
        break;
      case 'delete':
        response = await http.delete(uri, headers: headers);
        break;
      case 'patch':
        response = await http.patch(
          uri,
          headers: headers,
          body: json.encode(body, toEncodable: _encodeFallback),
        );
        break;
      default:
        throw ApiException('Unsupported HTTP method: $method', 400);
    }

    if (response.statusCode == 401) {
      debugPrint('Received 401 Unauthorized for $endpoint: ${response.body}');
      throw AuthenticationException('Authentication failed', 401);
    }

    if (response.body.isEmpty) {
      throw ApiException(
          'Empty response received from server', response.statusCode);
    }

    return response;
  } on SocketException catch (e) {
    if (await _hasInternetReachability()) {
      throw ServiceUnavailableException(
        'Service unavailable',
        originalError: e,
      );
    }
    throw NetworkException(
      'Network connection failed',
      originalError: e,
    );
  } on TimeoutException catch (e) {
    if (await _hasInternetReachability()) {
      throw ServiceUnavailableException(
        'Service unavailable',
        originalError: e,
      );
    }
    throw NetworkException(
      'Request timed out',
      originalError: e,
    );
  } on AuthenticationException {
    rethrow;
  } on ServiceUnavailableException {
    rethrow;
  } on ApiException {
    rethrow;
  } on NetworkException {
    rethrow;
  } catch (err) {
    debugPrint('Unexpected error: $err');
    throw ApiException('Unexpected API error', 500, details: err);
  }
}

Object? _encodeFallback(Object? object) {
  if (object is String) return object;
  return (object as dynamic).toJson();
}

Future<dynamic> vicoaApiRequest(
  String method, // 'get', 'post', 'put', 'patch', 'delete'
  String endpoint,
  dynamic body,
) async {
  final response = await _vicoaSendRequest(method, endpoint, body);
  final decoded = json.decode(utf8.decode(response.bodyBytes));
  if (response.statusCode >= 200 && response.statusCode < 300) {
    return decoded;
  }
  throw ApiException(
    'API Error: ${decoded.toString()}',
    response.statusCode,
    details: decoded,
  );
}

/// Same auth/transport semantics as [vicoaApiRequest], but runs [parser] in a
/// background isolate via [compute] so a large JSON body doesn't block the UI
/// thread while decoding. Use this for endpoints whose response is big enough
/// to drop frames (~hundreds of KB / tens of thousands of items).
///
/// [parser] must be a top-level or static function (compute requirement); it
/// receives the UTF-8-decoded response body and returns the parsed result.
///
/// Example:
/// ```dart
/// List<String> _parseFiles(String body) {
///   final m = json.decode(body) as Map;
///   return (m['files'] as List).map((e) => e.toString()).toList();
/// }
/// final files = await vicoaApiRequestComputed('get', '/api/v1/files', null, _parseFiles);
/// ```
///
/// Error semantics mirror [vicoaApiRequest], except non-2xx responses surface
/// the raw body (we don't decode it just to format the message).
Future<T> vicoaApiRequestComputed<T>(
  String method,
  String endpoint,
  dynamic body,
  T Function(String responseBody) parser,
) async {
  final response = await _vicoaSendRequest(method, endpoint, body);
  final responseBody = utf8.decode(response.bodyBytes);
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw ApiException(
      'API Error: $responseBody',
      response.statusCode,
      details: responseBody,
    );
  }
  return await compute(parser, responseBody);
}

Future<String?> getUserToken() async {
  // Get Supabase JWT token
  // Supabase handles automatic token refresh via autoRefreshToken: true
  var session = SupaFlow.client.auth.currentSession;

  // If no session, return null immediately
  if (session == null) {
    return null;
  }

  return session.accessToken;
}
