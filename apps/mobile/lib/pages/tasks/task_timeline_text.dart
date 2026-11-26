import 'package:intl/intl.dart';

import '/custom_code/utils/message_time.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/l10n/app_localizations.dart';
import 'task_l10n.dart';

/// The words the task timeline reads as: activity lines, names, the reactors
/// sentence, "Waiting on …". Ports of the web's `activityText`,
/// `principalDisplayName`, `describeReactors`, `sessionRefTitle` and
/// `waitingOnLabel`, localized. Kept apart from the widgets so they can be
/// tested on their own.

/// The signed-in user as the timeline needs them: their backend id (what
/// principals carry) and the name to fall back on for their own rows.
class TaskViewer {
  const TaskViewer({required this.id, this.name, this.avatarImageUri, this.emoji, this.updatedAt});

  final String id;

  /// `display_name`, else their email: shown only in their own chrome, never
  /// to anyone else.
  final String? name;
  final String? avatarImageUri;
  final String? emoji;
  final String? updatedAt;

  /// From `GET /api/v1/auth/me`, or null when it failed.
  static TaskViewer? fromProfile(Map<String, dynamic>? profile) {
    final id = profile?['id']?.toString();
    if (profile == null || id == null || id.isEmpty) return null;
    String? str(String key) {
      final v = profile[key]?.toString().trim();
      return v == null || v.isEmpty ? null : v;
    }

    return TaskViewer(
      id: id,
      name: str('display_name') ?? str('email'),
      avatarImageUri: str('avatar_image_uri'),
      emoji: str('avatar_emoji'),
      updatedAt: str('updated_at'),
    );
  }

  /// The viewer as a `PrincipalResponse`-shaped map, for their own avatar.
  Map<String, dynamic> toPrincipal() => {
        'type': 'user',
        'id': id,
        'name': name,
        'avatar_image_uri': avatarImageUri,
        'emoji': emoji,
        'updated_at': updatedAt,
      };
}

/// What to call a principal on screen.
///
/// Many accounts have no display name, and the backend never falls back to an
/// email (the same serializer feeds shared and public surfaces). The viewer is
/// the one principal whose own name can stand in, so that fallback happens
/// here, client-side, for them only. Past that: "Agent" for an agent, "Vicoa
/// user" for a real account with no name, "Unknown" for no principal at all
/// (an unattributed background change).
String principalDisplayName(AppLocalizations l10n, dynamic principal, TaskViewer? viewer) {
  final name = tutils.principalName(principal);
  if (name != null) return name;
  final id = tutils.principalId(principal);
  if (viewer != null && id != null && id == viewer.id) return viewer.name ?? l10n.tasksYou;
  if (principal == null) return l10n.tasksPrincipalUnknown;
  final type = tutils.principalType(principal);
  if (type == 'agent' || type == 'system') return l10n.tasksPrincipalAgent;
  return l10n.tasksPrincipalUser;
}

/// "Ada", "Ada and Bo", "Ada, Bo and Cy".
String joinNames(AppLocalizations l10n, List<String> names) {
  if (names.isEmpty) return '';
  if (names.length == 1) return names.first;
  return l10n.tasksNamesAnd(names.sublist(0, names.length - 1).join(', '), names.last);
}

String _pretty(AppLocalizations l10n, dynamic value, String kind) {
  final text = value?.toString() ?? '';
  if (text.isEmpty) return l10n.tasksActivityNone;
  if (kind == 'status') return taskStatusLabel(l10n, text);
  if (kind == 'priority') return taskPriorityLabel(l10n, text);
  return text;
}

