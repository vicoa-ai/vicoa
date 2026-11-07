// The annotation block must stay byte-identical to the web's, so these mirror
// `apps/web/lib/chat-annotations.test.ts` case for case.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/chat_annotations.dart';

ChatAnnotation _annotation(String quote, {String comment = '', String? id}) => ChatAnnotation(id: id ?? quote, quote: quote, comment: comment);

class _Composer with ChatAnnotationsMixin {
  int repaints = 0;
  int saves = 0;

  @override
  void Function()? get annotationsOnStateChanged => () => repaints++;

  @override
  void onAnnotationsChanged() => saves++;
}

void main() {
  group('normalizeSelectedText', () {
    test('folds CRLF, strips trailing spaces and squeezes blank-line runs', () {
      expect(normalizeSelectedText('  first  \r\n\r\n\r\n\nsecond\t\n'), 'first\n\nsecond');
    });

    test('strips a trailing non-breaking space', () {
      expect(normalizeSelectedText('first \nsecond'), 'first\nsecond');
    });

    test('clamps an over-long selection with a marker', () {
      final out = normalizeSelectedText('a' * (kMaxQuoteChars + 50));
      expect(out.startsWith('a' * kMaxQuoteChars), isTrue);
      expect(out.endsWith('\n… (truncated)'), isTrue);
    });

    test('never cuts through a surrogate pair at the clamp', () {
      // The emoji straddles the limit: its high surrogate is the last unit kept.
      final out = normalizeSelectedText('${'a' * (kMaxQuoteChars - 1)}😀${'b' * 50}');
      expect(out, '${'a' * (kMaxQuoteChars - 1)}\n… (truncated)');
    });
  });

  group('createAnnotation', () {
    test('normalises the quote, trims the comment and assigns an id', () {
      final a = createAnnotation('  quoted \n', comment: '  why?  ');
      expect(a.quote, 'quoted');
      expect(a.comment, 'why?');
      expect(a.id, isNotEmpty);
    });
  });

  group('buildAnnotationBlock', () {
    test('numbers the quotes and indents comments under them, with no header line', () {
      final block = buildAnnotationBlock([_annotation('line one\n\nline two', comment: 'Hi ?'), _annotation('second')]);
      expect(block, ['1. > line one', '   >', '   > line two', '   Comment: Hi ?', '', '2. > second'].join('\n'));
    });

    test('keeps a multi-line comment under its number', () {
      expect(buildAnnotationBlock([_annotation('q', comment: 'a\nb')]), ['1. > q', '   Comment: a', '   b'].join('\n'));
    });

    test('widens the indent past nine items', () {
      final many = [for (var i = 0; i < 10; i++) _annotation('q$i', comment: 'c', id: '$i')];
      final lines = buildAnnotationBlock(many).split('\n');
      expect(lines.sublist(lines.length - 2), ['10. > q9', '    Comment: c']);
    });

    test('is empty when nothing has a quote', () {
      expect(buildAnnotationBlock([_annotation('  ')]), '');
      expect(buildAnnotationBlock(const []), '');
    });
  });

  group('appendAnnotations', () {
    test('puts the block under the typed text after a rule', () {
      expect(appendAnnotations('fix this', [_annotation('q')]), 'fix this\n\n---\n1. > q');
    });

    test('sends the block alone when nothing was typed', () {
      expect(appendAnnotations('', [_annotation('q')]), '1. > q');
    });

    test('whitespace alone counts as nothing typed', () {
      expect(appendAnnotations(' \n ', [_annotation('q')]), '1. > q');
    });

    test('leaves the body untouched without annotations', () {
      expect(appendAnnotations('hello ', const []), 'hello ');
    });
  });

  group('parseAnnotations', () {
    test('keeps well-formed entries and drops the rest', () {
      final parsed = parseAnnotations([
        {'id': 'a', 'quote': 'q', 'comment': 'c'},
        {'id': 'b', 'quote': 'q2'},
        {'id': 'c', 'quote': '   '},
        {'quote': 'no id'},
        null,
        'text',
      ]);
      expect(parsed.map((a) => a.toJson()), [
        {'id': 'a', 'quote': 'q', 'comment': 'c'},
        {'id': 'b', 'quote': 'q2', 'comment': ''},
      ]);
    });

    test('treats anything but a list as empty', () {
      expect(parseAnnotations({'id': 'a'}), isEmpty);
      expect(parseAnnotations(null), isEmpty);
    });
  });

  group('ChatAnnotationHandoff', () {
    test('survives the router as JSON', () {
      final handoff = ChatAnnotationHandoff(annotations: [_annotation('q')], machineId: 'm-1', directory: '/repo', agentType: 'claude');
      final back = ChatAnnotationHandoff.fromJson(handoff.toJson())!;
      expect(back.annotations.single.quote, 'q');
      expect(back.machineId, 'm-1');
      expect(back.directory, '/repo');
      expect(back.agentType, 'claude');
    });

    test('carries no target when the viewer does not own the source session', () {
      final back = ChatAnnotationHandoff.fromJson(ChatAnnotationHandoff(annotations: [_annotation('q')]).toJson())!;
      expect(back.machineId, isNull);
      expect(back.directory, isNull);
      expect(back.agentType, isNull);
    });

    test('is null without text to continue from', () {
      expect(ChatAnnotationHandoff.fromJson(null), isNull);
      expect(ChatAnnotationHandoff.fromJson(<String, dynamic>{'machineId': 'm-1'}), isNull);
    });
  });

  group('ChatAnnotationsMixin', () {
    test('adds, comments on and removes, notifying the host each time', () {
      final composer = _Composer();

      final first = composer.addAnnotation(' first ')!;
      final second = composer.addAnnotation('second')!;
      expect(composer.annotations.map((a) => a.quote), ['first', 'second']);

      composer.updateAnnotationComment(second.id, '  why?  ');
      expect(composer.annotations.last.comment, 'why?');

      composer.removeAnnotation(first.id);
      expect(composer.annotations.single.id, second.id);

      composer.clearAnnotations();
      expect(composer.annotations, isEmpty);

      expect(composer.annotationsRevision, 5);
      expect(composer.saves, 5);
      expect(composer.repaints, 5);
    });

    test('ignores a selection that is only whitespace', () {
      final composer = _Composer();
      expect(composer.addAnnotation(' \n '), isNull);
      expect(composer.annotations, isEmpty);
      expect(composer.annotationsRevision, 0);
    });

    test('a send drops what it carried, not what was picked after it started', () {
      final composer = _Composer();
      composer.addAnnotation('sent');
      final sent = composer.annotations;
      composer.addAnnotation('picked while uploading');

      composer.removeSentAnnotations(sent);

      expect(composer.annotations.map((a) => a.quote), ['picked while uploading']);
    });
  });
}
