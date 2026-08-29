import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/constants/welcome_demo_session.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/index.dart';

/// A tappable "sample chat" card shown on Home to brand-new users who have no
/// real sessions yet. Tapping it opens the fully local welcome demo session
/// (see welcome_demo_session.dart) — no backend involved. Self-contained so it
/// stays out of the large home_widget.dart.
class WelcomeDemoCard extends StatelessWidget {
  const WelcomeDemoCard({super.key, this.onReturn});

  /// Called after the demo chat is popped, so Home can refresh if needed.
  final VoidCallback? onReturn;

  Future<void> _open(BuildContext context) async {
    HapticFeedback.lightImpact();
    await GoRouter.of(context).pushNamed(
      AgentChatWidget.routeName,
      pathParameters: {'instanceId': kWelcomeDemoInstanceId},
      extra: <String, dynamic>{
        'instanceData': buildWelcomeDemoInstance(),
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.rightToLeft,
        ),
      },
    );
    onReturn?.call();
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final demo = buildWelcomeDemoInstance();

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 4.0),
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(20.0),
        border: Border.all(
          color: theme.primary.withValues(alpha: 0.25),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            offset: const Offset(0, 2),
            blurRadius: 8.0,
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20.0),
          onTap: () => _open(context),
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16.0, vertical: 14.0),
            child: Row(
              children: [
                const SizedBox(
                  width: 36.0,
                  height: 36.0,
                  child: Center(
                    child: AgentTypeIconWidget(
                      agentTypeName: 'claude',
                      size: 16.0,
                      withBackground: true,
                    ),
                  ),
                ),
                const SizedBox(width: 12.0),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        demo['name']?.toString() ?? AppLocalizations.of(context).welcomeDemoCardWelcome,
                        style: theme.titleMedium.override(
                          font: GoogleFonts.sourceSans3(
                              fontWeight: FontWeight.w600),
                          fontSize: 17.0,
                          fontWeight: FontWeight.w600,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 3.0),
                      Text(
                        AppLocalizations.of(context).welcomeDemoCardTapToSee,
                        style: theme.bodySmall.override(
                          color: theme.secondaryText,
                          fontSize: 14.0,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8.0),
                Icon(
                  Icons.arrow_forward_ios_rounded,
                  size: 14.0,
                  color: theme.secondaryText.withValues(alpha: 0.6),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
