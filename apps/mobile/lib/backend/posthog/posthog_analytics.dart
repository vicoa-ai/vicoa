import 'package:posthog_flutter/posthog_flutter.dart';

const _kPostHogToken = 'phc_zgd6NcDfsBcGhRZrJKBJfNeuP8ZL9MRTygqHscJ6xL4H';
const _kPostHogHost = 'https://us.i.posthog.com';

Future<void> initPostHog() async {
  final config = PostHogConfig(_kPostHogToken);
  config.host = _kPostHogHost;
  config.debug = false;
  config.captureApplicationLifecycleEvents = true;
  await Posthog().setup(config);
  // Tag every event fired from the mobile app with its surface, so the shared
  // PostHog project can split web-vs-app funnels (web registers source='web').
  await Posthog().register('source', 'app');
}

Future<void> posthogCapture(
  String eventName, {
  Map<String, Object>? properties,
}) async {
  await Posthog().capture(eventName: eventName, properties: properties);
}

Future<void> posthogIdentify({
  required String userId,
  Map<String, Object>? userProperties,
  Map<String, Object>? userPropertiesSetOnce,
}) async {
  await Posthog().identify(
    userId: userId,
    userProperties: userProperties,
    userPropertiesSetOnce: userPropertiesSetOnce,
  );
}

Future<void> posthogScreen(String screenName) async {
  await Posthog().screen(screenName: screenName);
}

Future<void> posthogReset() async {
  await Posthog().reset();
}
