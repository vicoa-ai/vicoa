// Maps raw WebSocket RPC error codes into user-facing guidance.
//
// A failed `spawn-session` / resume RPC surfaces as an `RpcException` whose
// `code` is a wire slug (`no_handler`, `not_connected`, `target_disconnected`,
// `timeout`). The spawn/resume actions pass that slug through as `errorCode`.
// Showing the raw `RpcException(no_handler)` string told the user nothing and
// drove retry-spam against a machine the picker still claimed was online.

import 'package:flutter/widgets.dart';
import '/l10n/app_localizations.dart';

/// Friendly, localized message for a wire RPC error [code], or null when we
/// have no specific copy — callers then fall back to the raw error text (which,
/// for daemon-returned `{error: ...}` results, is already human-readable).
String? friendlyRpcErrorMessage(BuildContext context, String? code) {
  if (code == null || code.isEmpty) return null;
  final l10n = AppLocalizations.of(context);
  switch (code) {
    // The server's RPC router had no live daemon connection to route to
    // (`no_handler`, after its 3s grace window), or the daemon dropped
    // mid-call, or this device's own socket is down. All mean the same thing
    // to the user: the target computer isn't reachable right now.
    case 'no_handler':
    case 'target_disconnected':
    case 'disconnected':
    case 'not_connected':
      return l10n.rpcErrorComputerOffline;
    case 'timeout':
      return l10n.rpcErrorTimeout;
    default:
      return null;
  }
}

/// Whether an RPC error [code] means the machine's live link is down — as
/// opposed to a slow-but-present daemon (`timeout`) or a validation error. Used
/// to mark the machine offline locally, overriding the heartbeat-driven "online"
/// badge that can lag a dead WebSocket link.
bool rpcCodeMeansOffline(String? code) =>
    code == 'no_handler' ||
    code == 'target_disconnected' ||
    code == 'disconnected' ||
    code == 'not_connected';
