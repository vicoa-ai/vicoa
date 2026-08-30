import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';

bool hasAnsiOrLocalCommand(String text) {
  return RegExp(r'<local-command-(stdout|stderr)>').hasMatch(text) ||
      RegExp(r'\x1B\[[0-9;]*m').hasMatch(text);
}

Widget buildAnsiRichText(BuildContext context, String text, TextStyle baseStyle) {
  String cleaned = text;
  cleaned = cleaned.replaceAllMapped(
    RegExp(r'<local-command-stdout>([\s\S]*?)</local-command-stdout>', caseSensitive: false),
    (match) => match.group(1) ?? '',
  );
  cleaned = cleaned.replaceAll(
    RegExp(r'<local-command-stderr>[\s\S]*?</local-command-stderr>', caseSensitive: false),
    '',
  );
  cleaned = cleaned.replaceAll(RegExp(r'\[\?\d+[hl]'), '');

  final spans = <TextSpan>[];
  TextStyle currentStyle = baseStyle;
  String buffer = '';

  Color? colorFromCode(int code) {
    const ansiColors = {
      30: Color(0xFF000000),
      31: Color(0xFFAA0000),
      32: Color(0xFF00AA00),
      33: Color(0xFFAA5500),
      34: Color(0xFF0000AA),
      35: Color(0xFFAA00AA),
      36: Color(0xFF00AAAA),
      37: Color(0xFFAAAAAA),
      90: Color(0xFF555555),
      91: Color(0xFFFF5555),
      92: Color(0xFF55FF55),
      93: Color(0xFFFFFF55),
      94: Color(0xFF5555FF),
      95: Color(0xFFFF55FF),
      96: Color(0xFF55FFFF),
      97: Color(0xFFFFFFFF),
    };
    return ansiColors[code];
  }

  void flushBuffer() {
    if (buffer.isNotEmpty) {
      spans.add(TextSpan(text: buffer, style: currentStyle));
      buffer = '';
    }
  }

  final regex = RegExp(r'\x1B\[[0-9;]*m');
  int lastIndex = 0;
  for (final match in regex.allMatches(cleaned)) {
    buffer += cleaned.substring(lastIndex, match.start);
    flushBuffer();

    final seq = match.group(0) ?? '';
    final codePart = seq.replaceAll(RegExp(r'\x1B\['), '').replaceAll('m', '');
    final parts = codePart
        .split(';')
        .where((p) => p.isNotEmpty)
        .map(int.parse)
        .toList();

    bool bold = currentStyle.fontWeight == FontWeight.w700 ||
        currentStyle.fontWeight == FontWeight.bold;
    Color? color = currentStyle.color;

    if (parts.isEmpty) {
      bold = false;
      color = baseStyle.color;
    }

    for (int i = 0; i < parts.length; i++) {
      final p = parts[i];
      switch (p) {
        case 0:
          bold = false;
          color = baseStyle.color;
          break;
        case 1:
          bold = true;
          break;
        case 22:
          bold = false;
          break;
        case 39:
          color = baseStyle.color;
          break;
        case 38:
          if (i + 4 < parts.length && parts[i + 1] == 2) {
            color = Color.fromARGB(
              0xFF,
              parts[i + 2].clamp(0, 255).toInt(),
              parts[i + 3].clamp(0, 255).toInt(),
              parts[i + 4].clamp(0, 255).toInt(),
            );
            i += 4;
          }
          break;
        default:
          final mapped = colorFromCode(p);
          if (mapped != null) {
            color = mapped;
          }
      }
    }

    currentStyle = baseStyle.copyWith(
      color: color,
      fontWeight: bold ? FontWeight.w700 : baseStyle.fontWeight,
    );

    lastIndex = match.end;
  }

  buffer += cleaned.substring(lastIndex);
  flushBuffer();

  return SelectionArea(
    child: Text.rich(
      TextSpan(children: spans),
      style: baseStyle,
    ),
  );
}
