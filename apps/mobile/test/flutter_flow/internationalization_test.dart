import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/flutter_flow/internationalization.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();

  void setDeviceLocale(Locale locale) {
    binding.platformDispatcher.localeTestValue = locale;
  }

  tearDown(() => binding.platformDispatcher.clearLocaleTestValue());

  group('isSimplifiedChineseLocale', () {
    test('explicit zh preference uses Simplified regardless of device', () {
      setDeviceLocale(const Locale('en', 'US'));
      expect(isSimplifiedChineseLocale('zh'), isTrue);
    });

    test('explicit en preference never uses Simplified', () {
      setDeviceLocale(const Locale.fromSubtags(
          languageCode: 'zh', scriptCode: 'Hans', countryCode: 'CN'));
      expect(isSimplifiedChineseLocale('en'), isFalse);
    });

    group('system preference falls back to the device locale', () {
      test('non-Chinese device -> false', () {
        setDeviceLocale(const Locale('en', 'US'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });

      test('zh-Hans-CN -> true', () {
        setDeviceLocale(const Locale.fromSubtags(
            languageCode: 'zh', scriptCode: 'Hans', countryCode: 'CN'));
        expect(isSimplifiedChineseLocale('system'), isTrue);
      });

      test('bare zh (no script, no region) -> true', () {
        setDeviceLocale(const Locale('zh'));
        expect(isSimplifiedChineseLocale('system'), isTrue);
      });

      test('zh-CN (region only) -> true', () {
        setDeviceLocale(const Locale('zh', 'CN'));
        expect(isSimplifiedChineseLocale('system'), isTrue);
      });

      test('zh-SG (Simplified region) -> true', () {
        setDeviceLocale(const Locale('zh', 'SG'));
        expect(isSimplifiedChineseLocale('system'), isTrue);
      });

      test('zh-Hant-TW -> false', () {
        setDeviceLocale(const Locale.fromSubtags(
            languageCode: 'zh', scriptCode: 'Hant', countryCode: 'TW'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });

      test('zh-Hant without region -> false', () {
        setDeviceLocale(const Locale.fromSubtags(
            languageCode: 'zh', scriptCode: 'Hant'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });

      test('zh-TW (region only) -> false', () {
        setDeviceLocale(const Locale('zh', 'TW'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });

      test('zh-HK -> false', () {
        setDeviceLocale(const Locale('zh', 'HK'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });

      test('zh-MO -> false', () {
        setDeviceLocale(const Locale('zh', 'MO'));
        expect(isSimplifiedChineseLocale('system'), isFalse);
      });
    });
  });
}
