import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kLocaleStorageKey = '__locale_key__';

class FFLocalizations {
  FFLocalizations(this.locale);

  final Locale locale;

  static FFLocalizations of(BuildContext context) =>
      Localizations.of<FFLocalizations>(context, FFLocalizations)!;

  static List<String> languages() => ['en', 'zh'];

  static late SharedPreferences _prefs;
  static Future initialize() async =>
      _prefs = await SharedPreferences.getInstance();
  static Future storeLocale(String locale) =>
      _prefs.setString(_kLocaleStorageKey, locale);
  static Locale? getStoredLocale() {
    final locale = _prefs.getString(_kLocaleStorageKey);
    return locale != null && locale.isNotEmpty ? createLocale(locale) : null;
  }

  String get languageCode => locale.toString();
  String? get languageShortCode =>
      _languagesWithShortCode.contains(locale.toString())
          ? '${locale.toString()}_short'
          : null;
  int get languageIndex => languages().contains(languageCode)
      ? languages().indexOf(languageCode)
      : 0;

  String getText(String key) =>
      (kTranslationsMap[key] ?? {})[locale.toString()] ?? '';

  String getVariableText({
    String? enText = '',
  }) =>
      [enText][languageIndex] ?? '';

  static const Set<String> _languagesWithShortCode = {
    'ar',
    'az',
    'ca',
    'cs',
    'da',
    'de',
    'dv',
    'en',
    'es',
    'et',
    'fi',
    'fr',
    'gr',
    'he',
    'hi',
    'hu',
    'it',
    'km',
    'ku',
    'mn',
    'ms',
    'no',
    'pt',
    'ro',
    'ru',
    'rw',
    'sv',
    'th',
    'uk',
    'vi',
  };
}

/// Used if the locale is not supported by GlobalMaterialLocalizations.
class FallbackMaterialLocalizationDelegate
    extends LocalizationsDelegate<MaterialLocalizations> {
  const FallbackMaterialLocalizationDelegate();

  @override
  bool isSupported(Locale locale) => _isSupportedLocale(locale);

  @override
  Future<MaterialLocalizations> load(Locale locale) async =>
      SynchronousFuture<MaterialLocalizations>(
        const DefaultMaterialLocalizations(),
      );

  @override
  bool shouldReload(FallbackMaterialLocalizationDelegate old) => false;
}

/// Used if the locale is not supported by GlobalCupertinoLocalizations.
class FallbackCupertinoLocalizationDelegate
    extends LocalizationsDelegate<CupertinoLocalizations> {
  const FallbackCupertinoLocalizationDelegate();

  @override
  bool isSupported(Locale locale) => _isSupportedLocale(locale);

  @override
  Future<CupertinoLocalizations> load(Locale locale) =>
      SynchronousFuture<CupertinoLocalizations>(
        const DefaultCupertinoLocalizations(),
      );

  @override
  bool shouldReload(FallbackCupertinoLocalizationDelegate old) => false;
}

class FFLocalizationsDelegate extends LocalizationsDelegate<FFLocalizations> {
  const FFLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) => _isSupportedLocale(locale);

  @override
  Future<FFLocalizations> load(Locale locale) =>
      SynchronousFuture<FFLocalizations>(FFLocalizations(locale));

  @override
  bool shouldReload(FFLocalizationsDelegate old) => false;
}

Locale createLocale(String language) => language.contains('_')
    ? Locale.fromSubtags(
        languageCode: language.split('_').first,
        scriptCode: language.split('_').last,
      )
    : Locale(language);

/// App UI language codes the app ships with. To support a new language, add its
/// code here and create a matching `lib/l10n/app_<code>.arb`.
const List<String> kSupportedAppLanguages = ['en', 'zh'];

/// Stored-preference value meaning "follow the device/system locale".
const String kAppLanguageSystem = 'system';

/// Resolve the effective UI language code ('en' or 'zh') from a stored
/// preference. An explicit 'en'/'zh' is honored; 'system' (or any unknown
/// value) derives from the device locale — a Chinese device shows Chinese,
/// everything else falls back to English.
String resolveAppLanguageCode(String pref) =>
    kSupportedAppLanguages.contains(pref) ? pref : _deviceAppLanguageCode();

String _deviceAppLanguageCode() {
  final deviceLocale = WidgetsBinding.instance.platformDispatcher.locale;
  return deviceLocale.languageCode.toLowerCase() == 'zh' ? 'zh' : 'en';
}

/// Whether to use Simplified-Chinese (mainland) localized variants, e.g. the
/// `<placement>_cn` paywall. Mirrors [resolveAppLanguageCode]'s precedence: an
/// explicit 'zh'/'en' preference wins (the app ships Simplified Chinese only),
/// and 'system'/unknown derives from the device locale. Traditional Chinese is
/// excluded — `Hant` script or a TW/HK/MO region returns false — so those users
/// keep the base variant. A bare `zh` (no script, no region) is treated as
/// Simplified, since mainland devices commonly report it that way.
bool isSimplifiedChineseLocale(String pref) {
  if (kSupportedAppLanguages.contains(pref)) return pref == 'zh';
  final locale = WidgetsBinding.instance.platformDispatcher.locale;
  if (locale.languageCode.toLowerCase() != 'zh') return false;
  if (locale.scriptCode == 'Hant') return false;
  final region = locale.countryCode?.toUpperCase();
  return region != 'TW' && region != 'HK' && region != 'MO';
}

/// Resolve the [Locale] for `MaterialApp.locale` from a stored preference.
Locale resolveAppLocale(String pref) => Locale(resolveAppLanguageCode(pref));

bool _isSupportedLocale(Locale locale) {
  final language = locale.toString();
  return FFLocalizations.languages().contains(
    language.endsWith('_')
        ? language.substring(0, language.length - 1)
        : language,
  );
}

final kTranslationsMap =
    <Map<String, Map<String, String>>>[].reduce((a, b) => a..addAll(b));
