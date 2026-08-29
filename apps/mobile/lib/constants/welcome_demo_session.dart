/// Sample "welcome" chat session shown to brand-new users who haven't set up
/// the Vicoa CLI yet.
///
/// This is a fully local, fake session — it never hits the backend. It gives a
/// new user a feel for what a real agent chat looks like (markdown, code
/// blocks, tables, lists, blockquotes) while introducing the product and how to
/// get started. The conversation is written as a natural Q&A: `user` messages
/// are the questions, `assistant` messages are the answers.
///
/// The flow ends with a call-to-action message (see [kWelcomeCtaMetadataKey])
/// rendering two buttons:
///   1. "I'll set up the CLI on my computer" → emails a get-started link.
///   2. "I don't have a computer with me"    → expands an in-chat
///      AskUserQuestion ([buildWelcomeWaitlistMessage]) asking what they want.
///
/// Message maps follow the same shape the real chat renderer expects:
/// `id`, `content`, `sender_type`, `created_at`, optional `message_metadata`.
library;

import '/flutter_flow/app_locale.dart';

/// Sentinel instance id for the local welcome demo session. Used across the
/// home list, router, and chat model to branch into demo behavior instead of
/// the real API/WebSocket path.
const String kWelcomeDemoInstanceId = 'welcome-to-vicoa';

/// Metadata flag marking the agent message that should render the two CTA
/// buttons (handled in agent_chat_widget, not the normal OPTIONS path).
const String kWelcomeCtaMetadataKey = 'welcome_cta';

/// Metadata flag marking a message as part of the demo flow (so the chat model
/// can recognize locally-appended demo messages).
const String kWelcomeDemoMetadataKey = 'welcome_demo';

/// True when [id] refers to the local welcome demo session.
bool isWelcomeDemoInstance(String? id) => id == kWelcomeDemoInstanceId;

/// The trailing code-demo portion of the demo-9 agent message. Kept OUT of the
/// localized string (and hardcoded English, like all code) because the fenced
/// `diff` block contains literal `{`/`}`/`${name}`, which gen_l10n's ICU parser
/// would treat as placeholder syntax and fail to compile. Concatenated after
/// `tr().welcomeDemoMsg9`.
const String _kWelcomeDemoDiffBlock =
    "```diff\n"
    "  function greeting(name) {\n"
    "-   return \"Hi \" + name;\n"
    "+   return `Hi \${name}, welcome to Vicoa! 🚀`;\n"
    "  }\n"
    "```\n\n";

/// The synthetic session/instance map that backs the welcome demo. Mirrors the
/// fields the home session list and chat header read from a real instance.
///
/// Status is `REVIEWED` so the session reads as a normal (non-closed) entry in
/// the session list rather than a greyed-out closed one. Sending is disabled
/// separately via `AgentChatModel.canSendMessages` (the demo is read-only).
/// `REVIEWED` also keeps the chat's auto-review-on-open, streaming, and
/// typing-indicator logic from firing any network calls for this fake session.
Map<String, dynamic> buildWelcomeDemoInstance() {
  final now = DateTime.now();
  return <String, dynamic>{
    'id': kWelcomeDemoInstanceId,
    'name': tr().welcomeDemoInstanceName,
    'status': 'REVIEWED',
    'agent_type': 'claude',
    'agent_type_name': 'Claude Code',
    'project': '',
    'home_dir': '',
    'started_at': now.subtract(const Duration(minutes: 6)).toIso8601String(),
    'latest_message_at': now.toIso8601String(),
    'latest_message': tr().welcomeDemoLatestMessage,
    'is_welcome_demo': true,
  };
}

/// Builds the scripted welcome conversation. Timestamps are spread over the
/// last few minutes so ordering and relative-time labels read naturally.
List<Map<String, dynamic>> buildWelcomeDemoMessages() {
  final base = DateTime.now().subtract(const Duration(minutes: 6));
  var step = 0;
  String ts() => base
      .add(Duration(seconds: 20 * step++))
      .toIso8601String();

  Map<String, dynamic> agent(String id, String content,
          {Map<String, dynamic>? metadata}) =>
      <String, dynamic>{
        'id': id,
        'content': content,
        'sender_type': 'assistant',
        'created_at': ts(),
        if (metadata != null) 'message_metadata': metadata,
      };

  Map<String, dynamic> user(String id, String content) => <String, dynamic>{
        'id': id,
        'content': content,
        'sender_type': 'user',
        'created_at': ts(),
      };

  return <Map<String, dynamic>>[
    agent(
      'demo-1',
      tr().welcomeDemoMsg1,
    ),
    user('demo-2', tr().welcomeDemoMsg2),
    agent(
      'demo-3',
      tr().welcomeDemoMsg3,
    ),
    user('demo-4', tr().welcomeDemoMsg4),
    agent(
      'demo-5',
      tr().welcomeDemoMsg5,
    ),
    user('demo-8', tr().welcomeDemoMsg8),
    agent(
      'demo-9',
      tr().welcomeDemoMsg9 + _kWelcomeDemoDiffBlock,
    ),
    agent(
      'demo-cta',
      tr().welcomeDemoCta,
      metadata: <String, dynamic>{
        kWelcomeCtaMetadataKey: true,
        kWelcomeDemoMetadataKey: true,
      },
    ),
  ];
}

