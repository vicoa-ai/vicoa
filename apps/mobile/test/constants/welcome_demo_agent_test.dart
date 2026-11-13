import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/components/agent_type_icon/agent_type_icon_widget.dart';
import 'package:vicoa/constants/welcome_demo_session.dart';

void main() {
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  group('welcome demo agent', () {
    test('Android shows Vicoa\'s own name and mark', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(welcomeDemoAgentName(), 'Vicoa');
      expect(welcomeDemoIconKey(), 'vicoa');
      expect(agentTypeHasLogo(welcomeDemoIconKey()), isTrue);
      expect(agentTypeHasLogo(welcomeDemoAgentName()), isTrue);
    });

    test('other platforms are unchanged', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      expect(welcomeDemoAgentName(), 'Claude Code');
      expect(welcomeDemoIconKey(), 'claude');
    });
  });
}
