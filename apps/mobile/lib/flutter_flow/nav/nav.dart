import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:page_transition/page_transition.dart';
import 'package:provider/provider.dart';

import '/backend/schema/structs/index.dart';

import '/auth/base_auth_user_provider.dart';

import '/main.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/lat_lng.dart';
import '/flutter_flow/place.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'serialization_util.dart';

import '/index.dart';
import '/onboarding/onboarding_flow.dart';

export 'package:go_router/go_router.dart';
export 'serialization_util.dart';

const kTransitionInfoKey = '__transition_info__';

GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();

const debugRouteLinkMap = {
  '/profile':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Profile',
  '/home':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Home',
  '/onboard':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Onboard',
  '/welcome':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Welcome',
  '/survey':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Survey',
  '/configureSetup':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=ConfigureSetup',
  '/authOptions':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=AuthOptions',
  '/signUp':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=SignUp',
  '/account':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
  '/usageCredits':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=UsageCredits',
  '/notification':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Notification',
  '/notificationInOnboard':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=NotificationInOnboard',
  '/credtiHistory':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=CredtiHistory',
  '/landing':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Landing',
  '/referralCode':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=ReferralCode',
  '/newsTransit':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=NewsTransit',
  '/news':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=News',
  '/impact':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=impact',
  '/rating':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=rating',
  '/tutorial':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Tutorial',
  '/helpFeedback':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=HelpFeedback',
  '/appearance':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Appearance',
  '/voiceAssistance':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=VoiceAssistance',
  '/voiceLanguage':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=VoiceLanguage',
  '/appLanguage':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=AppLanguage',
  '/agentChat':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=AgentChat',
  '/web-preview':
      'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=WebPreview'
};

class AppStateNotifier extends ChangeNotifier {
  AppStateNotifier._();

  static AppStateNotifier? _instance;
  static AppStateNotifier get instance => _instance ??= AppStateNotifier._();

  BaseAuthUser? initialUser;
  BaseAuthUser? user;
  bool showSplashImage = true;
  String? _redirectLocation;

  /// Determines whether the app will refresh and build again when a sign
  /// in or sign out happens. This is useful when the app is launched or
  /// on an unexpected logout. However, this must be turned off when we
  /// intend to sign in/out and then navigate or perform any actions after.
  /// Otherwise, this will trigger a refresh and interrupt the action(s).
  bool notifyOnAuthChange = true;

  bool get loading => user == null || showSplashImage;
  bool get loggedIn => user?.loggedIn ?? false;
  bool get initiallyLoggedIn => initialUser?.loggedIn ?? false;
  bool get shouldRedirect => loggedIn && _redirectLocation != null;

  String getRedirectLocation() => _redirectLocation!;
  bool hasRedirect() => _redirectLocation != null;
  void setRedirectLocationIfUnset(String loc) => _redirectLocation ??= loc;
  void clearRedirectLocation() => _redirectLocation = null;

  /// Mark as not needing to notify on a sign in / out when we intend
  /// to perform subsequent actions (such as navigation) afterwards.
  void updateNotifyOnAuthChange(bool notify) => notifyOnAuthChange = notify;

  void update(BaseAuthUser newUser) {
    final shouldUpdate =
        user?.uid == null || newUser.uid == null || user?.uid != newUser.uid;
    initialUser ??= newUser;
    user = newUser;
    // Refresh the app on auth change unless explicitly marked otherwise.
    // No need to update unless the user has changed.
    if (notifyOnAuthChange && shouldUpdate) {
      notifyListeners();
    }
    // Once again mark the notifier as needing to update on auth change
    // (in order to catch sign in / out events).
    updateNotifyOnAuthChange(true);
  }

  void stopShowingSplashImage() {
    showSplashImage = false;
    notifyListeners();
  }
}