/// Stable question key for the waitlist survey. Used as the `surveys.question`
/// upsert key, so re-answering overrides the prior row (onConflict
/// user_id,question). Kept English/stable even though the displayed question is
/// localized separately (see `welcomeDemoWaitlistQuestion`).
const String kWaitlistSurveyQuestion = 'What do you want to do with Vicoa?';

/// The "developer, computer not with me" option routes into the setup flow
/// (email + 9pm reminder) instead of recording a survey answer; the
/// "not a developer" option records an answer and reminds the user to cancel
/// any paid plan. Both the rendered labels and the routing matches in
/// `submitWaitlist` reference the SAME localized strings
/// (`welcomeDemoWaitlistOptDev` / `welcomeDemoWaitlistOptNotDev`) so routing
/// stays in sync with what the user sees.

/// Where users learn how to cancel their subscription.
const String kCancelSubscriptionUrl = 'https://vicoa.ai/cancel-subscription';

/// The waitlist question shown in-chat when the user taps
/// "I don't have a computer with me". Reuses the existing AskUserQuestion
/// renderer (`message_metadata.ask_user_question`). The "Type something" option
/// in that panel covers any "other" answer.
Map<String, dynamic> buildWelcomeWaitlistMessage() {
  return <String, dynamic>{
    'id': 'demo-waitlist',
    'content': tr().welcomeDemoWaitlistIntro,
    'sender_type': 'assistant',
    'created_at': DateTime.now().toIso8601String(),
    'message_metadata': <String, dynamic>{
      kWelcomeDemoMetadataKey: true,
      'ask_user_question': <String, dynamic>{
        'prompt': tr().welcomeDemoWaitlistPrompt,
        'questions': <Map<String, dynamic>>[
          <String, dynamic>{
            'question': tr().welcomeDemoWaitlistQuestion,
            'header': tr().welcomeDemoWaitlistHeader,
            'multi_select': false,
            'options': <Map<String, dynamic>>[
              <String, dynamic>{
                'label': tr().welcomeDemoWaitlistOptDev,
              },
              <String, dynamic>{
                'label': tr().welcomeDemoWaitlistOptGithub,
              },
              <String, dynamic>{
                'label': tr().welcomeDemoWaitlistOptNotDev,
              },
            ],
          },
        ],
      },
    },
  };
}

/// The "How do I start?" user bubble, shown after the user taps the "set up
/// CLI" button (moved out of the upfront script so it leads into the setup
/// instructions).
Map<String, dynamic> buildSetupQuestionUserMessage() {
  return <String, dynamic>{
    'id': 'demo-setup-question',
    'content': tr().welcomeDemoSetupQuestion,
    'sender_type': 'user',
    'created_at': DateTime.now().toIso8601String(),
    'message_metadata': <String, dynamic>{kWelcomeDemoMetadataKey: true},
  };
}

/// Local agent message appended after the user taps the "set up CLI" button.
/// Shows the (optional) "email sent" line plus the next-step instructions.
Map<String, dynamic> buildSetupInstructionsMessage({
  required bool emailSent,
  String email = '',
}) {
  final target = email.trim().isNotEmpty
      ? '**${email.trim()}**'
      : tr().welcomeDemoSetupEmailTargetFallback;
  final emailLine = emailSent ? tr().welcomeDemoSetupEmailSent(target) : '';
  return <String, dynamic>{
    'id': 'demo-setup-instructions',
    'content': "$emailLine${tr().welcomeDemoSetupInstructions}",
        // "Your sessions will show up right here. I'll give you a nudge tonight at 9pm too 🔔",
    'sender_type': 'assistant',
    'created_at': DateTime.now().toIso8601String(),
    'message_metadata': <String, dynamic>{kWelcomeDemoMetadataKey: true},
  };
}

/// Shared thank-you text for waitlist submissions (kept identical across the
/// plain thanks and the cancel-subscription variants).
String get _kWaitlistThanksText => tr().welcomeDemoWaitlistThanks;

/// Local agent confirmation appended after the user submits the waitlist
/// question.
Map<String, dynamic> buildWaitlistThanksMessage() {
  return <String, dynamic>{
    'id': 'demo-waitlist-thanks',
    'content': _kWaitlistThanksText,
    'sender_type': 'assistant',
    'created_at': DateTime.now().toIso8601String(),
    'message_metadata': <String, dynamic>{kWelcomeDemoMetadataKey: true},
  };
}

/// Same thanks text as [buildWaitlistThanksMessage], plus a reminder to cancel
/// any paid plan — a non-developer can't use Vicoa (it needs a computer), so a
/// subscription would otherwise keep charging.
Map<String, dynamic> buildCancelSubscriptionMessage() {
  return <String, dynamic>{
    'id': 'demo-cancel-subscription',
    'content': "$_kWaitlistThanksText\n\n"
        "${tr().welcomeDemoCancelSubscription(kCancelSubscriptionUrl)}",
    'sender_type': 'assistant',
    'created_at': DateTime.now().toIso8601String(),
    'message_metadata': <String, dynamic>{kWelcomeDemoMetadataKey: true},
  };
}
