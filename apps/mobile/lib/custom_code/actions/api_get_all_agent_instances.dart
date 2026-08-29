// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

bool? _parseBoolValue(dynamic value) {
  if (value is bool) {
    return value;
  }
  if (value is num) {
    return value != 0;
  }
  if (value is String) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'true') {
      return true;
    }
    if (normalized == 'false') {
      return false;
    }
  }
  return null;
}

int? _parseIntValue(dynamic value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim());
  }
  return null;
}

List<dynamic> _extractItems(dynamic result) {
  if (result is List) {
    return result;
  }
  if (result is Map) {
    final items = result['items'] ??
        result['results'] ??
        result['data'] ??
        result['agent_instances'];
    if (items is List) {
      return items;
    }
  }
  return [];
}

Future<Map<String, dynamic>> apiGetAllAgentInstances({
  int page = 1,
  int pageSize = 20,
}) async {
  try {
    final offset = (page - 1) * pageSize;
    final endpoint = '/api/v1/agent-instances?limit=$pageSize&offset=$offset';
    final result = await vicoaApiRequest('get', endpoint, null);
    final items = _extractItems(result);

    if (result is List) {
      return {
        'items': items,
        'page': page,
        'nextPage': items.length >= pageSize ? page + 1 : null,
        'hasMore': items.length >= pageSize,
      };
    }

    if (result is Map) {
      final explicitHasMore =
          _parseBoolValue(result['has_more']) ?? _parseBoolValue(result['hasMore']);
      final total = _parseIntValue(result['total']);
      final respLimit = _parseIntValue(result['limit']) ?? pageSize;
      final respOffset = _parseIntValue(result['offset']) ?? offset;
      final currentPage = respLimit > 0 ? (respOffset ~/ respLimit) + 1 : page;

      final resolvedHasMore = explicitHasMore ??
          (total != null
              ? respOffset + items.length < total
              : items.length >= pageSize);

      return {
        'items': items,
        'page': currentPage,
        'nextPage': resolvedHasMore ? currentPage + 1 : null,
        'hasMore': resolvedHasMore,
      };
    }

    return {
      'items': items,
      'page': page,
      'nextPage': items.length >= pageSize ? page + 1 : null,
      'hasMore': items.length >= pageSize,
    };
  } on AuthenticationException {
    rethrow; // Let caller handle auth errors
  } on ServiceUnavailableException {
    rethrow; // Let caller handle service availability errors
  } on NetworkException {
    rethrow; // Let caller handle network errors
  } catch (e) {
    debugPrint('Error getting all agent instances: $e');
    return {
      'items': <dynamic>[],
      'page': page,
      'nextPage': null,
      'hasMore': false,
    };
  }
}
