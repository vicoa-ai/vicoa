/// Reading a plan-limit refusal off an API error.
///
/// The backend answers `402 {detail, capability}` when an action would go past
/// what the plan includes — a second machine, an eleventh automation.
/// `capability` is `limit.<resource>`,
/// where the resource is the same key `GET /limits` reports, so a denial can
/// be lined up with the usage row it came from.
///
/// Kept apart from the `collab.*` capabilities, which also answer 402: those
/// are about seats and send the user to a different place.
library;

import '/custom_code/actions/index.dart';

const String _limitPrefix = 'limit.';

class PlanLimitDenial {
  const PlanLimitDenial({required this.resource, required this.detail});

  /// `machines`, `automations`, …
  final String resource;

  /// The server's sentence, already written for the user. Shown as-is rather
  /// than reworded here, so the number in it always matches the plan the
  /// server actually applied.
  final String detail;
}

/// The plan limit [error] names, or null when it is any other failure.
///
/// Never throws: a caller is already on its error path.
PlanLimitDenial? planLimitFromError(Object? error) {
  if (error is! ApiException || error.statusCode != 402) return null;
  final details = error.details;
  if (details is! Map) return null;
  final capability = details['capability']?.toString() ?? '';
  if (!capability.startsWith(_limitPrefix)) return null;
  final detail = details['detail']?.toString().trim() ?? '';
  return PlanLimitDenial(
    resource: capability.substring(_limitPrefix.length),
    detail: detail.isEmpty ? 'This is more than your plan includes.' : detail,
  );
}
