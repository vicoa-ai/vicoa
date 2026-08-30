import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/pages/agent_chat/agent_chat_model.dart';

/// The ACP gear helpers only read `instanceData`, so they're testable without
/// the full FlutterFlow model lifecycle.
AgentChatModel _modelWith(Map<String, dynamic> instanceData) {
  final m = AgentChatModel();
  m.instanceData = instanceData;
  return m;
}

void main() {
  group('ACP gear helpers', () {
    test('isAcpAgent detects generic ACP agents by type name', () {
      expect(_modelWith({'agent_type_name': 'Gemini'}).isAcpAgent(), isTrue);
      expect(_modelWith({'agent_type_name': 'Cursor'}).isAcpAgent(), isTrue);
      expect(_modelWith({'agent_type_name': 'Claude Code'}).isAcpAgent(), isFalse);
      expect(_modelWith({'agent_type_name': 'Codex'}).isAcpAgent(), isFalse);
    });

    test('reads live modes/models reported onto session_config', () {
      final m = _modelWith({
        'agent_type_name': 'Cursor',
        'session_config': {
          'available_modes': [
            {'id': 'agent', 'label': 'Agent'},
            {'id': 'plan', 'label': 'Plan'},
          ],
          'current_mode': 'plan',
          'available_models': [
            {'id': 'auto', 'label': 'Auto'},
          ],
          'current_model': 'auto',
        },
      });
      expect(m.acpAvailableModes.map((e) => e['id']).toList(), ['agent', 'plan']);
      expect(m.acpCurrentMode, 'plan');
      expect(m.acpAvailableModels.map((e) => e['id']).toList(), ['auto']);
      expect(m.acpCurrentModel, 'auto');
      expect(m.hasAcpControls(), isTrue);
      expect(m.canShowAgentConfigSheet(), isTrue);
    });

    test('gear hidden for an ACP agent that advertised no controls', () {
      final m = _modelWith({'agent_type_name': 'Gemini', 'session_config': {}});
      expect(m.hasAcpControls(), isFalse);
      expect(m.canShowAgentConfigSheet(), isFalse);
    });

    test('current mode/model fall back to permission_mode / model', () {
      final m = _modelWith({
        'agent_type_name': 'Gemini',
        'session_config': {
          'permission_mode': 'yolo',
          'model': 'gemini-2.5-flash',
          'available_modes': [
            {'id': 'yolo', 'label': 'Yolo'},
          ],
        },
      });
      expect(m.acpCurrentMode, 'yolo');
      expect(m.acpCurrentModel, 'gemini-2.5-flash');
    });
  });
}