GoRouter createRouter(AppStateNotifier appStateNotifier) => GoRouter(
      initialLocation: '/',
      debugLogDiagnostics: true,
      refreshListenable: appStateNotifier,
      navigatorKey: appNavigatorKey,
      errorBuilder: (context, state) =>
          appStateNotifier.loggedIn ? MainTabsWidget() : unauthedHome(),
      routes: [
        FFRoute(
          name: '_initialize',
          path: '/',
          builder: (context, _) =>
              appStateNotifier.loggedIn ? MainTabsWidget() : unauthedHome(),
        ),
        FFRoute(
          name: ProfileWidget.routeName,
          path: ProfileWidget.routePath,
          builder: (context, params) => ProfileWidget(),
        ),
        FFRoute(
          name: MachinesWidget.routeName,
          path: MachinesWidget.routePath,
          builder: (context, params) => MachinesWidget(),
        ),
        FFRoute(
          name: MachineDetailWidget.routeName,
          path: MachineDetailWidget.routePath,
          builder: (context, params) => MachineDetailWidget(
            machineId: params.getParam(
              'machineId',
              ParamType.String,
            ),
            machineData: params.getParam(
              'machineData',
              ParamType.JSON,
            ),
          ),
        ),
        FFRoute(
          name: FilesScreenWidget.routeName,
          path: FilesScreenWidget.routePath,
          builder: (context, params) => FilesScreenWidget(
            machineId: params.getParam('machineId', ParamType.String) ?? '',
            cwd: params.getParam('cwd', ParamType.String) ?? '',
            projectName: params.getParam('projectName', ParamType.String),
          ),
        ),
        FFRoute(
          name: WorktreesWidget.routeName,
          path: WorktreesWidget.routePath,
          builder: (context, params) => WorktreesWidget(
            machineId: params.getParam('machineId', ParamType.String) ?? '',
            cwd: params.getParam('cwd', ParamType.String) ?? '',
            projectName: params.getParam('projectName', ParamType.String),
          ),
        ),
        FFRoute(
          name: FileViewerWidget.routeName,
          path: FileViewerWidget.routePath,
          builder: (context, params) => FileViewerWidget(
            machineId: params.getParam('machineId', ParamType.String) ?? '',
            cwd: params.getParam('cwd', ParamType.String) ?? '',
            path: params.getParam('path', ParamType.String) ?? '',
            name: params.getParam('name', ParamType.String) ?? '',
          ),
        ),
        // Home / Tasks / Automations render inside the tabbed shell — the
        // route name is kept so existing pushNamed/goNamed callers land on
        // the right tab.
        FFRoute(
          name: HomeWidget.routeName,
          path: HomeWidget.routePath,
          builder: (context, params) => MainTabsWidget(),
        ),
        // Onboarding funnel routes (Onboard, Welcome, Survey, Personalizing,
        // Landing, …) live in the closed overlay — empty in the open build.
        ...onboardingRoutes(),
        FFRoute(
          name: AuthOptionsWidget.routeName,
          path: AuthOptionsWidget.routePath,
          builder: (context, params) => AuthOptionsWidget(),
        ),
        FFRoute(
          name: SignUpWidget.routeName,
          path: SignUpWidget.routePath,
          builder: (context, params) => SignUpWidget(
            mode: params.getParam('mode', ParamType.String),
          ),
        ),
        FFRoute(
          name: AccountWidget.routeName,
          path: AccountWidget.routePath,
          builder: (context, params) => AccountWidget(),
        ),
        FFRoute(
          name: UsageCreditsWidget.routeName,
          path: UsageCreditsWidget.routePath,
          builder: (context, params) => UsageCreditsWidget(),
        ),
        FFRoute(
          name: NotificationWidget.routeName,
          path: NotificationWidget.routePath,
          builder: (context, params) => NotificationWidget(),
        ),
        FFRoute(
          name: CredtiHistoryWidget.routeName,
          path: CredtiHistoryWidget.routePath,
          builder: (context, params) => CredtiHistoryWidget(),
        ),
        FFRoute(
          name: TutorialWidget.routeName,
          path: TutorialWidget.routePath,
          builder: (context, params) => TutorialWidget(),
        ),
        FFRoute(
          name: HelpFeedbackWidget.routeName,
          path: HelpFeedbackWidget.routePath,
          builder: (context, params) => HelpFeedbackWidget(),
        ),
        FFRoute(
          name: AppearanceWidget.routeName,
          path: AppearanceWidget.routePath,
          builder: (context, params) => AppearanceWidget(),
        ),
        FFRoute(
          name: VoiceAssistanceWidget.routeName,
          path: VoiceAssistanceWidget.routePath,
          builder: (context, params) => VoiceAssistanceWidget(),
        ),
        FFRoute(
          name: VoiceLanguageWidget.routeName,
          path: VoiceLanguageWidget.routePath,
          builder: (context, params) => VoiceLanguageWidget(),
        ),
        FFRoute(
          name: AppLanguageWidget.routeName,
          path: AppLanguageWidget.routePath,
          builder: (context, params) => AppLanguageWidget(),
        ),
        FFRoute(
          name: AgentChatWidget.routeName,
          path: AgentChatWidget.routePath,
          builder: (context, params) => AgentChatWidget(
            instanceId: params.getParam(
              'instanceId',
              ParamType.String,
            ),
            instanceData: params.getParam(
              'instanceData',
              ParamType.JSON,
            ),
            hasInitialPrompt: params.getParam(
                  'hasInitialPrompt',
                  ParamType.bool,
                ) ??
                false,
          ),
        ),
        FFRoute(
          name: StartSessionWidget.routeName,
          path: StartSessionWidget.routePath,
          builder: (context, params) => StartSessionWidget(),
        ),
        FFRoute(
          name: NewSessionWidget.routeName,
          path: NewSessionWidget.routePath,
          builder: (context, params) {
            // Optional task context (passed via `extra`) when the flow is
            // launched from a task: seeds the first prompt and links the
            // spawned session back to the task.
            final taskContext = params.getParam('taskContext', ParamType.JSON);
            return NewSessionWidget(
              taskId: taskContext is Map
                  ? taskContext['taskId']?.toString()
                  : null,
              initialPrompt: taskContext is Map
                  ? taskContext['initialPrompt']?.toString()
                  : null,
              subtaskIds: taskContext is Map && taskContext['subtaskIds'] is List
                  ? (taskContext['subtaskIds'] as List)
                      .map((e) => e.toString())
                      .toList()
                  : null,
            );
          },
        ),
        FFRoute(
          name: TasksWidget.routeName,
          path: TasksWidget.routePath,
          builder: (context, params) => MainTabsWidget(initialTab: 1),
        ),
        FFRoute(
          name: AutomationsWidget.routeName,
          path: AutomationsWidget.routePath,
          builder: (context, params) => MainTabsWidget(initialTab: 2),
        ),
        FFRoute(
          name: SearchWidget.routeName,
          path: SearchWidget.routePath,
          builder: (context, params) => SearchWidget(
            recentSessions: params.getParam(
              'recentSessions',
              ParamType.JSON,
            ),
          ),
        ),
        FFRoute(
          name: WebPreviewWidget.routeName,
          path: WebPreviewWidget.routePath,
          builder: (context, params) => WebPreviewWidget(
            initialUrl: params.getParam(
              'initialUrl',
              ParamType.String,
            ),
          ),
        ),
      ].map((r) => r.toRoute(appStateNotifier)).toList(),
      observers: [routeObserver],
    );

