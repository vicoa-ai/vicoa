// ignore_for_file: overridden_fields, annotate_overrides

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:shared_preferences/shared_preferences.dart';

const kThemeModeKey = '__theme_mode__';

SharedPreferences? _prefs;

abstract class FlutterFlowTheme {
  static Future initialize() async =>
      _prefs = await SharedPreferences.getInstance();

  static ThemeMode get themeMode {
    final darkMode = _prefs?.getBool(kThemeModeKey);
    return darkMode == null
        ? ThemeMode.dark
        : darkMode
            ? ThemeMode.dark
            : ThemeMode.light;
  }

  static void saveThemeMode(ThemeMode mode) => mode == ThemeMode.system
      ? _prefs?.remove(kThemeModeKey)
      : _prefs?.setBool(kThemeModeKey, mode == ThemeMode.dark);

  static FlutterFlowTheme of(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? DarkModeTheme()
        : LightModeTheme();
  }

  @Deprecated('Use primary instead')
  Color get primaryColor => primary;
  @Deprecated('Use secondary instead')
  Color get secondaryColor => secondary;
  @Deprecated('Use tertiary instead')
  Color get tertiaryColor => tertiary;

  late Color primary;
  late Color secondary;
  late Color tertiary;
  late Color alternate;
  late Color primaryText;
  late Color secondaryText;
  late Color primaryBackground;
  late Color secondaryBackground;
  late Color accent1;
  late Color accent2;
  late Color accent3;
  late Color accent4;
  late Color success;
  late Color warning;
  late Color error;
  late Color info;

  late Color themeText;
  late Color disabledButton;
  late Color tertiaryText;
  late Color primaryLight;
  late Color shadowColor;
  late Color overlayColor;
  
  late Color diffDeletedBackground;
  late Color diffDeletedText;
  late Color diffAddedBackground;
  late Color diffAddedText;
  late Color codeBlockBackground;
  late Color inlineCodeColor;

  @Deprecated('Use displaySmallFamily instead')
  String get title1Family => displaySmallFamily;
  @Deprecated('Use displaySmall instead')
  TextStyle get title1 => typography.displaySmall;
  @Deprecated('Use headlineMediumFamily instead')
  String get title2Family => typography.headlineMediumFamily;
  @Deprecated('Use headlineMedium instead')
  TextStyle get title2 => typography.headlineMedium;
  @Deprecated('Use headlineSmallFamily instead')
  String get title3Family => typography.headlineSmallFamily;
  @Deprecated('Use headlineSmall instead')
  TextStyle get title3 => typography.headlineSmall;
  @Deprecated('Use titleMediumFamily instead')
  String get subtitle1Family => typography.titleMediumFamily;
  @Deprecated('Use titleMedium instead')
  TextStyle get subtitle1 => typography.titleMedium;
  @Deprecated('Use titleSmallFamily instead')
  String get subtitle2Family => typography.titleSmallFamily;
  @Deprecated('Use titleSmall instead')
  TextStyle get subtitle2 => typography.titleSmall;
  @Deprecated('Use bodyMediumFamily instead')
  String get bodyText1Family => typography.bodyMediumFamily;
  @Deprecated('Use bodyMedium instead')
  TextStyle get bodyText1 => typography.bodyMedium;
  @Deprecated('Use bodySmallFamily instead')
  String get bodyText2Family => typography.bodySmallFamily;
  @Deprecated('Use bodySmall instead')
  TextStyle get bodyText2 => typography.bodySmall;

