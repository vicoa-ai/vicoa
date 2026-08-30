class DeepgramLanguageOption {
  const DeepgramLanguageOption({
    required this.tag,
    required this.label,
    required this.supportsNova3,
  });

  final String tag;
  final String label;
  final bool supportsNova3;

  String get recommendedModel =>
      supportsNova3 ? 'nova-3-general' : 'nova-2-general';
}

const List<DeepgramLanguageOption> deepgramLanguageOptions = [
  DeepgramLanguageOption(tag: 'en', label: 'English', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'en-US', label: 'English (US)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'en-GB', label: 'English (UK)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'en-AU', label: 'English (Australia)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'en-IN', label: 'English (India)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'en-NZ', label: 'English (New Zealand)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'zh', label: 'Chinese (Simplified)', supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'zh-CN', label: 'Chinese (Simplified, China)', supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'zh-Hans',
      label: 'Chinese (Simplified, Hans)',
      supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'zh-Hant',
      label: 'Chinese (Traditional, Hant)',
      supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'zh-HK',
      label: 'Chinese (Cantonese, Hong Kong)',
      supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'zh-TW',
      label: 'Chinese (Traditional, Taiwan)',
      supportsNova3: false),
  DeepgramLanguageOption(tag: 'es', label: 'Spanish', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'es-419', label: 'Spanish (Latin America)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'fr', label: 'French', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'fr-CA', label: 'French (Canada)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'de', label: 'German', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'de-CH', label: 'German (Switzerland)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'it', label: 'Italian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ru', label: 'Russian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ja', label: 'Japanese', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ko', label: 'Korean', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ko-KR', label: 'Korean (South Korea)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ar', label: 'Arabic', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-AE', label: 'Arabic (UAE)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-DZ', label: 'Arabic (Algeria)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-EG', label: 'Arabic (Egypt)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-IR', label: 'Arabic (Iran)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-IQ', label: 'Arabic (Iraq)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-JO', label: 'Arabic (Jordan)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-KW', label: 'Arabic (Kuwait)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-LB', label: 'Arabic (Lebanon)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-MA', label: 'Arabic (Morocco)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-PS', label: 'Arabic (Palestine)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-QA', label: 'Arabic (Qatar)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-SA', label: 'Arabic (Saudi Arabia)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-SD', label: 'Arabic (Sudan)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-SY', label: 'Arabic (Syria)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-TD', label: 'Arabic (Chad)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'ar-TN', label: 'Arabic (Tunisia)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'be', label: 'Belarusian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'bg', label: 'Bulgarian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'bn', label: 'Bengali', supportsNova3: true),
  DeepgramLanguageOption(tag: 'bs', label: 'Bosnian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ca', label: 'Catalan', supportsNova3: true),
  DeepgramLanguageOption(tag: 'cs', label: 'Czech', supportsNova3: true),
  DeepgramLanguageOption(tag: 'da', label: 'Danish', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'da-DK', label: 'Danish (Denmark)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'el', label: 'Greek', supportsNova3: true),
  DeepgramLanguageOption(tag: 'et', label: 'Estonian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'fa', label: 'Persian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'fi', label: 'Finnish', supportsNova3: true),
  DeepgramLanguageOption(tag: 'he', label: 'Hebrew', supportsNova3: true),
  DeepgramLanguageOption(tag: 'hi', label: 'Hindi', supportsNova3: true),
  DeepgramLanguageOption(tag: 'hr', label: 'Croatian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'hu', label: 'Hungarian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'id', label: 'Indonesian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'kn', label: 'Kannada', supportsNova3: true),
  DeepgramLanguageOption(tag: 'lt', label: 'Lithuanian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'lv', label: 'Latvian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'mk', label: 'Macedonian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'mr', label: 'Marathi', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ms', label: 'Malay', supportsNova3: true),
  DeepgramLanguageOption(tag: 'nl', label: 'Dutch', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'nl-BE', label: 'Flemish (Belgium)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'no', label: 'Norwegian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'pl', label: 'Polish', supportsNova3: true),
  DeepgramLanguageOption(tag: 'pt', label: 'Portuguese', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'pt-BR', label: 'Portuguese (Brazil)', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'pt-PT', label: 'Portuguese (Portugal)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ro', label: 'Romanian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ru', label: 'Russian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'sk', label: 'Slovak', supportsNova3: true),
  DeepgramLanguageOption(tag: 'sl', label: 'Slovenian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'sr', label: 'Serbian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'sv', label: 'Swedish', supportsNova3: true),
  DeepgramLanguageOption(
      tag: 'sv-SE', label: 'Swedish (Sweden)', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ta', label: 'Tamil', supportsNova3: true),
  DeepgramLanguageOption(tag: 'te', label: 'Telugu', supportsNova3: true),
  DeepgramLanguageOption(tag: 'th', label: 'Thai', supportsNova3: false),
  DeepgramLanguageOption(
      tag: 'th-TH', label: 'Thai (Thailand)', supportsNova3: false),
  DeepgramLanguageOption(tag: 'tl', label: 'Tagalog', supportsNova3: true),
  DeepgramLanguageOption(tag: 'tr', label: 'Turkish', supportsNova3: true),
  DeepgramLanguageOption(tag: 'uk', label: 'Ukrainian', supportsNova3: true),
  DeepgramLanguageOption(tag: 'ur', label: 'Urdu', supportsNova3: true),
  DeepgramLanguageOption(tag: 'vi', label: 'Vietnamese', supportsNova3: true),
];

DeepgramLanguageOption deepgramLanguageForTag(String? tag) {
  final normalized = (tag ?? '').trim();
  if (normalized.isNotEmpty) {
    for (final option in deepgramLanguageOptions) {
      if (option.tag == normalized) {
        return option;
      }
    }
  }
  return deepgramLanguageOptions.first;
}
