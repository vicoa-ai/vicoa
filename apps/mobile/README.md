# Vicoa Mobile

Flutter app (iOS/Android) for running AI coding agents from your phone —
continue a session started on your laptop, get notified when it needs input,
review diffs and reply from anywhere.

See
`AGENTS.md` for the architecture, coding conventions, and page-building
patterns; this file only covers getting a build running.

## Prerequisites

- Flutter, managed via [FVM](https://fvm.app/) — `.fvmrc` pins the exact
  version (`3.38.5`); invoke `flutter` through FVM (`fvm flutter ...`) or
  install that Flutter version directly.
- Xcode (iOS) / Android Studio + an Android SDK (Android).
- CocoaPods for iOS (`cd ios && pod install`).

## Setup

```bash
flutter pub get
cd ios && pod install && cd ..   # iOS only
```

Supabase is configured at build time via `--dart-define` (`SUPABASE_URL`,
`SUPABASE_ANON_KEY`) — there are no defaults in the source, so a bare
`flutter run` fails with "Supabase is not configured". Point these at your own
Supabase project (see `SELF_HOSTING.md`):

```bash
cp env.example.json env.json     # then fill in your URL + anon key
```

## Running

`flutter run` can't read dart-defines from a file on its own, so use the wrapper
`run.sh`, which injects `env.json` via `--dart-define-from-file` and passes any
extra arguments straight through:

```bash
./run.sh                   # like `flutter run` (debug, connected device)
./run.sh -d chrome         # extra flags pass through to `flutter run`
./run.sh build apk         # any other flutter subcommand works too
```

Or invoke Flutter directly with the flag:

```bash
flutter run --dart-define-from-file=env.json
flutter build apk --dart-define-from-file=env.json
flutter build ios --dart-define-from-file=env.json   # then archive via Xcode
```

## Testing

```bash
flutter test
flutter analyze
```

## Structure

- `lib/` — production Dart code: `pages/`, `auth/`, `backend/`, `onboarding/`,
  `profile/`; FlutterFlow-generated scaffolding in `flutter_flow/`; hand-written
  business logic and widgets in `custom_code/`.
- `assets/` — media, declared in `pubspec.yaml`.
- `android/`, `ios/`, `web/` — platform shells.
- `test/` — unit/widget tests, mirroring `lib/`.
