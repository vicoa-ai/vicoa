import '/app_state.dart';
import '/l10n/app_localizations.dart';
import 'internationalization.dart';

/// Context-free localization accessor for code that has no [BuildContext]
/// (custom actions, background notifications, isolates). Resolves the current
/// UI language from the stored preference in [FFAppState].
///
/// Widget code should prefer `AppLocalizations.of(context)` so it rebuilds on a
/// live language switch.
AppLocalizations tr() =>
    lookupAppLocalizations(resolveAppLocale(FFAppState().appLanguage));
