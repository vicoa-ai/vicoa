import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class ErrorBannerWidget extends StatelessWidget {
  const ErrorBannerWidget({
    super.key,
    required this.errorType,
    this.errorMessage,
    this.onRetry,
  }); 

  final functions.ErrorType errorType;
  final String? errorMessage;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
      padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.4),
          width: 1.0,
        ),
      ),
      child: Row(
        children: [
          Icon(
            functions.getErrorIcon(errorType),
            color: FlutterFlowTheme.of(context).secondaryText,
            size: 20.0,
          ),
          SizedBox(width: 12.0),
          Expanded(
            child: Text(
              errorMessage ?? 'Using cached data',
              style: FlutterFlowTheme.of(context).bodyMedium.override(
                color: FlutterFlowTheme.of(context).primaryText,
                fontSize: 14.0,
              ),
            ),
          ),
          // if (onRetry != null &&
          //     (errorType == functions.ErrorType.network ||
          //      errorType == functions.ErrorType.server))
          //   // TextButton(
            //   onPressed: () {
            //     HapticFeedback.lightImpact();
            //     onRetry!();
            //   },
            //   child: Text(
            //     'Retry',
            //     style: TextStyle(
            //       color: FlutterFlowTheme.of(context).secondaryText,
            //       fontWeight: FontWeight.w600,
            //     ),
            //   ),
            // ),
        ],
      ),
    );
  }
}
