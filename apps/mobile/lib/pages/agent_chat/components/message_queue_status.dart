// Reads the send-queue status a USER message carries while an agent is busy.
//
// Shape (only present on `sender_type: user` messages):
//   message_metadata.queue = {
//     status: 'queued' | 'steer' | 'consumed' | 'cancelled',
//     steered?: bool,
//     consumed_at?: string,
//     cancelled_at?: string,
//   }
//
// `queued` means the message is waiting for the agent to pick it up; `steer`
// means the user pressed Steer and the daemon is delivering it into the
// running turn (it settles to `consumed`, or back to `queued` if the turn
// could not be steered); `consumed` means the agent has started acting on it
// (renders like a normal message); `cancelled` means the user pulled it back
// before the agent consumed it. Any other/missing value renders normally.

const String kQueueStatusQueued = 'queued';
const String kQueueStatusSteer = 'steer';
const String kQueueStatusConsumed = 'consumed';
const String kQueueStatusCancelled = 'cancelled';

/// Reads `message['message_metadata']['queue']['status']`, guarding every
/// level with `is Map` (mirrors [parseAskUserQuestionPayload]'s defensive
/// style). Returns null when the message isn't a Map, carries no queue
/// metadata, or `status` isn't a non-empty string.
String? queueStatus(dynamic message) {
  if (message is! Map) return null;
  final metadataRaw = message['message_metadata'];
  if (metadataRaw is! Map) return null;
  final queueRaw = metadataRaw['queue'];
  if (queueRaw is! Map) return null;
  final status = queueRaw['status'];
  if (status is! String || status.isEmpty) return null;
  return status;
}

/// True while a message still lives in the queue bar: waiting (`queued`) or
/// being steered into the running turn (`steer`). Terminal statuses and a
/// missing status are not pending. Mirrors `isPendingQueueStatus` in the
/// web's queue-status.tsx.
bool isPendingQueueStatus(String? status) =>
    status == kQueueStatusQueued || status == kQueueStatusSteer;

final RegExp _controlCommandJsonRegex =
    RegExp(r'\{\s*"type"\s*:\s*"control"[^}]*\}', caseSensitive: false);
const String _waitingForInputPlaceholder = 'Waiting for your input...';

/// True for the control/artifact messages that ride the same send path as
/// chat input — permission-mode, model, thinking, interrupt, and
/// AskUserQuestion submit/summary/cancel commands, each carrying a
/// `{"type":"control"...}` blob — plus the transient "Waiting for your
/// input..." placeholder. Sent mid-turn they're stamped [kQueueStatusQueued]
/// like any message, but the agent swallows them without ever `consumed`-ing
/// them, so they'd sit in the queue bar forever. They aren't real pending
/// input, so the bar filters them out (mirrors the web queue-bar filter).
bool isControlOrArtifactMessage(dynamic message) {
  if (message is! Map) return false;
  final content = message['content']?.toString() ?? '';
  if (content.trim() == _waitingForInputPlaceholder) return true;
  return _controlCommandJsonRegex.hasMatch(content);
}

// ---------------------------------------------------------------------------
// Local send state on an optimistic USER message.
//
// Never comes from the server: `_addOptimisticMessage` stamps it,
// `_promoteOptimistic` strips it on success, and a server copy replacing the
// entry (WS echo or REST merge) drops it implicitly. Shape:
//
//   _send_status: 'sending' | 'failed'
//   _sent_at:     ISO-8601, when this attempt started
//
// The default is success: a `sending` bubble shows nothing for the first
// [kSendIndicatorDelay], so a normal 200–800ms round trip never flashes an
// indicator. `failed` is event-driven (the POST actually errored or hit its
// deadline), not a second timer.

const String kSendStatusKey = '_send_status';
const String kSentAtKey = '_sent_at';
const String kSendStatusSending = 'sending';
const String kSendStatusFailed = 'failed';

/// How long a `sending` bubble stays indicator-free before the spinner appears.
const Duration kSendIndicatorDelay = Duration(seconds: 2);

/// Reads `message['_send_status']`; null for anything that isn't an
/// in-flight or failed local send.
String? sendStatus(dynamic message) {
  if (message is! Map) return null;
  final status = message[kSendStatusKey];
  if (status is! String || status.isEmpty) return null;
  return status;
}

/// When the current send attempt started, or null if unknown.
DateTime? sentAt(dynamic message) {
  if (message is! Map) return null;
  final raw = message[kSentAtKey];
  if (raw is! String) return null;
  return DateTime.tryParse(raw);
}
