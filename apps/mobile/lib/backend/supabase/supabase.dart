import 'dart:io' show Platform;
import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart' hide Provider;
import '/flutter_flow/flutter_flow_util.dart';

export 'database/database.dart';

// Build-time only: --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=...
// No default here on purpose -- this is the open-source tree, so it must not
// point at Vicoa's own hosted project. Point these at your own Supabase
// project instead (see SELF_HOSTING.md).
//
// TODO(self-hosting): support pointing the mobile app at a self-hosted backend
// that uses the built-in auth provider (AUTH_PROVIDER=builtin), so Supabase is
// not required. Today auth is Supabase-only here and in auth/supabase_auth/;
// the web dashboard already supports both providers via lib/auth/.
const String _kSupabaseUrl = String.fromEnvironment('SUPABASE_URL');
const String _kSupabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

class SupaFlow {
  SupaFlow._();

  static SupaFlow? _instance;
  static SupaFlow get instance => _instance ??= SupaFlow._();

  final _supabase = Supabase.instance.client;
  static SupabaseClient get client => instance._supabase;

  static Future initialize() {
    if (_kSupabaseUrl.isEmpty || _kSupabaseAnonKey.isEmpty) {
      throw StateError(
        'Supabase is not configured. Build with '
        '--dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=... '
        'pointing at your own Supabase project (see SELF_HOSTING.md).',
      );
    }
    return Supabase.initialize(
        url: _kSupabaseUrl,
        headers: {
          'X-Client-Info': 'flutterflow',
        },
        anonKey: _kSupabaseAnonKey,
        debug: false,
        authOptions: FlutterAuthClientOptions(
          // Android strips URL fragments from deep links, so implicit flow
          // (#access_token=...) breaks OAuth callbacks there. PKCE uses
          // ?code= query params which Android preserves. iOS handles fragments
          // correctly in custom URL schemes so implicit keeps working there.
          // authFlowType: !kIsWeb && Platform.isAndroid
          //     ? AuthFlowType.pkce
          //     : AuthFlowType.implicit,
          authFlowType: AuthFlowType.pkce,
          autoRefreshToken: true,
        ),
      );
  }
}
