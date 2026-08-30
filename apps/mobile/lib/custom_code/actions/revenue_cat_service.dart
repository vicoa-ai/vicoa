// Automatic FlutterFlow imports

import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:purchases_flutter/purchases_flutter.dart';
import 'package:purchases_ui_flutter/purchases_ui_flutter.dart';
import 'package:vicoa/custom_code/actions/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';

Future<void> showRevenueCatPaywall(BuildContext context) async {
  try {
    // Present the RevenueCat paywall directly
    final paywallResult = await RevenueCatUI.presentPaywall();
    debugPrint('Paywall result: $paywallResult');

    // Await so local subscription state (and the billing cache) is updated
    // before we return to the caller — the message gate in NoCreditSheet /
    // agent chat checks the subscription synchronously on the next send, so
    // Pro must take effect immediately without the user refreshing.
    await syncRevenueCatSubscriptionStatus();
  } catch (e) {
    debugPrint('RevenueCat paywall error: $e');
  }
}

Future<bool> checkRevenueCatSubscriptionStatus() async {
  try {
    CustomerInfo customerInfo = await Purchases.getCustomerInfo();
    return customerInfo.entitlements.all['pro']?.isActive ?? false;
  } catch (e) {
    debugPrint('Error checking subscription status: $e');
    return false;
  }
}

Future<void> syncRevenueCatSubscriptionStatus() async {
  try {
    CustomerInfo customerInfo = await Purchases.getCustomerInfo();
    
    // Set RevenueCat customer ID in user struct
    FFAppState().user = FFAppState().user..revenueCatId = customerInfo.originalAppUserId;
    
    // Update subscription status based on RevenueCat entitlements
    bool hasActiveSubscription = customerInfo.entitlements.all['pro']?.isActive ?? false;
    String newStatus = hasActiveSubscription ? 'active' : 'inactive';

    String originalStatus = FFAppState().user.subscriptionStatus;

    if (originalStatus != newStatus) {
      FFAppState().user = FFAppState().user..subscriptionStatus = newStatus;
      debugPrint('Updated subscription status to: $newStatus');
    }

    if (originalStatus != 'active' && newStatus == 'active') {
      await requestReview();
    }
    
  } catch (e) {
    debugPrint('Error syncing RevenueCat subscription status: $e');
  }
}

Future<String> getRevenueCatUserId() async {
  try {
    CustomerInfo customerInfo = await Purchases.getCustomerInfo();
    return customerInfo.originalAppUserId;
  } catch (e) {
    debugPrint('Error getting RevenueCat user ID: $e');
    return '';
  }
}

Future<void> restoreRevenueCatPurchases() async {
  try {
    CustomerInfo customerInfo = await Purchases.restorePurchases();
    debugPrint('Purchases restored: ${customerInfo.entitlements.all}');
    
    // Sync subscription status after restore
    await syncRevenueCatSubscriptionStatus();
  } catch (e) {
    debugPrint('Error restoring purchases: $e');
  }
}

Future<void> showRevenueCatPaywallFullScreen(
  BuildContext context, {
  String? offeringIdentifier,
  String? nextPageRoute,
}) async {
  try {
    // Navigate to full-screen paywall page with slide up animation
    await Navigator.of(context).push(
      PageRouteBuilder(
        pageBuilder: (context, animation, secondaryAnimation) => FullScreenPaywallWidget(
          offeringIdentifier: offeringIdentifier,
          nextPageRoute: nextPageRoute,
        ),
        fullscreenDialog: true,
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          // Slide up from bottom: start below screen, end at normal position
          const begin = Offset(0.0, 1.0); // 1.0 means one full screen height down (off-screen bottom)
          const end = Offset(0.0, 0.0);   // 0.0 means normal position (on-screen)
          
          var slideUpTween = Tween(
            begin: begin,
            end: end,
          ).chain(CurveTween(curve: Curves.easeOutCubic));

          return SlideTransition(
            position: animation.drive(slideUpTween),
            child: child,
          );
        },
        transitionDuration: const Duration(milliseconds: 400),
        reverseTransitionDuration: const Duration(milliseconds: 400),
      ),
    );

    // Check subscription status after paywall dismissal
    await syncRevenueCatSubscriptionStatus();
  } catch (e) {
    debugPrint('RevenueCat paywall error: $e');
  }
}

class FullScreenPaywallWidget extends StatefulWidget {
  final String? offeringIdentifier;
  final String? nextPageRoute;
  
  const FullScreenPaywallWidget({
    super.key, 
    this.offeringIdentifier,
    this.nextPageRoute,
  });

  @override
  State<FullScreenPaywallWidget> createState() => _FullScreenPaywallWidgetState();
}

class _FullScreenPaywallWidgetState extends State<FullScreenPaywallWidget> {
  Offering? _offering;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadOffering();
  }

  Future<void> _loadOffering() async {
    try {
      final offerings = await Purchases.getOfferings();
      
      if (widget.offeringIdentifier != null) {
        // Find specific offering by identifier
        _offering = offerings.all[widget.offeringIdentifier!];
        if (_offering == null) {
          debugPrint('Offering ${widget.offeringIdentifier} not found, using current offering');
          _offering = offerings.current;
        }
      } else {
        // Use current offering as fallback
        _offering = offerings.current;
      }
      
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('Error loading offering: $e');
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  void _handlePaywallClose() {
      if (Navigator.canPop(context)) {
        Navigator.of(context).pop();
      }
      // Then navigate to next page if specified
      if (widget.nextPageRoute != null && widget.nextPageRoute!.isNotEmpty) {
        // Wait for the pop animation to complete before navigating
        Future.delayed(const Duration(milliseconds: 100), () {
          if (mounted) {
            try {
              context.pushNamed(widget.nextPageRoute!);
            } catch (e) {
              debugPrint('Navigation error: $e');
              try {
                context.go('/${widget.nextPageRoute!}');
              } catch (e2) {
                debugPrint('Fallback navigation also failed: $e2');
              }
            }
          }
        });
      }
    // });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF161C24),
      body: 
      // SafeArea(
      //   child: 
        _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(AppLocalizations.of(context).billingXPaywallLoadError(_error ?? '')),
                        ElevatedButton(
                          onPressed: () => Navigator.of(context).pop(),
                          child: Text(AppLocalizations.of(context).commonClose),
                        ),
                      ],
                    ),
                  )
                : _offering != null
                    ? PaywallView(
                        offering: _offering,
                        onRestoreCompleted: (customerInfo) async {
                          debugPrint('Restore completed: ${customerInfo.entitlements.all}');
                          await syncRevenueCatSubscriptionStatus();
                          _handlePaywallClose();
                        },
                        onPurchaseCompleted: (customerInfo, storeTransaction) async {
                          debugPrint('Purchase completed: ${customerInfo.entitlements.all}');
                          await syncRevenueCatSubscriptionStatus();
                          _handlePaywallClose();
                        },
                        onPurchaseError: (error) {
                          debugPrint('Purchase error: $error');
                        },
                        onDismiss: () {
                          _handlePaywallClose();
                        },
                      )
                    : Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(AppLocalizations.of(context).billingXNoOffering),
                            ElevatedButton(
                              onPressed: () => Navigator.of(context).pop(),
                              child: Text(AppLocalizations.of(context).commonClose),
                            ),
                          ],
                        ),
                      ),
      // ),
    );
  }
}