extension NavParamExtensions on Map<String, String?> {
  Map<String, String> get withoutNulls => Map.fromEntries(
        entries
            .where((e) => e.value != null)
            .map((e) => MapEntry(e.key, e.value!)),
      );
}

extension NavigationExtensions on BuildContext {
  void goNamedAuth(
    String name,
    bool mounted, {
    Map<String, String> pathParameters = const <String, String>{},
    Map<String, String> queryParameters = const <String, String>{},
    Object? extra,
    bool ignoreRedirect = false,
  }) =>
      !mounted || GoRouter.of(this).shouldRedirect(ignoreRedirect)
          ? null
          : goNamed(
              name,
              pathParameters: pathParameters,
              queryParameters: queryParameters,
              extra: extra,
            );

  void pushNamedAuth(
    String name,
    bool mounted, {
    Map<String, String> pathParameters = const <String, String>{},
    Map<String, String> queryParameters = const <String, String>{},
    Object? extra,
    bool ignoreRedirect = false,
  }) =>
      !mounted || GoRouter.of(this).shouldRedirect(ignoreRedirect)
          ? null
          : pushNamed(
              name,
              pathParameters: pathParameters,
              queryParameters: queryParameters,
              extra: extra,
            );

  void safePop() {
    // If there is only one route on the stack, navigate to the initial
    // page instead of popping.
    if (canPop()) {
      pop();
    } else {
      go('/');
    }
  }
}

