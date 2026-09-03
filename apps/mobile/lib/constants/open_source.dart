/// Canonical entry points into Vicoa's open-source repo.
///
/// The whole stack — CLI, daemon, backend, web, desktop and this app — is
/// AGPLv3 at github.com/vicoa-ai/vicoa, so stars, bug reports and pull
/// requests all land in the same place. Everything that links out to the repo
/// (home card, Usage & Credits, Profile, Help & Feedback) reads these, so the
/// URLs only ever have to change here.
library;

import 'package:url_launcher/url_launcher.dart';

const String kGithubRepoUrl = 'https://github.com/vicoa-ai/vicoa';
const String kGithubIssuesUrl = '$kGithubRepoUrl/issues';

/// Free messages granted once for starring the repo — the GitHub twin of the
/// 50 granted for an App Store review (see ConfirmRatingWidget).
const int kGithubStarCreditReward = 200;

/// Credit-transaction label for the reward, shown in the credit history.
const String kGithubStarCreditName = 'Star on GitHub';

/// Opens a repo link in the user's real browser instead of an in-app web view.
///
/// `launchURL`'s platform default hands http(s) to an embedded browser
/// (SFSafariViewController / Custom Tabs), which carries no GitHub session —
/// so the repo opens logged-out and the Star button asks the user to sign in.
/// The default browser (or the GitHub app, which claims these links) is
/// already signed in. Falls back to the platform default if no external
/// handler exists, so a link never silently does nothing.
Future<void> openGithubUrl(String url) async {
  final uri = Uri.parse(url);
  try {
    if (await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      return;
    }
  } catch (_) {
    // No external handler (a bare simulator, a locked-down device) — fall
    // through to the platform default rather than throwing at the caller.
  }
  await launchUrl(uri);
}
