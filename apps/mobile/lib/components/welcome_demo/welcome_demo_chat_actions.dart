import 'dart:async';

import '/app_state.dart';
import '/auth/supabase_auth/auth_util.dart';
import '/constants/welcome_demo_session.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/app_locale.dart';

/// Local interaction logic for the welcome-demo chat CTA, kept out of the large
/// agent_chat_widget.dart.
///
/// Each method drives a local-only flow (no live agent): it talks to the email
/// endpoint and appends scripted messages via [appendMessage] — the chat
/// model's `appendDemoMessage`. Passing the callback keeps this file free of
/// any dependency on the chat page's internals.
class WelcomeDemoChatActions {
  WelcomeDemoChatActions({required this.appendMessage});

  final void Function(Map<String, dynamic> message) appendMessage;

  /// "I'll set up the CLI on my computer" → email a get-started link, append
  /// the in-chat next-step instructions (whether or not the email went through),
  /// and schedule a 9pm local reminder to finish setup.
  Future<void> setUpCli() async {
    // Lead in with the "How do I start?" question, then answer with the setup
    // instructions (both moved here from the upfront script).
    appendMessage(buildSetupQuestionUserMessage());
    await _emailSetupAndRemind();
  }

  /// Shared "set up on your computer" flow: email a get-started link, append
  /// the in-chat instructions, and schedule the 9pm reminder.
  ///
  /// One-shot per device: once `FFAppState().setting.welcomeGetStartedEmailSent`
  /// is true the API call is skipped entirely so re-tapping the CTA (or
  /// re-submitting the "developer no computer" waitlist option) doesn't spam
  /// the user with duplicate emails. The instructions message is still
  /// appended, but with `emailSent: false` so the UI doesn't claim a fresh
  /// email just went out. The 9pm reminder is idempotent (fixed notification
  /// id), so always scheduling it on re-trigger just reschedules — no
  /// stacking.
  Future<void> _emailSetupAndRemind() async {
    final alreadySent = FFAppState().setting.welcomeGetStartedEmailSent;

    bool freshlySent = false;
    if (!alreadySent) {
      freshlySent = await actions.apiSendEmail('get_started');
      if (freshlySent) {
        FFAppState().updateSettingStruct(
          (e) => e..welcomeGetStartedEmailSent = true,
        );
      }
    }

    appendMessage(
      buildSetupInstructionsMessage(
        emailSent: freshlySent,
        email: currentUserEmail,
      ),
    );
    // Fire-and-forget: don't block the chat on permission prompts / scheduling.
    unawaited(actions.scheduleSetupReminder());
  }

  /// "I don't have a computer with me" → reveal the in-chat waitlist question.
  void showWaitlistQuestion() => appendMessage(buildWelcomeWaitlistMessage());

  /// Handle a submitted waitlist answer.
  ///
  /// A developer whose computer just isn't on hand is a real setup candidate —
  /// route them into the same flow as the "set up CLI" button (email + 9pm
  /// reminder). Every other option (and free-text) is recorded as a normal
  /// survey row, which upserts so re-answering overrides the prior entry.
  void submitWaitlist(String answer) {
    final trimmed = answer.trim();

    // Developer who just doesn't have their computer → route to setup.
    if (trimmed == tr().welcomeDemoWaitlistOptDev) {
      unawaited(_emailSetupAndRemind());
      return;
    }

    // Everything else is recorded as a survey answer (upsert overrides).
    unawaited(
      actions.supabaseUpsertSurvey(kWaitlistSurveyQuestion, [answer]),
    );

    // A non-developer can't use Vicoa (it needs a computer) — remind them to
    // cancel any paid plan so they aren't charged.
    if (trimmed == tr().welcomeDemoWaitlistOptNotDev) {
      appendMessage(buildCancelSubscriptionMessage());
    } else {
      appendMessage(buildWaitlistThanksMessage());
    }
  }
}