extension GoRouterExtensions on GoRouter {
  AppStateNotifier get appState => AppStateNotifier.instance;
  void prepareAuthEvent([bool ignoreRedirect = false]) =>
      appState.hasRedirect() && !ignoreRedirect
          ? null
          : appState.updateNotifyOnAuthChange(false);
  bool shouldRedirect(bool ignoreRedirect) =>
      !ignoreRedirect && appState.hasRedirect();
  void clearRedirectLocation() => appState.clearRedirectLocation();
  void setRedirectLocationIfUnset(String location) =>
      appState.updateNotifyOnAuthChange(false);
}

extension _GoRouterStateExtensions on GoRouterState {
  Map<String, dynamic> get extraMap =>
      extra != null ? extra as Map<String, dynamic> : {};
  Map<String, dynamic> get allParams => <String, dynamic>{}
    ..addAll(pathParameters)
    ..addAll(uri.queryParameters)
    ..addAll(extraMap);
  TransitionInfo get transitionInfo => extraMap.containsKey(kTransitionInfoKey)
      ? extraMap[kTransitionInfoKey] as TransitionInfo
      : TransitionInfo.appDefault();
}

class FFParameters {
  FFParameters(this.state, [this.asyncParams = const {}]);

  final GoRouterState state;
  final Map<String, Future<dynamic> Function(String)> asyncParams;

  Map<String, dynamic> futureParamValues = {};

  // Parameters are empty if the params map is empty or if the only parameter
  // present is the special extra parameter reserved for the transition info.
  bool get isEmpty =>
      state.allParams.isEmpty ||
      (state.allParams.length == 1 &&
          state.extraMap.containsKey(kTransitionInfoKey));
  bool isAsyncParam(MapEntry<String, dynamic> param) =>
      asyncParams.containsKey(param.key) && param.value is String;
  bool get hasFutures => state.allParams.entries.any(isAsyncParam);
  Future<bool> completeFutures() => Future.wait(
        state.allParams.entries.where(isAsyncParam).map(
          (param) async {
            final doc = await asyncParams[param.key]!(param.value)
                .onError((_, __) => null);
            if (doc != null) {
              futureParamValues[param.key] = doc;
              return true;
            }
            return false;
          },
        ),
      ).onError((_, __) => [false]).then((v) => v.every((e) => e));

  dynamic getParam<T>(
    String paramName,
    ParamType type, {
    bool isList = false,
    StructBuilder<T>? structBuilder,
  }) {
    if (futureParamValues.containsKey(paramName)) {
      return futureParamValues[paramName];
    }
    if (!state.allParams.containsKey(paramName)) {
      return null;
    }
    final param = state.allParams[paramName];
    // Got parameter from `extras`, so just directly return it.
    if (param is! String) {
      return param;
    }
    // Return serialized value.
    return deserializeParam<T>(
      param,
      type,
      isList,
      structBuilder: structBuilder,
    );
  }
}

