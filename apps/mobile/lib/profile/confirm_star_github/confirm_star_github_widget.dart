import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/actions/actions.dart' as action_blocks;
import '/constants/open_source.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import '/pages/gift_dialog/gift_dialog_widget.dart';

/// Opens the repo, then asks the user to confirm they starred it and grants
/// the reward — the GitHub twin of the App Store review flow
/// (openStoreListing → ConfirmRatingWidget → grantCredit).
///
/// Like that flow the confirmation is on the honour system: GitHub gives an
/// app no way to verify a star for an unauthenticated user, so the reward is
/// granted once per account ([FFAppState.githubStarClaimed]) on the user's
/// word. Returns true when the credits were granted, so callers can rebuild.
Future<bool> startGithubStarFlow(
  BuildContext context, {
  required String source,
}) async {
  logFirebaseEvent('github_star_flow_start', parameters: {'source': source});
  HapticFeedback.lightImpact();
  await openGithubUrl(kGithubRepoUrl);
  if (!context.mounted) {
    return false;
  }
  final claimed = await showModalBottomSheet<bool>(
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    enableDrag: false,
    context: context,
    builder: (sheetContext) => Padding(
      padding: MediaQuery.viewInsetsOf(sheetContext),
      child: const ConfirmStarGithubWidget(),
    ),
  );
  return claimed ?? false;
}

/// Bottom sheet that claims the "starred us on GitHub" reward. Pops with
/// `true` once the credits are granted.
class ConfirmStarGithubWidget extends StatefulWidget {
  const ConfirmStarGithubWidget({super.key});

  @override
  State<ConfirmStarGithubWidget> createState() =>
      _ConfirmStarGithubWidgetState();
}

class _ConfirmStarGithubWidgetState extends State<ConfirmStarGithubWidget> {
  bool _claiming = false;

  Future<void> _claim() async {
    if (_claiming) {
      return;
    }
    setState(() => _claiming = true);
    logFirebaseEvent('github_star_flow_claim');
    HapticFeedback.lightImpact();

    // Guard against a double grant if the sheet is somehow reopened after the
    // reward already landed (the entry points hide themselves once claimed).
    if (!FFAppState().githubStarClaimed) {
      await action_blocks.grantCredit(
        context,
        creditGranted: kGithubStarCreditReward,
        name: kGithubStarCreditName,
      );
      FFAppState().githubStarClaimed = true;
    }
    if (!mounted) {
      return;
    }

    await showDialog(
      context: context,
      builder: (dialogContext) => Dialog(
        elevation: 0,
        insetPadding: EdgeInsets.zero,
        backgroundColor: Colors.transparent,
        alignment:
            const AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
        child: GiftDialogWidget(
          text: AppLocalizations.of(context)
              .confirmStarGithubGiftText(kGithubStarCreditReward),
          buttonText: AppLocalizations.of(context).confirmStarGithubGiftButton,
        ),
      ),
    );
    if (!mounted) {
      return;
    }
    Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24.0),
          topRight: Radius.circular(24.0),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(24.0, 16.0, 24.0, 24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const SizedBox(width: 40.0),
                  Expanded(
                    child: Text(
                      l10n.confirmStarGithubTitle,
                      textAlign: TextAlign.center,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        fontSize: 20.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close_rounded,
                        color: theme.secondaryText, size: 20.0),
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context, false);
                    },
                  ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.only(top: 8.0),
                child: FaIcon(FontAwesomeIcons.github,
                    color: theme.primaryText, size: 34.0),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 16.0),
                child: Text(
                  l10n.confirmStarGithubBody,
                  textAlign: TextAlign.center,
                  style: theme.labelLarge.override(
                    font: GoogleFonts.sourceSans3(fontWeight: FontWeight.normal),
                    color: theme.secondaryText,
                    fontSize: 17.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.normal,
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 24.0),
                child: FFButtonWidget(
                  onPressed: _claiming ? null : _claim,
                  text: l10n.confirmStarGithubDoneButton,
                  options: FFButtonOptions(
                    width: 240.0,
                    height: 56.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(
                        24.0, 0.0, 24.0, 0.0),
                    color: theme.primary,
                    textStyle: theme.titleSmall.override(
                      font: GoogleFonts.sourceSans3(),
                      color: Colors.white,
                      fontSize: 18.0,
                      letterSpacing: 0.0,
                    ),
                    elevation: 2.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(24.0),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
