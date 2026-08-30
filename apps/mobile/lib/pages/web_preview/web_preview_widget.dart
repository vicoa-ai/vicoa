import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'web_preview_model.dart';
export 'web_preview_model.dart';

class WebPreviewWidget extends StatefulWidget {
  const WebPreviewWidget({super.key, this.initialUrl});

  static String routeName = 'WebPreview';
  static String routePath = '/web-preview';

  final String? initialUrl;

  @override
  State<WebPreviewWidget> createState() => _WebPreviewWidgetState();
}

class _WebPreviewWidgetState extends State<WebPreviewWidget> with RouteAware {
  static const _desktopScriptGroup = 'vicoa_desktop_mode';
  static const _defaultUrl = 'https://vicoa.ai';

  late WebPreviewModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  InAppWebViewController? _webController;
  late final TextEditingController _urlController;
  bool _isLoading = true;
  bool _isDesktopMode = false;
  bool _isFullScreen = false;
  bool _desktopScriptInstalled = false;
  bool _pendingDesktopNavigationReload = false;
  bool _skipNextDesktopNavigationReload = false;
  String? _ignoreNextHistoryReloadUrl;
  String _currentUrl = _defaultUrl;
  String? _pendingUrl;
  String? _replayedNavigationUrl;
  String? _loadErrorMessage;
  bool _isManualUrlEntry = false;

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => WebPreviewModel());
    PlatformInAppWebViewController.debugLoggingSettings.enabled = false;

    logFirebaseEvent('screen_view', parameters: {'screen_name': 'WebPreview'});

    _isDesktopMode = FFAppState().lastWebPreviewDesktopMode;
    _currentUrl = _resolveInitialPreviewUrl();
    _urlController = TextEditingController(text: _currentUrl);

    _isLoading = true;
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    _isFullScreen = false;
    _urlController.dispose();
    _model.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(WebPreviewWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    _model.widget = widget;

    // Don't override manual URL entries
    if (_isManualUrlEntry) {
      return;
    }

    // Only update if the incoming initialUrl has changed
    // This prevents overriding user's manual URL changes
    if (widget.initialUrl != oldWidget.initialUrl) {
      final nextUrl = _resolveInitialPreviewUrl();
      if (nextUrl == _currentUrl) {
        return;
      }
      _setCurrentUrl(nextUrl, syncTextField: true, persist: false);
      if (_webController == null || kIsWeb) {
        _pendingUrl = nextUrl;
        return;
      }
      setState(() {
        _isLoading = true;
      });
      _pendingDesktopNavigationReload = _isDesktopMode;
      Future(() async {
        if (!mounted || _webController == null || kIsWeb) {
          return;
        }
        await _applyPlatformModeSettings();
        if (!mounted) {
          return;
        }
        await _webController!.loadUrl(
          urlRequest: URLRequest(url: WebUri.uri(_normalizeUri(nextUrl))),
        );
      });
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = DebugModalRoute.of(context);
    if (route != null) {
      routeObserver.subscribe(this, route);
    }
    debugLogGlobalProperty(context);
  }

  @override
  void didPopNext() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
    Future(() async {
      if (!mounted) {
        return;
      }
      if (_webController != null && !kIsWeb) {
        await _applyPlatformModeSettings();
        await _applyViewportProfile();
        final currentUri = _normalizeUri(_currentUrl);
        await _webController!
            .loadUrl(urlRequest: URLRequest(url: WebUri.uri(currentUri)));
      }
    });
  }

  @override
  void didPush() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
  }

  @override
  void didPop() {
    _model.isRouteVisible = false;
  }

  @override
  void didPushNext() {
    _model.isRouteVisible = false;
  }

  Uri _normalizeUri(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) {
      return Uri.parse(_currentUrl);
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return Uri.parse(trimmed);
    }
    return Uri.parse('https://$trimmed');
  }

  String _resolveInitialPreviewUrl() {
    final cachedUrl = FFAppState().lastWebPreviewUrl.trim();
    final incomingUrl = widget.initialUrl?.trim() ?? '';

    // If there's an incoming URL from navigation (e.g., from agent chat)
    if (incomingUrl.isNotEmpty) {
      final normalizedIncoming = _normalizeUri(incomingUrl).toString();

      // If no cached URL, use and cache the incoming URL
      if (cachedUrl.isEmpty) {
        FFAppState().setLastWebPreviewUrl(normalizedIncoming);
        return normalizedIncoming;
      }

      final normalizedCached = _normalizeUri(cachedUrl).toString();

      // If URLs are identical, use cached (maintains user's last state)
      if (normalizedIncoming == normalizedCached) {
        return normalizedCached;
      }

      // Check if the URLs are from the same origin (host)
      final incomingHost = _extractHost(normalizedIncoming);
      final cachedHost = _extractHost(normalizedCached);

      // If same host (e.g., same ngrok URL), prefer cached URL to maintain state
      // But if different host, use the new incoming URL
      if (incomingHost == cachedHost && incomingHost.isNotEmpty) {
        return normalizedCached;
      }

      // Different origin, update cache and use new URL
      FFAppState().setLastWebPreviewUrl(normalizedIncoming);
      return normalizedIncoming;
    }

    // No incoming URL, use cached or default
    if (cachedUrl.isNotEmpty) {
      return _normalizeUri(cachedUrl).toString();
    }
    return _defaultUrl;
  }

  String _extractHost(String url) {
    try {
      final uri = Uri.parse(url);
      return uri.host.trim().toLowerCase();
    } catch (_) {
      return '';
    }
  }

  void _setCurrentUrl(
    String nextUrl, {
    bool syncTextField = false,
    bool persist = false,
  }) {
    final normalizedUrl = _normalizeUri(nextUrl).toString();
    final needsStateUpdate =
        _currentUrl != normalizedUrl || (syncTextField && _urlController.text != normalizedUrl);
    if (needsStateUpdate) {
      setState(() {
        _currentUrl = normalizedUrl;
        if (syncTextField) {
          _urlController.text = normalizedUrl;
        }
      });
    } else if (syncTextField && _urlController.text != normalizedUrl) {
      _urlController.text = normalizedUrl;
    }
    if (persist) {
      FFAppState().setLastWebPreviewUrl(normalizedUrl);
    }
  }

  String _desktopUserAgent() {
    return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36';
  }

  String _mobileUserAgent() {
    return 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) '
        'Version/17.0 Mobile/15E148 Safari/604.1';
  }

  Future<void> _applyViewportProfile() async {
    if (kIsWeb || _webController == null) {
      return;
    }

    final script = _isDesktopMode
        ? '''
(() => {
  const targetWidth = 1200;
  const head = document.head || document.getElementsByTagName('head')[0];
  if (!head) return;
  let meta = document.querySelector('meta[name="viewport"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'viewport';
    head.appendChild(meta);
  }
  meta.setAttribute('content', 'width=' + targetWidth + ', initial-scale=1, maximum-scale=5, user-scalable=yes');
  window.dispatchEvent(new Event('resize'));
})();
'''
        : '''
(() => {
  const head = document.head || document.getElementsByTagName('head')[0];
  if (!head) return;
  let meta = document.querySelector('meta[name="viewport"]');
  if (!meta) {
    meta = document.createElement('meta');
    meta.name = 'viewport';
    head.appendChild(meta);
  }
  meta.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=5, user-scalable=yes');
})();
''';

    try {
      await _webController!.evaluateJavascript(source: script);
    } catch (_) {}
  }

  Future<void> _ensureDesktopUserScript() async {
    if (kIsWeb || _webController == null) {
      return;
    }

    if (!_isDesktopMode) {
      // Always attempt cleanup when entering phone mode.
      try {
        await _webController!.removeUserScriptsByGroupName(
          groupName: _desktopScriptGroup,
        );
      } catch (_) {}
      _desktopScriptInstalled = false;
      return;
    }

    if (_desktopScriptInstalled) {
      return;
    }

    const source = '''
(() => {
  const targetWidth = 1200;
  const currentWidth = Math.max(
    document.documentElement?.clientWidth || 0,
    window.innerWidth || 0
  );
  const fitScale = Math.max(0.2, Math.min(1, (currentWidth / targetWidth) * 0.4));
  const viewportContent =
    'width=' + targetWidth +
    ', initial-scale=' + fitScale +
    ', minimum-scale=0.2, maximum-scale=5, user-scalable=yes';

  const ensureViewport = () => {
    const head = document.head || document.getElementsByTagName('head')[0];
    if (!head) return;
    let meta = document.querySelector('meta[name="viewport"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'viewport';
      head.appendChild(meta);
    }
    if (meta.getAttribute('content') !== viewportContent) {
      meta.setAttribute('content', viewportContent);
    }
  };

  ensureViewport();
  document.addEventListener('readystatechange', ensureViewport);
  window.addEventListener('load', ensureViewport, { once: false });

  const observer = new MutationObserver(() => ensureViewport());
  observer.observe(document.documentElement || document, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['content', 'name'],
  });

  try {
    Object.defineProperty(window, 'innerWidth', { get: () => targetWidth, configurable: true });
    Object.defineProperty(window, 'outerWidth', { get: () => targetWidth, configurable: true });
    Object.defineProperty(screen, 'width', { get: () => targetWidth, configurable: true });
    Object.defineProperty(screen, 'availWidth', { get: () => targetWidth, configurable: true });
  } catch (e) {}
})();
''';

    try {
      await _webController!.addUserScript(
        userScript: UserScript(
          groupName: _desktopScriptGroup,
          source: source,
          injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
        ),
      );
      _desktopScriptInstalled = true;
    } catch (_) {}
  }

  InAppWebViewSettings _buildWebSettings() {
    return InAppWebViewSettings(
      javaScriptEnabled: true,
      userAgent: _isDesktopMode ? _desktopUserAgent() : _mobileUserAgent(),
      useWideViewPort: _isDesktopMode,
      loadWithOverviewMode: _isDesktopMode,
      useShouldOverrideUrlLoading: true,
      supportMultipleWindows: false,
      javaScriptCanOpenWindowsAutomatically: false,
      supportZoom: true,
      builtInZoomControls: true,
      displayZoomControls: false,
      preferredContentMode: _isDesktopMode
          ? UserPreferredContentMode.DESKTOP
          : UserPreferredContentMode.MOBILE,
    );
  }

  Future<void> _applyPlatformModeSettings() async {
    if (_webController == null) {
      return;
    }
    await _ensureDesktopUserScript();
    await _webController!.setSettings(settings: _buildWebSettings());
  }

  Future<void> _switchPreviewMode(bool desktopMode) async {
    if (_isDesktopMode == desktopMode) {
      return;
    }
    setState(() {
      _isDesktopMode = desktopMode;
      _isLoading = true;
    });
    FFAppState().setLastWebPreviewDesktopMode(desktopMode);
    _pendingDesktopNavigationReload = false;
    _skipNextDesktopNavigationReload = false;
    FFAppState().updateSettingStruct((e) {
      e.lastUpdatedAt = getCurrentTimestamp;
    });
    final uri = _normalizeUri(_currentUrl);
    if (_webController == null || kIsWeb) {
      _pendingUrl = uri.toString();
      return;
    }
    await _applyPlatformModeSettings();
    await _applyViewportProfile();
    await _webController!.loadUrl(urlRequest: URLRequest(url: WebUri.uri(uri)));
  }

  Future<void> _setFullScreen(bool enabled) async {
    setState(() {
      _isFullScreen = enabled;
    });
  }

  Future<NavigationActionPolicy> _handleNavigationOverride(
    InAppWebViewController controller,
    NavigationAction navigationAction,
  ) async {
    final requestUrl = navigationAction.request.url;
    if (requestUrl == null) {
      return NavigationActionPolicy.ALLOW;
    }
    final requestUrlString = requestUrl.toString();

    // Allow replayed navigation to proceed
    if (_replayedNavigationUrl == requestUrlString) {
      _replayedNavigationUrl = null;
      await _ensureDesktopUserScript();
      await controller.setSettings(settings: _buildWebSettings());
      return NavigationActionPolicy.ALLOW;
    }

    // Allow manual URL entries to proceed directly without replay
    if (_isManualUrlEntry) {
      await _ensureDesktopUserScript();
      await controller.setSettings(settings: _buildWebSettings());
      return NavigationActionPolicy.ALLOW;
    }

    final isMainFrame = navigationAction.isForMainFrame;
    final method = (navigationAction.request.method ?? 'GET').toUpperCase();
    final shouldReplay = isMainFrame && method == 'GET';

    if (!shouldReplay) {
      return NavigationActionPolicy.ALLOW;
    }

    if (_skipNextDesktopNavigationReload) {
      _skipNextDesktopNavigationReload = false;
      return NavigationActionPolicy.ALLOW;
    }

    // ALWAYS ensure settings are applied for main frame navigations
    // This is necessary because each new page might override viewport settings
    await _ensureDesktopUserScript();
    await controller.setSettings(settings: _buildWebSettings());

    // Cancel original navigation and reload with correct settings
    if (_isDesktopMode) {
      _pendingDesktopNavigationReload = true;
    }
    _replayedNavigationUrl = requestUrlString;
    await controller.loadUrl(urlRequest: URLRequest(url: requestUrl));
    return NavigationActionPolicy.CANCEL;
  }

  Future<void> _goToTypedUrl() async {
    final raw = _urlController.text.trim();
    if (raw.isEmpty) {
      return;
    }
    FocusScope.of(context).unfocus();
    final uri = _normalizeUri(raw);

    // Mark this as a manual URL entry
    _isManualUrlEntry = true;

    setState(() {
      _isLoading = true;
      _loadErrorMessage = null;
    });

    // For manual entry, always update cache and navigate to the typed URL
    _setCurrentUrl(uri.toString(), syncTextField: true, persist: true);

    if (_webController == null || kIsWeb) {
      _pendingUrl = uri.toString();
      _isManualUrlEntry = false;
      return;
    }

    if (_isDesktopMode) {
      _pendingDesktopNavigationReload = true;
    }
    await _applyPlatformModeSettings();
    await _webController!.loadUrl(urlRequest: URLRequest(url: WebUri.uri(uri)));

    // Reset the flag after a short delay to ensure it's caught by the navigation handler
    Future.delayed(const Duration(milliseconds: 500), () {
      _isManualUrlEntry = false;
    });
  }

  void _updateCurrentUrl(WebUri? url) {
    if (url == null) {
      return;
    }
    _setCurrentUrl(url.toString(), syncTextField: true, persist: true);
  }

  String _formatLoadErrorMessage(String? details) {
    final l10n = AppLocalizations.of(context);
    if (details == null || details.trim().isEmpty) {
      return l10n.webPreviewUrlUnreachableHint;
    }
    return l10n.webPreviewUrlUnreachableDetails(details);
  }

  Widget _buildLoadErrorOverlay() {
    final theme = FlutterFlowTheme.of(context);
    if (_loadErrorMessage == null || _loadErrorMessage!.isEmpty || _isLoading) {
      return const SizedBox.shrink();
    }
    return Container(
      color: theme.primaryBackground,
      alignment: Alignment.center,
      padding: EdgeInsets.fromLTRB(24.0, 0.0, 24.0, 24.0),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: 420.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72.0,
              height: 72.0,
              decoration: BoxDecoration(
                color: theme.secondaryText.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(36.0),
              ),
              child: Icon(
                Icons.error_outline,
                size: 34.0,
              ),
            ),
            SizedBox(height: 18.0),
            Text(
              AppLocalizations.of(context).webPreviewSiteUnreachable,
              textAlign: TextAlign.center,
              style: theme.headlineSmall.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: 10.0),
            Text(
              _loadErrorMessage!,
              textAlign: TextAlign.center,
              style: theme.bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
                color: theme.secondaryText,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInAppWebView() {
    return InAppWebView(
      initialSettings: _buildWebSettings(),
      onWebViewCreated: (controller) async {
        _webController = controller;

        _desktopScriptInstalled = false;
        await _ensureDesktopUserScript();

        final queued = _pendingUrl ?? _currentUrl;
        _pendingUrl = null;
        final uri = _normalizeUri(queued);
        setState(() {
          _isLoading = true;
          _loadErrorMessage = null;
        });
        _setCurrentUrl(uri.toString(), syncTextField: true, persist: true);
        await _applyPlatformModeSettings();
        await controller.loadUrl(
          urlRequest: URLRequest(url: WebUri.uri(uri)),
        );
      },
      shouldOverrideUrlLoading: (controller, navigationAction) async {
        return _handleNavigationOverride(
          controller,
          navigationAction,
        );
      },
      onCreateWindow: (controller, createWindowAction) async {
        final targetUrl = createWindowAction.request.url;
        if (targetUrl != null) {
          _updateCurrentUrl(targetUrl);
          await _applyPlatformModeSettings();
          await controller.loadUrl(
            urlRequest: URLRequest(url: targetUrl),
          );
        }
        return false;
      },
      onLoadStart: (controller, url) async {
        if (!mounted) {
          return;
        }
        if (_isDesktopMode) {
          await _applyPlatformModeSettings();
        }
        setState(() {
          _isLoading = true;
          _loadErrorMessage = null;
        });
        _updateCurrentUrl(url);
      },
      onLoadStop: (controller, url) async {
        await _applyViewportProfile();
        if (!mounted) {
          return;
        }
        if (_isDesktopMode && _pendingDesktopNavigationReload && !_isManualUrlEntry) {
          _pendingDesktopNavigationReload = false;
          _skipNextDesktopNavigationReload = true;
          _ignoreNextHistoryReloadUrl = (url?.toString().isNotEmpty ?? false)
              ? url.toString()
              : _currentUrl;
          await _applyPlatformModeSettings();
          await controller.reload();
          return;
        }
        _pendingDesktopNavigationReload = false;
        setState(() {
          _isLoading = false;
          _loadErrorMessage = null;
        });
        _updateCurrentUrl(url);
      },
      onUpdateVisitedHistory: (controller, url, androidIsReload) async {
        if (!mounted) {
          return;
        }
        if (url == null) {
          return;
        }
        final historyUrl = url.toString();
        final previousUrl = _currentUrl;
        if (_ignoreNextHistoryReloadUrl == historyUrl) {
          _ignoreNextHistoryReloadUrl = null;
          _updateCurrentUrl(url);
          return;
        }
        _updateCurrentUrl(url);
        if (!_isDesktopMode) {
          return;
        }
        if (historyUrl == previousUrl) {
          return;
        }
        if (androidIsReload == true) {
          return;
        }
        if (_isManualUrlEntry) {
          return;
        }
        _pendingDesktopNavigationReload = false;
        _skipNextDesktopNavigationReload = true;
        _ignoreNextHistoryReloadUrl = historyUrl;
        setState(() {
          _isLoading = true;
          _loadErrorMessage = null;
        });
        await _applyPlatformModeSettings();
        await controller.reload();
      },
      onReceivedError: (controller, request, error) {
        if (!mounted) {
          return;
        }
        _pendingDesktopNavigationReload = false;
        _skipNextDesktopNavigationReload = false;
        _ignoreNextHistoryReloadUrl = null;
        setState(() {
          _isLoading = false;
          _loadErrorMessage = _formatLoadErrorMessage(error.description);
        });
      },
      onReceivedHttpError: (controller, request, response) {
        if (!mounted || request.isForMainFrame != true) {
          return;
        }
        setState(() {
          _isLoading = false;
          _loadErrorMessage = _formatLoadErrorMessage(
            AppLocalizations.of(context)
                .webPreviewHttpStatus(response.statusCode ?? 0),
          );
        });
      },
    );
  }

  Widget _buildModeButtons() {
    final theme = FlutterFlowTheme.of(context);

    return Container(
      height: 36.0,
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(10.0),
        border: Border.all(color: theme.alternate),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(9.0),
            onTap: () async {
              if (_isDesktopMode) {
                return;
              }
              HapticFeedback.lightImpact();
              await _switchPreviewMode(true);
            },
            child: Container(
              width: 44.0,
              height: 32.0,
              decoration: BoxDecoration(
                color: _isDesktopMode ? theme.alternate : Colors.transparent,
                borderRadius: BorderRadius.circular(8.0),
              ),
              child: Icon(
                Icons.desktop_windows_rounded,
                size: 18.0,
                color: _isDesktopMode ? theme.primaryText : theme.secondaryText,
              ),
            ),
          ),
          InkWell(
            borderRadius: BorderRadius.circular(9.0),
            onTap: () async {
              if (!_isDesktopMode) {
                return;
              }
              HapticFeedback.lightImpact();
              await _switchPreviewMode(false);
            },
            child: Container(
              width: 44.0,
              height: 32.0,
              decoration: BoxDecoration(
                color: !_isDesktopMode ? theme.alternate : Colors.transparent,
                borderRadius: BorderRadius.circular(8.0),
              ),
              child: Icon(
                Icons.smartphone_rounded,
                size: 18.0,
                color:
                    !_isDesktopMode ? theme.primaryText : theme.secondaryText,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopControls() {
    final theme = FlutterFlowTheme.of(context);

    return Container(
      margin: EdgeInsetsDirectional.fromSTEB(12.0, 10.0, 12.0, 8.0),
      padding: EdgeInsetsDirectional.fromSTEB(10.0, 8.0, 10.0, 8.0),
      decoration: BoxDecoration(
        color: theme.secondaryBackground.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(14.0),
        border: Border.all(color: theme.alternate),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Container(
                  height: 40.0,
                  decoration: BoxDecoration(
                    color: theme.primaryBackground,
                    borderRadius: BorderRadius.circular(10.0),
                  ),
                  child: TextFormField(
                    controller: _urlController,
                    maxLines: 1,
                    textAlignVertical: TextAlignVertical.center,
                    decoration: InputDecoration(
                      isDense: true,
                      hintText: AppLocalizations.of(context).webPreviewEnterUrl,
                      border: InputBorder.none,
                      contentPadding:
                          EdgeInsetsDirectional.fromSTEB(12.0, 12.0, 12.0, 8.0),
                    ),
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      letterSpacing: 0.0,
                    ),
                    onFieldSubmitted: (value) async {
                      HapticFeedback.lightImpact();
                      await _goToTypedUrl();
                    },
                  ),
                ),
              ),
              SizedBox(width: 8.0),
              FlutterFlowIconButton(
                borderColor: Colors.transparent,
                borderRadius: 10.0,
                borderWidth: 1.0,
                buttonSize: 40.0,
                fillColor: theme.primaryBackground,
                icon: Icon(
                  Icons.arrow_forward_rounded,
                  color: theme.primaryText,
                  size: 20.0,
                ),
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  await _goToTypedUrl();
                },
              ),
            ],
          ),
          SizedBox(height: 8.0),
          Row(
            children: [
              _buildModeButtons(),
              Spacer(),
              FlutterFlowIconButton(
                borderColor: Colors.transparent,
                borderRadius: 10.0,
                borderWidth: 1.0,
                buttonSize: 36.0,
                fillColor: theme.primaryBackground,
                icon: Icon(
                  Icons.arrow_back_rounded,
                  color: theme.secondaryText,
                  size: 18.0,
                ),
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  await _applyPlatformModeSettings();
                  await _webController?.goBack();
                },
              ),
              SizedBox(width: 6.0),
              FlutterFlowIconButton(
                borderColor: Colors.transparent,
                borderRadius: 10.0,
                borderWidth: 1.0,
                buttonSize: 36.0,
                fillColor: theme.primaryBackground,
                icon: Icon(
                  Icons.arrow_forward_rounded,
                  color: theme.secondaryText,
                  size: 18.0,
                ),
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  await _applyPlatformModeSettings();
                  await _webController?.goForward();
                },
              ),
              SizedBox(width: 6.0),
              FlutterFlowIconButton(
                borderColor: Colors.transparent,
                borderRadius: 10.0,
                borderWidth: 1.0,
                buttonSize: 36.0,
                fillColor: theme.primaryBackground,
                icon: Icon(
                  Icons.refresh_rounded,
                  color: theme.secondaryText,
                  size: 18.0,
                ),
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  await _applyPlatformModeSettings();
                  await _webController?.reload();
                },
              ),
              SizedBox(width: 6.0),
              FlutterFlowIconButton(
                borderColor: Colors.transparent,
                borderRadius: 10.0,
                borderWidth: 1.0,
                buttonSize: 36.0,
                fillColor: theme.primaryBackground,
                icon: Icon(
                  Icons.help_outline_rounded,
                  color: theme.secondaryText,
                  size: 18.0,
                ),
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  await launchURL('https://vicoa.ai/docs/live-preview');
                },
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildWebSurface() {
    final theme = FlutterFlowTheme.of(context);
    final phoneWidth = 390.0;
    final phoneHeight = 844.0;

    return Expanded(
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(
          _isFullScreen ? 0.0 : 12.0,
          0.0,
          _isFullScreen ? 0.0 : 12.0,
          _isFullScreen ? 0.0 : 12.0,
        ),
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(_isFullScreen ? 0.0 : 14.0),
            border: _isFullScreen
                ? null
                : Border.all(
                    color: theme.alternate,
                  ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(_isFullScreen ? 0.0 : 14.0),
            child: Stack(
              children: [
                if (kIsWeb)
                  Center(
                    child: Padding(
                      padding: EdgeInsets.all(16.0),
                      child: Text(
                        AppLocalizations.of(context).webPreviewWebUnavailable,
                        textAlign: TextAlign.center,
                        style: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          letterSpacing: 0.0,
                        ),
                      ),
                    ),
                  )
                else
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final usePhoneFrame = !_isDesktopMode && !_isFullScreen;
                      final targetWidth = usePhoneFrame
                          ? (constraints.maxWidth < phoneWidth
                              ? constraints.maxWidth
                              : phoneWidth)
                          : constraints.maxWidth;
                      final targetHeight = usePhoneFrame
                          ? (constraints.maxHeight < phoneHeight
                              ? constraints.maxHeight
                              : phoneHeight)
                          : constraints.maxHeight;

                      return Center(
                        child: SizedBox(
                          width: targetWidth,
                          height: targetHeight,
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(
                              usePhoneFrame ? 24.0 : 0.0,
                            ),
                            child: _buildInAppWebView(),
                          ),
                        ),
                      );
                    },
                  ),
                if (_isLoading && !kIsWeb)
                  Align(
                    alignment: Alignment.center,
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(
                        theme.primary,
                      ),
                    ),
                  ),
                if (!kIsWeb) _buildLoadErrorOverlay(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)
        ?.parentModelCallback
        ?.call(_model);
    context.watch<FFAppState>();

    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
      },
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
        appBar: AppBar(
          backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
          automaticallyImplyLeading: false,
          leading: Align(
            alignment: AlignmentDirectional(1.0, 0.0),
            child: FlutterFlowIconButton(
              borderColor: Colors.transparent,
              borderRadius: 10.0,
              borderWidth: 1.0,
              buttonSize: 40.0,
              fillColor: FlutterFlowTheme.of(context).primaryBackground,
              icon: Icon(
                Icons.chevron_left_rounded,
                color: FlutterFlowTheme.of(context).secondaryText,
                size: 24.0,
              ),
              onPressed: () async {
                HapticFeedback.lightImpact();
                context.safePop();
              },
            ),
          ),
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                AppLocalizations.of(context).webPreviewTitle,
                style: FlutterFlowTheme.of(context).titleLarge.override(
                      font: GoogleFonts.sourceSans3(
                        fontWeight:
                            FlutterFlowTheme.of(context).titleLarge.fontWeight,
                        fontStyle:
                            FlutterFlowTheme.of(context).titleLarge.fontStyle,
                      ),
                      letterSpacing: 0.0,
                    ),
              ),
              Padding(
                padding: EdgeInsetsDirectional.fromSTEB(6.0, 0.0, 0.0, 0.0),
                child: Text(
                  AppLocalizations.of(context).webPreviewBeta,
                  style: FlutterFlowTheme.of(context).bodySmall.override(
                        font: GoogleFonts.sourceSans3(
                          fontWeight: FontWeight.w600,
                          fontStyle:
                              FlutterFlowTheme.of(context).bodySmall.fontStyle,
                        ),
                        fontSize: 10.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                        color: FlutterFlowTheme.of(context).secondaryText,
                      ),
                ),
              ),
            ],
          ),
          actions: [
            Align(
              alignment: AlignmentDirectional(-1.0, 0.0),
              child: Padding(
                padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 10.0, 0.0),
                child: FlutterFlowIconButton(
                  borderColor: Colors.transparent,
                  borderRadius: 10.0,
                  borderWidth: 1.0,
                  buttonSize: 40.0,
                  fillColor: FlutterFlowTheme.of(context).primaryBackground,
                  icon: Icon(
                    _isFullScreen
                        ? Icons.fullscreen_exit_rounded
                        : Icons.fullscreen_rounded,
                    color: FlutterFlowTheme.of(context).secondaryText,
                    size: 20.0,
                  ),
                  onPressed: () async {
                    HapticFeedback.lightImpact();
                    await _setFullScreen(!_isFullScreen);
                  },
                ),
              ),
            ),
          ],
          centerTitle: true,
          elevation: 0.0,
        ),
        body: SafeArea(
          top: true,
          bottom: false,
          child: Column(
            children: [
              if (!_isFullScreen) _buildTopControls(),
              _buildWebSurface(),
            ],
          ),
        ),
      ),
    );
  }
}