  String get displayLargeFamily => typography.displayLargeFamily;
  bool get displayLargeIsCustom => typography.displayLargeIsCustom;
  TextStyle get displayLarge => typography.displayLarge;
  String get displayMediumFamily => typography.displayMediumFamily;
  bool get displayMediumIsCustom => typography.displayMediumIsCustom;
  TextStyle get displayMedium => typography.displayMedium;
  String get displaySmallFamily => typography.displaySmallFamily;
  bool get displaySmallIsCustom => typography.displaySmallIsCustom;
  TextStyle get displaySmall => typography.displaySmall;
  String get headlineLargeFamily => typography.headlineLargeFamily;
  bool get headlineLargeIsCustom => typography.headlineLargeIsCustom;
  TextStyle get headlineLarge => typography.headlineLarge;
  String get headlineMediumFamily => typography.headlineMediumFamily;
  bool get headlineMediumIsCustom => typography.headlineMediumIsCustom;
  TextStyle get headlineMedium => typography.headlineMedium;
  String get headlineSmallFamily => typography.headlineSmallFamily;
  bool get headlineSmallIsCustom => typography.headlineSmallIsCustom;
  TextStyle get headlineSmall => typography.headlineSmall;
  String get titleLargeFamily => typography.titleLargeFamily;
  bool get titleLargeIsCustom => typography.titleLargeIsCustom;
  TextStyle get titleLarge => typography.titleLarge;
  String get titleMediumFamily => typography.titleMediumFamily;
  bool get titleMediumIsCustom => typography.titleMediumIsCustom;
  TextStyle get titleMedium => typography.titleMedium;
  String get titleSmallFamily => typography.titleSmallFamily;
  bool get titleSmallIsCustom => typography.titleSmallIsCustom;
  TextStyle get titleSmall => typography.titleSmall;
  String get labelLargeFamily => typography.labelLargeFamily;
  bool get labelLargeIsCustom => typography.labelLargeIsCustom;
  TextStyle get labelLarge => typography.labelLarge;
  String get labelMediumFamily => typography.labelMediumFamily;
  bool get labelMediumIsCustom => typography.labelMediumIsCustom;
  TextStyle get labelMedium => typography.labelMedium;
  String get labelSmallFamily => typography.labelSmallFamily;
  bool get labelSmallIsCustom => typography.labelSmallIsCustom;
  TextStyle get labelSmall => typography.labelSmall;
  String get bodyLargeFamily => typography.bodyLargeFamily;
  bool get bodyLargeIsCustom => typography.bodyLargeIsCustom;
  TextStyle get bodyLarge => typography.bodyLarge;
  String get bodyMediumFamily => typography.bodyMediumFamily;
  bool get bodyMediumIsCustom => typography.bodyMediumIsCustom;
  TextStyle get bodyMedium => typography.bodyMedium;
  String get bodySmallFamily => typography.bodySmallFamily;
  bool get bodySmallIsCustom => typography.bodySmallIsCustom;
  TextStyle get bodySmall => typography.bodySmall;

  Typography get typography => ThemeTypography(this);
}

class LightModeTheme extends FlutterFlowTheme {
  @Deprecated('Use primary instead')
  Color get primaryColor => primary;
  @Deprecated('Use secondary instead')
  Color get secondaryColor => secondary;
  @Deprecated('Use tertiary instead')
  Color get tertiaryColor => tertiary;

  late Color primary = const Color(0xFF416FEE);
  late Color secondary = const Color(0xFF0B67BC);
  late Color tertiary = const Color(0xFFACC420);
  late Color alternate = const Color(0xFFE0E3E7);
  late Color primaryText = const Color(0xFF161C24);
  late Color secondaryText = const Color(0xFF636F81);
  late Color primaryBackground = const Color(0xFFF0F5F9);
  late Color secondaryBackground = const Color(0xFFFFFFFF);
  late Color accent1 = const Color(0x4C2797FF);
  late Color accent2 = const Color(0x4C0B67BC);
  late Color accent3 = const Color(0x4DACC420);
  late Color accent4 = const Color(0xFFEEEEEE);
  late Color success = const Color(0xFF27AE52);
  late Color warning = const Color(0xFFFC964D);
  late Color error = const Color(0xFFEE4444);
  late Color info = const Color(0xFFFFFFFF);

  late Color themeText = const Color(0xFF161C24);
  late Color disabledButton = const Color(0xFFD4D4D4);
  late Color tertiaryText = const Color(0xFF92979B);
  late Color primaryLight = const Color(0xFFDBE7FB);
  late Color shadowColor = const Color(0x2AB2B2B2);
  late Color overlayColor = const Color(0x8CEFEFEF);
  
  late Color diffDeletedBackground = const Color(0xFFFFEBEE);
  late Color diffDeletedText = const Color(0xFFD32F2F);
  late Color diffAddedBackground = const Color(0xFFE8F5E8);
  late Color diffAddedText = const Color(0xFF388E3C);
  late Color codeBlockBackground = const Color(0xFFF5F5F5);
  late Color inlineCodeColor = const Color.fromARGB(255, 101, 107, 190);
}

