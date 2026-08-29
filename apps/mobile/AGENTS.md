# Repository Guidelines

These guidelines help agents contribute confidently to the Vicoa Flutter app.

## Project Overview

Vicoa is a Flutter-based vibe code app that allows running coding agents anywhere with a mobile app.

## Project Structure & Module Organization
- `lib/` holds production Dart code; feature areas live under `actions/`, `auth/`, `backend/`, `onboarding/`, `pages/`, and `profile/`, while reusable FlutterFlow scaffolding is in `flutter_flow/` and custom hooks in `custom_code/`.
- `assets/` supplies media grouped by type (e.g., `images/`, `videos/`, `rive_animations/`); declare new assets in `pubspec.yaml`.
- Platform shells reside in `android/`, `ios/`, and `web/`; managed resources such as Firebase configs live under `firebase/`.
- Tests live in `test/`; mirror `lib/` structure as coverage grows.

## Build, Test, and Development Commands

Flutter is managed via FVM (Flutter Version Manager); invoke it as `flutter`.

```bash
# Resolve dependencies (run after updating pubspec.yaml)
flutter pub get

# Clean build artifacts
flutter clean

# Run the app (debug mode)
flutter run

# Build for specific platforms
flutter build apk
flutter build ios
flutter build web

# Run tests
flutter test

# Static analysis using the shared lint rules
flutter analyze
```

### Platform-specific Commands
```bash
# iOS development (requires Xcode)
cd ios && pod install

# Android development
cd android && ./gradlew clean
```

## Code Architecture

### Core Architecture Pattern
The app follows a **FlutterFlow-generated architecture** with heavy customization:

- **State Management**: Uses Provider pattern with `FFAppState` singleton for global state
- **Navigation**: GoRouter-based routing with authentication guards
- **Backend**: Dual backend approach using both Firebase and Supabase
- **Authentication**: Custom Supabase authentication with social login support

### Key Architectural Components

#### 1. State Management (`app_state.dart`)
- `FFAppState` singleton manages all persistent app state
- Uses `SharedPreferences` for local persistence
- Structured data types with custom serialization
- Key state objects: `UserStruct`, `CreditStruct`

#### 2. Backend Services
- **Supabase**: Primary backend for user data, notes, and real-time sync
- **Firebase**: Analytics, crashlytics, and performance monitoring
- **Custom API**: to be connected

#### 3. Authentication Flow
Located in `/auth/supabase_auth/`:
- Email/password and social authentication
- JWT token management with auto-refresh
- User session persistence across app restarts

#### 4. Custom Actions (`/custom_code/actions/`)
Extensive custom Flutter code for business logic.

#### 5. Widget Architecture
- **Model-View pattern**: Each screen has a corresponding model class
- **Reusable Components**: Custom widgets in `/custom_code/widgets/`
- **Navigation**: Centralized routing in `/flutter_flow/nav/nav.dart`

## Important Development Patterns

### Custom Actions Pattern
All custom business logic is implemented as standalone action functions in `/custom_code/actions/`. Each action:
- Is a pure function with clear inputs/outputs
- Handles error cases gracefully
- Updates app state when necessary
- Follows async/await patterns

### Data Persistence Strategy
- **Local First**: All user data stored locally in `FFAppState`
- **Background Sync**: Periodic synchronization with Supabase
- **Conflict Resolution**: Last-write-wins for most data
- **Offline Support**: App functions fully offline with sync on reconnection

### Error Handling
- Custom error widget builder in `main.dart` with stack trace filtering
- Firebase Crashlytics integration for production error tracking
- Graceful degradation for network failures

### Animation Consistency
When adding new UI elements to a screen that already uses page-load animations (via `animateOnPageLoad` and `animationsMap`), apply matching animations to the new elements so the screen animates as a cohesive whole. Reuse the existing `AnimationInfo` entries in `animationsMap` when the motion (fade, slide direction, duration, curve) should match — only register a new key when a genuinely different motion is needed. This keeps screen entry transitions consistent across sections rather than having some elements pop in instantly while others animate.

### Building a New Page

Conventions for hand-written (non-FlutterFlow-generated) pages. See `lib/pages/machines/` and `lib/pages/machine_detail/` for a worked example.

**Wiring**
- A page is a `StatefulWidget` + a `FlutterFlowModel<TWidget>`. Only `initState(BuildContext)` and `dispose()` are required overrides on the model — skip the generated `toWidgetClassDebugData`/debug boilerplate. In the widget: `_model = createModel(context, () => TModel())`, drive rebuilds with `safeSetState`, and let the model own data/streams. A `void setNotify(VoidCallback)` on the model that the widget wires to `safeSetState` keeps async updates (fetch, WS, timers) out of the widget.
- Declare `static String routeName` / `static String routePath` (e.g. `'/foo/:id'`) on the widget. Register a `FFRoute` in `lib/flutter_flow/nav/nav.dart` (read params via `params.getParam('id', ParamType.String)` / `ParamType.JSON`), and `export` the widget from `lib/index.dart`. Pass non-path data through `extra: <String, dynamic>{...}` and read it back as a `ParamType.JSON` param.
- Add a Profile menu entry by duplicating an existing row in `profile_widget.dart`; register a dedicated `animationsMap` key (don't reuse another row's `AnimationInfo` instance).

