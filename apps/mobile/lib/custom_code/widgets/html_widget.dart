// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom widgets
import '/custom_code/actions/index.dart'; // Imports custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom widget code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_html/flutter_html.dart';

class HtmlWidget extends StatefulWidget {
  const HtmlWidget({
    super.key,
    this.width,
    this.height,
    this.htmlData,
  });

  final double? width;
  final double? height;
  final String? htmlData;

  @override
  State<HtmlWidget> createState() => _HtmlWidgetState();
}

class _HtmlWidgetState extends State<HtmlWidget> {
  @override
  Widget build(BuildContext context) {
    if (widget.htmlData == null) {
      return Container();
    }

    return SingleChildScrollView(
      child: SelectionArea(
        child: Html(
          data: widget.htmlData!.replaceAll("<br>", ""),
          style: {
            'p': Style(
              fontSize: FontSize(16),
            ),
          },
          onLinkTap: (url, _, __) async {
            debugPrint("Opening $url...");
            if (url != null) {
              await launchURL(url);
            }
          },
          onCssParseError: (css, messages) {
            debugPrint("css that errored: $css");
            debugPrint("error messages:");
            for (var element in messages) {
              debugPrint(element.toString());
            }
            return '';
          },
        ),
      ),
    );
  }
}