abstract class Typography {
  String get displayLargeFamily;
  bool get displayLargeIsCustom;
  TextStyle get displayLarge;
  String get displayMediumFamily;
  bool get displayMediumIsCustom;
  TextStyle get displayMedium;
  String get displaySmallFamily;
  bool get displaySmallIsCustom;
  TextStyle get displaySmall;
  String get headlineLargeFamily;
  bool get headlineLargeIsCustom;
  TextStyle get headlineLarge;
  String get headlineMediumFamily;
  bool get headlineMediumIsCustom;
  TextStyle get headlineMedium;
  String get headlineSmallFamily;
  bool get headlineSmallIsCustom;
  TextStyle get headlineSmall;
  String get titleLargeFamily;
  bool get titleLargeIsCustom;
  TextStyle get titleLarge;
  String get titleMediumFamily;
  bool get titleMediumIsCustom;
  TextStyle get titleMedium;
  String get titleSmallFamily;
  bool get titleSmallIsCustom;
  TextStyle get titleSmall;
  String get labelLargeFamily;
  bool get labelLargeIsCustom;
  TextStyle get labelLarge;
  String get labelMediumFamily;
  bool get labelMediumIsCustom;
  TextStyle get labelMedium;
  String get labelSmallFamily;
  bool get labelSmallIsCustom;
  TextStyle get labelSmall;
  String get bodyLargeFamily;
  bool get bodyLargeIsCustom;
  TextStyle get bodyLarge;
  String get bodyMediumFamily;
  bool get bodyMediumIsCustom;
  TextStyle get bodyMedium;
  String get bodySmallFamily;
  bool get bodySmallIsCustom;
  TextStyle get bodySmall;
}

class ThemeTypography extends Typography {
  ThemeTypography(this.theme);

  final FlutterFlowTheme theme;

  String get displayLargeFamily => 'Source Sans 3';
  bool get displayLargeIsCustom => false;
  TextStyle get displayLarge => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.normal,
        fontSize: 57.0,
      );
  String get displayMediumFamily => 'Source Sans 3';
  bool get displayMediumIsCustom => false;
  TextStyle get displayMedium => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.normal,
        fontSize: 45.0,
      );
  String get displaySmallFamily => 'Source Sans 3';
  bool get displaySmallIsCustom => false;
  TextStyle get displaySmall => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w600,
        fontSize: 36.0,
      );
  String get headlineLargeFamily => 'Source Sans 3';
  bool get headlineLargeIsCustom => false;
  TextStyle get headlineLarge => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.normal,
        fontSize: 32.0,
      );
  String get headlineMediumFamily => 'Source Sans 3';
  bool get headlineMediumIsCustom => false;
  TextStyle get headlineMedium => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w600,
        fontSize: 32.0,
      );
  String get headlineSmallFamily => 'Source Sans 3';
  bool get headlineSmallIsCustom => false;
  TextStyle get headlineSmall => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.bold,
        fontSize: 24.0,
      );
  String get titleLargeFamily => 'Source Sans 3';
  bool get titleLargeIsCustom => false;
  TextStyle get titleLarge => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w500,
        fontSize: 24.0,
      );
  String get titleMediumFamily => 'Source Sans 3';
  bool get titleMediumIsCustom => false;
  TextStyle get titleMedium => GoogleFonts.sourceSans3(
        color: theme.info,
        fontWeight: FontWeight.w500,
        fontSize: 16.0,
      );
  String get titleSmallFamily => 'Source Sans 3';
  bool get titleSmallIsCustom => false;
  TextStyle get titleSmall => GoogleFonts.sourceSans3(
        color: theme.info,
        fontWeight: FontWeight.w500,
        fontSize: 14.0,
      );
  String get labelLargeFamily => 'Source Sans 3';
  bool get labelLargeIsCustom => false;
  TextStyle get labelLarge => GoogleFonts.sourceSans3(
        color: theme.secondaryText,
        fontWeight: FontWeight.w500,
        fontSize: 16.0,
      );
  String get labelMediumFamily => 'Source Sans 3';
  bool get labelMediumIsCustom => false;
  TextStyle get labelMedium => GoogleFonts.sourceSans3(
        color: theme.secondaryText,
        fontWeight: FontWeight.w500,
        fontSize: 14.0,
      );
  String get labelSmallFamily => 'Source Sans 3';
  bool get labelSmallIsCustom => false;
  TextStyle get labelSmall => GoogleFonts.sourceSans3(
        color: theme.secondaryText,
        fontWeight: FontWeight.w500,
        fontSize: 12.0,
      );
  String get bodyLargeFamily => 'Source Sans 3';
  bool get bodyLargeIsCustom => false;
  TextStyle get bodyLarge => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w400,
        fontSize: 17.0,
      );
  String get bodyMediumFamily => 'Source Sans 3';
  bool get bodyMediumIsCustom => false;
  TextStyle get bodyMedium => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w400,
        fontSize: 15.0,
      );
  String get bodySmallFamily => 'Source Sans 3';
  bool get bodySmallIsCustom => false;
  TextStyle get bodySmall => GoogleFonts.sourceSans3(
        color: theme.primaryText,
        fontWeight: FontWeight.w400,
        fontSize: 13.0,
      );
}

