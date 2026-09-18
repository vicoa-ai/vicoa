// The two text lines of a home-page session card, as pure functions of the
// instance + the list's group-by mode (so they can be unit-tested without
// pumping the card, which pulls in theme, SVG assets and the resume registry).

String displayAgentType(String? raw) {
  if (raw == null) return 'Agent';
  if (raw.toLowerCase() == 'claude') return 'Claude Code';
  return raw;
}

bool sessionHasTitle(Map<String, dynamic> instance) =>
    instance['name']?.toString().isNotEmpty == true;

/// Latest message preview, or '' when there is none worth showing.
String sessionLatestMessage(Map<String, dynamic> instance) {
  final msg = instance['latest_message']?.toString().trim() ?? '';
  return (msg.isNotEmpty && !msg.contains('API Error') && !msg.contains('error'))
      ? msg
      : '';
}

/// Last path segment of the session's project, or ''.
String sessionProjectLabel(Map<String, dynamic> instance) {
  final project = instance['project']?.toString().trim() ?? '';
  if (project.isEmpty) return '';
  final clean = project.endsWith('/') ? project.substring(0, project.length - 1) : project;
  final last = clean.split('/').last;
  return last.isNotEmpty ? last : '';
}

/// Branch of the linked git worktree the session runs in, or null for a main
/// checkout / non-git folder. The CLI probes it at registration and the
/// backend surfaces it as `worktree_name` (older rows only carry it inside
/// `instance_metadata`). The branch a *main* checkout is on is not in the
/// payload; the home model reads it live and hands it to the card as
/// `checkoutBranch`.
String? sessionWorktreeBranch(Map<String, dynamic> instance) {
  var raw = instance['worktree_name'];
  if (raw is! String || raw.isEmpty) {
    final meta = instance['instance_metadata'];
    raw = meta is Map ? meta['worktree_name'] : null;
  }
  return raw is String && raw.isNotEmpty ? raw : null;
}

String sessionCardRow1(Map<String, dynamic> instance) {
  if (sessionHasTitle(instance)) return instance['name'] as String;
  final msg = sessionLatestMessage(instance);
  if (msg.isNotEmpty) return msg;
  return displayAgentType(instance['agent_type_name']?.toString());
}

/// Second line of the card. [branch] is rendered with a branch icon after
/// [text] (`text  ⎇ branch`, gap only, no separator); either may be empty.
///
/// A git session leads with its branch — a worktree session's own
/// `worktree_name`, else the live [checkoutBranch] the home model resolved
/// for its cwd (a detached HEAD, `''`, counts as no branch). Under "Group by
/// project" that is the whole line (the project is the header, and the branch
/// says more than the agent type or a message preview would); under
/// Time/Status the project name stays in front of it, since nothing else on
/// screen says which project the card belongs to. Sessions with no branch
/// (plain folder, or branch not resolved yet) keep the previous line.
({String text, String? branch}) sessionCardRow2(
  Map<String, dynamic> instance,
  String groupBy, {
  String? checkoutBranch,
}) {
  final branch = sessionWorktreeBranch(instance) ??
      (checkoutBranch != null && checkoutBranch.isNotEmpty ? checkoutBranch : null);
  final agentType = displayAgentType(instance['agent_type_name']?.toString());
  if (groupBy == 'Project') {
    if (branch != null) return (text: '', branch: branch);
    if (sessionHasTitle(instance)) {
      final msg = sessionLatestMessage(instance);
      return (text: msg.isNotEmpty ? msg : agentType, branch: null);
    }
    return (text: agentType, branch: null);
  }
  final label = sessionProjectLabel(instance);
  if (branch != null) return (text: label, branch: branch);
  return (text: label.isNotEmpty ? label : agentType, branch: null);
}