/// The phrase an activity row reads as, after its actor's name.
String activityText(AppLocalizations l10n, dynamic row) {
  final d = tutils.activityDetails(row);
  final hasTo = d['to'] != null && d['to'].toString().isNotEmpty;
  switch (tutils.activityAction(row)) {
    case 'created':
      return l10n.tasksActivityCreated;
    case 'status_changed':
      return l10n.tasksActivityStatusChanged(_pretty(l10n, d['from'], 'status'), _pretty(l10n, d['to'], 'status'));
    case 'priority_changed':
      return l10n.tasksActivityPriorityChanged(_pretty(l10n, d['from'], 'priority'), _pretty(l10n, d['to'], 'priority'));
    case 'assigned':
      return hasTo ? l10n.tasksActivityAssigned : l10n.tasksActivityUnassigned;
    case 'title_changed':
      return l10n.tasksActivityTitleChanged;
    case 'description_changed':
      return l10n.tasksActivityDescriptionChanged;
    case 'label_added':
      return l10n.tasksActivityLabelAdded(_pretty(l10n, d['label'], ''));
    case 'label_removed':
      return l10n.tasksActivityLabelRemoved(_pretty(l10n, d['label'], ''));
    case 'due_date_set':
      return hasTo ? l10n.tasksActivityDueDateSet : l10n.tasksActivityDueDateRemoved;
    case 'start_date_set':
      return hasTo ? l10n.tasksActivityStartDateSet : l10n.tasksActivityStartDateRemoved;
    case 'project_changed':
      return l10n.tasksActivityProjectChanged;
    case 'parent_changed':
      return hasTo ? l10n.tasksActivityParentChanged : l10n.tasksActivityParentRemoved;
    // A `#` in a session's message; the row's "via" names the session.
    case 'referenced':
      return l10n.tasksActivityReferenced;
    default:
      return tutils.activityAction(row).replaceAll('_', ' ');
  }
}

/// A session's name as a "Created in" / "via" line reads it. A ref carries no
/// transcript, so an unnamed one is "a Claude session", never "New session".
String sessionRefTitle(AppLocalizations l10n, dynamic ref) {
  final name = (ref is Map ? ref['name'] : null)?.toString().trim() ?? '';
  if (name.isNotEmpty) return name;
  final agent = (ref is Map ? ref['agent_type_name'] : null)?.toString() ?? '';
  if (agent.isEmpty) return l10n.tasksSessionRefUnnamed;
  return l10n.tasksSessionRefAgent('${agent[0].toUpperCase()}${agent.substring(1)}');
}

/// "You and Ada reacted with 👍": what a long-press on a pill says.
///
/// The viewer comes first and reads as "You". Past the server's cap the rest
/// collapse to "and N others", so the sentence never under-reports who is on
/// a pill.
String describeReactors(AppLocalizations l10n, dynamic reaction, TaskViewer? viewer) {
  final named = <String>[];
  var mine = false;
  for (final r in tutils.reactionReactors(reaction)) {
    if (viewer != null && tutils.principalId(r) == viewer.id) {
      mine = true;
    } else {
      named.add(principalDisplayName(l10n, r, viewer));
    }
  }
  if (mine) named.insert(0, l10n.tasksYou);
  final unnamed = tutils.reactionCount(reaction) - named.length;
  if (unnamed > 0) named.add(l10n.tasksReactorsOthers(unnamed));
  final people = named.isEmpty ? l10n.tasksSomeone : joinNames(l10n, named);
  return l10n.tasksReactedWith(people, tutils.reactionEmoji(reaction));
}

/// "Waiting on you", "Waiting on Nick", "Waiting on you and Ada", "Waiting on
/// 3 people". Null when it waits on nobody. The viewer reads first: it is the
/// half of the label they act on.
String? waitingOnLabel(AppLocalizations l10n, List<dynamic> people, String? viewerId) {
  if (people.isEmpty) return null;
  if (people.length > 2) return l10n.tasksWaitingOnCount(people.length);
  bool isViewer(dynamic p) => viewerId != null && tutils.principalId(p) == viewerId;
  final ordered = [...people.where(isViewer), ...people.where((p) => !isViewer(p))];
  final names = ordered.map((p) => isViewer(p) ? l10n.tasksWaitingOnYou : (tutils.principalName(p) ?? l10n.tasksWaitingOnSomeone)).toList();
  return l10n.tasksWaitingOn(joinNames(l10n, names));
}

/// The one-word label for a session's strongest relation to the task.
String sessionRelationLabel(AppLocalizations l10n, String relation) {
  switch (relation) {
    case 'linked':
      return l10n.tasksSessionRelationLinked;
    case 'created':
      return l10n.tasksSessionRelationCreated;
    case 'updated':
      return l10n.tasksSessionRelationUpdated;
    case 'commented':
      return l10n.tasksSessionRelationCommented;
    case 'referenced':
      return l10n.tasksSessionRelationReferenced;
    default:
      return relation;
  }
}

/// A short "Nov 26, 3:04 PM" for a row's time, on the device's clock and in
/// [locale]. Empty when the time can't be read.
String timelineTimeLabel(String iso, String locale) {
  final t = parseMessageTimestamp(iso);
  if (t == null) return '';
  return DateFormat.MMMd(locale).add_jm().format(t);
}
