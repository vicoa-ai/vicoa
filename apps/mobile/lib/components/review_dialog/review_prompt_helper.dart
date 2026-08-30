import '/components/review_dialog/review_dialog_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:flutter/material.dart';

Future<void> maybePromptForSessionReview({
  required BuildContext context,
  required int totalSessionCount,
  Duration delay = const Duration(milliseconds: 500),
}) async {
  // Don't show review prompt if there are no sessions
  if (totalSessionCount == 0) {
    return;
  }

  final appState = FFAppState();
  final lastPromptedCount = appState.setting.lastReviewPromptedSessionCount;
  final sessionMilestones = [100, 50, 25, 10, 2];
  final milestone = sessionMilestones.firstWhere(
    (count) => totalSessionCount >= count && lastPromptedCount < count,
    orElse: () => 0,
  );
  if (milestone <= 0) {
    return;
  }

  await Future.delayed(delay);
  if (!context.mounted) {
    return;
  }

  await showDialog(
    context: context,
    builder: (context) {
      return Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: EdgeInsets.symmetric(horizontal: 24.0),
        child: ReviewDialogWidget(),
      );
    },
  );

  appState.updateSettingStruct(
    (setting) => setting.lastReviewPromptedSessionCount = milestone,
  );
}

Future<void> maybePromptForReferralReview({
  required BuildContext context,
  required int referralCount,
  Duration delay = Duration.zero,
}) async {
  final appState = FFAppState();
  final lastPromptedCount = appState.setting.lastReviewPromptedReferralCount;
  final referralMilestones = [10, 6, 3, 1];
  final milestone = referralMilestones.firstWhere(
    (count) => referralCount >= count && lastPromptedCount < count,
    orElse: () => 0,
  );
  if (milestone <= 0) {
    return;
  }

  if (delay > Duration.zero) {
    await Future.delayed(delay);
  }
  if (!context.mounted) {
    return;
  }

  await showDialog(
    context: context,
    builder: (context) {
      return Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: EdgeInsets.symmetric(horizontal: 24.0),
        child: ReviewDialogWidget(),
      );
    },
  );

  appState.updateSettingStruct(
    (setting) => setting.lastReviewPromptedReferralCount = milestone,
  );
}
