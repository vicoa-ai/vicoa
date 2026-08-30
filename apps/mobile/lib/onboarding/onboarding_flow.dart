// Seam between the open-source app and Vicoa's closed onboarding funnel.
//
// The public build ships this lean version: there is no marketing/onboarding
// funnel in this repository, so a signed-out user goes straight to the
// sign-in / sign-up screen and no funnel routes are registered.
//
// Vicoa's hosted build replaces this file — and adds the funnel screens back
// under lib/onboarding/ — via its closed overlay build step. Keep these three
// symbols stable: nav.dart and profile/account/account_widget.dart depend on
// them, and the overlay's version of this file must expose the same signatures.
import 'package:flutter/material.dart';

import '/flutter_flow/nav/nav.dart';
import '/onboarding/auth_options/auth_options_widget.dart';

/// Extra routes contributed by the onboarding funnel. Empty in the open build.
List<FFRoute> onboardingRoutes() => const <FFRoute>[];

/// The first screen a signed-out user lands on. Open build: the auth screen.
Widget unauthedHome() => AuthOptionsWidget();

/// Route to navigate to after sign-out. Open build: the auth screen.
String unauthedHomeRoute() => AuthOptionsWidget.routeName;