class FFRoute {
  const FFRoute({
    required this.name,
    required this.path,
    required this.builder,
    this.requireAuth = false,
    this.asyncParams = const {},
    this.routes = const [],
  });

  final String name;
  final String path;
  final bool requireAuth;
  final Map<String, Future<dynamic> Function(String)> asyncParams;
  final Widget Function(BuildContext, FFParameters) builder;
  final List<GoRoute> routes;

  GoRoute toRoute(AppStateNotifier appStateNotifier) => GoRoute(
        name: name,
        path: path,
        redirect: (context, state) {
          if (appStateNotifier.shouldRedirect) {
            final redirectLocation = appStateNotifier.getRedirectLocation();
            appStateNotifier.clearRedirectLocation();
            return redirectLocation;
          }

          if (requireAuth && !appStateNotifier.loggedIn) {
            appStateNotifier.setRedirectLocationIfUnset(state.uri.toString());
            return '/landing';
          }
          return null;
        },
        pageBuilder: (context, state) {
          fixStatusBarOniOS16AndBelow(context);
          final ffParams = FFParameters(state, asyncParams);
          final page = ffParams.hasFutures
              ? FutureBuilder(
                  future: ffParams.completeFutures(),
                  builder: (context, _) => builder(context, ffParams),
                )
              : builder(context, ffParams);
          final child = appStateNotifier.loading
              ? Container(
                  color: FlutterFlowTheme.of(context).secondaryBackground,
                  child: Column(
                    children: [
                      const Spacer(flex: 5),
                      Image.asset(
                        'assets/images/vicoa-light.webp',
                        width: 60.0,
                        fit: BoxFit.contain,
                      ),
                      const Spacer(flex: 6),
                    ],
                  ),
                )
              : page;

          final transitionInfo = state.transitionInfo;
          return transitionInfo.hasTransition
              ? CustomTransitionPage(
                  key: state.pageKey,
                  child: child,
                  transitionDuration: transitionInfo.duration,
                  transitionsBuilder:
                      (context, animation, secondaryAnimation, child) =>
                          PageTransition(
                    type: transitionInfo.transitionType,
                    duration: transitionInfo.duration,
                    reverseDuration: transitionInfo.duration,
                    alignment: transitionInfo.alignment,
                    child: child,
                  ).buildTransitions(
                    context,
                    animation,
                    secondaryAnimation,
                    child,
                  ),
                )
              : MaterialPage(key: state.pageKey, child: child);
        },
        routes: routes,
      );
}

class TransitionInfo {
  const TransitionInfo({
    required this.hasTransition,
    this.transitionType = PageTransitionType.fade,
    this.duration = const Duration(milliseconds: 400),
    this.alignment,
  });

  final bool hasTransition;
  final PageTransitionType transitionType;
  final Duration duration;
  final Alignment? alignment;

  static TransitionInfo appDefault() => TransitionInfo(hasTransition: false);
}

class RootPageContext {
  const RootPageContext(this.isRootPage, [this.errorRoute]);
  final bool isRootPage;
  final String? errorRoute;

  static bool isInactiveRootPage(BuildContext context) {
    final rootPageContext = context.read<RootPageContext?>();
    final isRootPage = rootPageContext?.isRootPage ?? false;
    final location = GoRouterState.of(context).uri.toString();
    return isRootPage &&
        location != '/' &&
        location != rootPageContext?.errorRoute;
  }

  static Widget wrap(Widget child, {String? errorRoute}) => Provider.value(
        value: RootPageContext(true, errorRoute),
        child: child,
      );
}

extension GoRouterLocationExtension on GoRouter {
  String getCurrentLocation() {
    final RouteMatch lastMatch = routerDelegate.currentConfiguration.last;
    final RouteMatchList matchList = lastMatch is ImperativeRouteMatch
        ? lastMatch.matches
        : routerDelegate.currentConfiguration;
    return matchList.uri.toString();
  }
}