**Backgrounds**
- For a full-bleed look, set the `Scaffold` and `AppBar` `backgroundColor` both to `theme.secondaryBackground` (one continuous surface), and give cards/sections `theme.primaryBackground` with a `theme.alternate` 1px border. (Dark mode: cards read lighter than the bg; light mode: subtle grey cards on white.)

**AppBar / header**
- Back button: `leading: Align(alignment: AlignmentDirectional(1.0, 0.0), child: FlutterFlowIconButton(borderRadius: 10, buttonSize: 40, fillColor: primaryBackground, icon: chevron_left @ secondaryText))`.
- A right-side action icon button MUST be wrapped in `Align(alignment: AlignmentDirectional(-1.0, 0.0), child: Padding(... FlutterFlowIconButton(...)))`. Without the `Align`, a custom `toolbarHeight` stretches the button vertically and it stops being square. (Pattern lifted from `agent_chat_widget.dart`.)
- Centered two-line header (title + subtitle): `centerTitle: true`, `toolbarHeight: 72`, `title:` a `Column(mainAxisSize: .min)` of the title `Text` (ellipsis, `maxLines: 1`) and a compact subtitle row.

**Scroll & spacing**
- Wrap the body in `SafeArea(bottom: false)` so content scrolls under the home indicator, and add the bottom breathing room yourself on the scrollable (e.g. `ListView` `padding` bottom `~32`). The last element of a page needs explicit bottom padding — it won't get any for free.
- List pages: `RefreshIndicator` + `ListView.builder` with `AlwaysScrollableScrollPhysics`. Handle loading / empty / error states, and wrap the empty & error states in a scrollable too so pull-to-refresh still works when the list is empty.

**Reuse**
- Text styles: `theme.<style>.override(font: GoogleFonts.sourceSans3(), color:, fontSize:, letterSpacing: 0.0, fontWeight:)`.
- Dialogs: `RenameDialogWidget(title:, initialValue:, placeholder:)` returns the new string (or null); `ConfirmDialogWidget(title:, content:)` returns a bool. Mirror `SessionActions` (`lib/pages/common/`) for confirm → loading → API → callback flows.
- Agent branding: `AgentTypeIconWidget(agentTypeName: 'claude'|'codex'|'opencode', size:)` renders the SVG logo (assets already declared).
- A "Caution Zone" / destructive section is a normal section card with a tappable row (label + trailing icon) and a small `secondaryText` footnote below explaining the consequence — keep it neutral-colored (match `account_widget.dart`'s delete row), not red.

**Misc**
- Use `withValues(alpha: x)`, not the deprecated `withOpacity(x)`.
- `context.pushNamed(name, pathParameters:, extra:)`, `context.pop(result)`, `context.safePop()` come from `flutter_flow_util` (it re-exports `go_router`) — don't import `package:go_router` directly.

## Coding Style & Naming Conventions
- Follow Flutter lints (see `analysis_options.yaml`); prefer idiomatic Dart with 2-space indentation and trailing commas for multi-line widgets.
- Keep widget, page, and action classes in PascalCase; private helpers start with `_camelCase`.
- Never run `flutter format` or `dart format`. Try to keep the code in one line instead of multiple lines.
- Keep files modular — don't let a file grow too long or unwieldy. Split new things into new files: create dedicated files for new widgets, components, and logic rather than piling onto an existing large file.

## Key Integrations

### Supabase Configuration
- Base URL: `https://example.supabase.co`
- Authentication flow: Implicit with auto-refresh
- Tables: Users, credit_transactions

### Firebase Services
- Analytics: User behavior tracking
- Crashlytics: Error reporting
- Performance: App performance monitoring

## Testing Guidelines
- Currently minimal test coverage. Add widget or unit tests alongside new features under `test/feature_name/`; name files `<feature>_test.dart`.
- Unit tests for custom actions in `/test/actions/`; widget tests for custom components; integration tests for critical user flows.
- Cover critical flows (auth actions, push notifications, billing) and guard against regressions introduced by FlutterFlow regenerations.

## Commit & Pull Request Guidelines
- Use concise, imperative commit summaries (e.g., "Improve Git Diff Viewer dropdown performance"), and group related changes per commit.
- Reference related issues or tasks in the description; include before/after screenshots for visible UI tweaks.
- PRs should outline scope, testing performed, and any follow-up work; request review from a maintainer familiar with the affected module.

## Development Notes

### FlutterFlow Integration
This project is generated from FlutterFlow but heavily customized:
- Do not regenerate from FlutterFlow without backing up custom code
- Custom actions and widgets are preserved between regenerations
- FlutterFlow-generated files are in `/flutter_flow/` directory

### Environment Configuration
- Development: Uses debug Firebase project
- Production: Separate Firebase project with release keys
- API endpoints configured in custom action files
