// Reads the send-queue status a USER message carries while an agent is busy.
//
// Shape (only present on `sender_type: user` messages):
//   message_metadata.queue = {
//     status: 'queued' | 'consumed' | 'cancelled',
//     consumed_at?: string,
//     cancelled_at?: string,
//   }
//
// `queued` means the message is waiting for the agent to pick it up;
// `consumed` means the agent has started acting on it (renders like a normal
// message); `cancelled` means the user pulled it back before the agent
// consumed it. Any other/missing value renders normally.

const String kQueueStatusQueued = 'queued';
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
