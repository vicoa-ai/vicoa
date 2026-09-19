// Spec for the generated project-icon helpers — the Dart mirror of the web's
// `lib/project-icons.ts`. The expected hashes were produced by the web
// implementation, so a project's color is pinned to match across devices.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/project_icons.dart';

void main() {
  group('projectIdentityHash', () {
    test('matches the web hash bit-for-bit', () {
      expect(projectIdentityHash(''), 0);
      expect(projectIdentityHash('a'), 97);
      expect(projectIdentityHash('vicoa'), 112202210);
      expect(
        projectIdentityHash('3f2a9c1e-7b4d-4e8a-9f60-1c2d3e4f5a6b'),
        1750665912,
      );
      // Wraps at 32 bits (unsigned) rather than growing.
      expect(
        projectIdentityHash('d9b1e6f0-1234-4abc-8def-0123456789ab'),
        3357838468,
      );
      expect(
        projectIdentityHash(
          'very-long-seed-that-overflows-32-bits-many-times-over-and-over',
        ),
        956892199,
      );
    });

    test('hashes an astral code point by its high surrogate, like JS', () {
      expect(projectIdentityHash('🚀 rocket'), 605980695);
    });
  });

  group('projectAvatarColor', () {
    test('lands on the same palette entry as the web', () {
      expect(projectAvatarColor('vicoa'), 0xFF7A6AA8); // index 0
      expect(projectAvatarColor('a'), 0xFFB06260); // index 7
      expect(
        projectAvatarColor('3f2a9c1e-7b4d-4e8a-9f60-1c2d3e4f5a6b'),
        0xFF388068, // index 2
      );
      expect(
        projectAvatarColor('d9b1e6f0-1234-4abc-8def-0123456789ab'),
        0xFF8F7838, // index 8
      );
      expect(projectAvatarColor('Vicoa app'), 0xFF6A70B8); // index 5
    });

    test('is deterministic', () {
      expect(projectAvatarColor('same'), projectAvatarColor('same'));
    });
  });

  group('projectInitial', () {
    test('first visible character, uppercased', () {
      expect(projectInitial('vicoa'), 'V');
      expect(projectInitial('  app'), 'A');
      expect(projectInitial('ünicode'), 'Ü');
    });

    test('keeps a whole astral character', () {
      expect(projectInitial('🚀 rocket'), '🚀');
      expect(projectInitial('😀'), '😀');
    });

    test('middle dot when there is nothing to show', () {
      expect(projectInitial(''), '·');
      expect(projectInitial('   '), '·');
      expect(projectInitial(null), '·');
    });
  });
}