class DarkModeTheme extends FlutterFlowTheme {
  @Deprecated('Use primary instead')
  Color get primaryColor => primary;
  @Deprecated('Use secondary instead')
  Color get secondaryColor => secondary;
  @Deprecated('Use tertiary instead')
  Color get tertiaryColor => tertiary;

  late Color primary = const Color(0xFF2797FF);
  late Color secondary = const Color(0xFF0B67BC);
  late Color tertiary = const Color(0xFFACC420);
  late Color alternate = const Color(0xFF2B3743);
  late Color primaryText = const Color(0xFFFFFFFF);
  late Color secondaryText = const Color(0xFFC1CDE0);
  late Color primaryBackground = const Color(0xFF212B36);
  late Color secondaryBackground = const Color(0xFF161C24);
  late Color accent1 = const Color(0x4C2797FF);
  late Color accent2 = const Color(0x4C0B67BC);
  late Color accent3 = const Color(0x4DACC420);
  late Color accent4 = const Color(0xB3161C24);
  late Color success = const Color(0xFF27AE52);
  late Color warning = const Color(0xFFFC964D);
  late Color error = const Color(0xFFEE4444);
  late Color info = const Color(0xFFFFFFFF);

  late Color themeText = const Color(0xFFFFFFFF);
  late Color disabledButton = const Color(0xFF232F42);
  late Color tertiaryText = const Color(0xFF6B6F71);
  late Color primaryLight = const Color(0xFF414749);
  late Color shadowColor = const Color(0x19363636);
  late Color overlayColor = const Color(0x8A585858);
  
  late Color diffDeletedBackground = const Color(0xFF662A30);
  late Color diffDeletedText = const Color(0xFFFFCDD2);
  late Color diffAddedBackground = const Color(0xFF2A502A);
  late Color diffAddedText = const Color(0xFFC8E6C9);
  late Color codeBlockBackground = const Color.fromARGB(255, 30, 37, 46);
  late Color inlineCodeColor = const Color(0xFFABB0F4);
}

/// Fonts that contain CJK (Chinese) glyphs, appended as a fallback to every app
/// [TextStyle] so Chinese renders even though the primary font (Source Sans 3)
/// has no CJK glyphs. 'PingFang SC' is the iOS system font; Noto resolves on
/// Android. Add 'PingFang TC' here to cover Traditional Chinese.
const List<String> kCjkFontFallback = [
  'PingFang SC',
  'Noto Sans CJK SC',
  'Noto Sans SC',
];

extension TextStyleHelper on TextStyle {
  TextStyle override({
    TextStyle? font,
    String? fontFamily,
    Color? color,
    double? fontSize,
    FontWeight? fontWeight,
    double? letterSpacing,
    FontStyle? fontStyle,
    bool useGoogleFonts = false,
    TextDecoration? decoration,
    double? lineHeight,
    List<Shadow>? shadows,
    String? package,
  }) {
    if (useGoogleFonts && fontFamily != null) {
      font = GoogleFonts.getFont(fontFamily,
          fontWeight: fontWeight ?? this.fontWeight,
          fontStyle: fontStyle ?? this.fontStyle);
    }

    return font != null
        ? font.copyWith(
            color: color ?? this.color,
            fontSize: fontSize ?? this.fontSize,
            letterSpacing: letterSpacing ?? this.letterSpacing,
            fontWeight: fontWeight ?? this.fontWeight,
            fontStyle: fontStyle ?? this.fontStyle,
            decoration: decoration,
            height: lineHeight,
            shadows: shadows,
            fontFamilyFallback: [
              ...?font.fontFamilyFallback,
              ...kCjkFontFallback,
            ],
          )
        : copyWith(
            fontFamily: fontFamily,
            package: package,
            color: color,
            fontSize: fontSize,
            letterSpacing: letterSpacing,
            fontWeight: fontWeight,
            fontStyle: fontStyle,
            decoration: decoration,
            height: lineHeight,
            shadows: shadows,
            fontFamilyFallback: [
              ...?fontFamilyFallback,
              ...kCjkFontFallback,
            ],
          );
  }
}
