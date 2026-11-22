/// The Tasks list's "Relation to me" filter: how a task relates to the
/// signed-in user. Mirrors the web's `TaskRelation` (task-views.ts), with the
/// same words, so the two read the same way.
///
/// `assigned`: they are its assignee. `waiting`: an agent's question on it
/// waits on them (`open_questions`). Picked values are OR ("Assigned to me" or
/// "Waiting on me" is everything that needs me). Stored as words rather than an
/// id, so a remembered filter follows whoever is signed in.
library;

const String kTaskRelationAssigned = 'assigned';
const String kTaskRelationWaiting = 'waiting';

/// Every relation, in the order the filter lists them.
const List<String> kTaskRelations = [kTaskRelationAssigned, kTaskRelationWaiting];

/// [values] without the ones this build doesn't know, in menu order and once
/// each, so a filter saved by a newer build can't hide every task.
List<String> knownTaskRelations(Iterable<String> values) {
  final picked = values.toSet();
  return kTaskRelations.where(picked.contains).toList();
}

/// Whether [t] relates to the viewer in any of the [active] ways (none active
/// keeps everything). [viewerId] is the backend's id for the signed-in user;
/// until it is known nothing matches, rather than everything.
bool taskMatchesRelation(dynamic t, Set<String> active, String? viewerId) {
  if (active.isEmpty) return true;
  if (viewerId == null || t is! Map) return false;
  if (active.contains(kTaskRelationAssigned) && t['assignee_type'] == 'user' && t['assignee_id']?.toString() == viewerId) {
    return true;
  }
  if (!active.contains(kTaskRelationWaiting)) return false;
  final questions = t['open_questions'];
  if (questions is! List) return false;
  return questions.any((q) {
    final addressee = q is Map ? q['addressee'] : null;
    return addressee is Map && addressee['id']?.toString() == viewerId;
  });
}
