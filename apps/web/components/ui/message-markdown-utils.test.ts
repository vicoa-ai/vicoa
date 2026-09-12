import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { describe, expect, test } from 'vitest';
import { delimitBareUrls, extractMessageOptions, formatDiffLines } from '@/components/ui/message-markdown-utils';

test('merges verbose diff while preserving context lines', () => {
  const input = [
    "  import 'dart:convert';",
    "- import 'dart:math' as math;",
    "- ",
    "- import 'package:flutter/material.dart';",
    "- import 'package:google_fonts/google_fonts.dart';",
    "- import 'package:intl/intl.dart';",
    "- import 'package:timeago/timeago.dart' as timeago;",
    "- import 'lat_lng.dart';",
    "- import 'place.dart';",
    "- import 'uploaded_file.dart';",
    "- import '/backend/schema/structs/index.dart';",
    "- import '/backend/supabase/supabase.dart';",
    "- import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'dart:io';",
    "+ import 'dart:math' as math;",
    "+ ",
    "+ import 'package:flutter/material.dart';",
    "+ import 'package:google_fonts/google_fonts.dart';",
    "+ import 'package:intl/intl.dart';",
    "+ import 'package:timeago/timeago.dart' as timeago;",
    "+ import 'lat_lng.dart';",
    "+ import 'place.dart';",
    "+ import 'uploaded_file.dart';",
    "+ import '/backend/schema/structs/index.dart';",
    "+ import '/backend/supabase/supabase.dart';",
    "+ import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'flutter_flow_util.dart';",
  ].join('\n');

  const output = formatDiffLines(input, true, { compactContext: false }).map((line) => line.content);

  expect(output).toEqual([
    "  import 'dart:convert';",
    "+ import 'dart:io';",
    "  import 'dart:math' as math;",
    '  ',
    "  import 'package:flutter/material.dart';",
    "  import 'package:google_fonts/google_fonts.dart';",
    "  import 'package:intl/intl.dart';",
    "  import 'package:timeago/timeago.dart' as timeago;",
    "  import 'lat_lng.dart';",
    "  import 'place.dart';",
    "  import 'uploaded_file.dart';",
    "  import '/backend/schema/structs/index.dart';",
    "  import '/backend/supabase/supabase.dart';",
    "  import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'flutter_flow_util.dart';",
  ]);
});

test('extracts bracket-delimited options from message content', () => {
  const input = [
    'Pick one:',
    '[OPTIONS]',
    '1. Keep current branch',
    '2. Create a new worktree',
    '[/OPTIONS]',
  ].join('\n');

  const output = extractMessageOptions(input);

  expect(output.content).toBe('Pick one:');
  expect(output.options).toEqual(['Keep current branch', 'Create a new worktree']);
});

test('extracts slash-delimited options from message content', () => {
  const input = [
    'Need a choice',
    'options/',
    '1. Approve',
    '2. Reject',
    '\\options',
  ].join('\n');

  const output = extractMessageOptions(input);

  expect(output.content).toBe('Need a choice');
  expect(output.options).toEqual(['Approve', 'Reject']);
});

describe('delimitBareUrls', () => {
  test('cuts a bare URL at CJK punctuation and at a bold closer', () => {
    expect(delimitBareUrls('PR 已开：**https://github.com/vicoa-ai/vicoa/pull/54**（rebase 到最新 main）。')).toBe(
      'PR 已开：**<https://github.com/vicoa-ai/vicoa/pull/54>**（rebase 到最新 main）。',
    );
    // What the agent actually emitted: ASCII punctuation glued on, which GFM
    // would otherwise keep as part of the URL.
    expect(delimitBareUrls('PR 已开:**https://github.com/vicoa-ai/vicoa/pull/54**(rebase 到最新 main,5 个文件)。')).toBe(
      'PR 已开:**<https://github.com/vicoa-ai/vicoa/pull/54>**(rebase 到最新 main,5 个文件)。',
    );
    expect(delimitBareUrls('见 https://x.com/a，https://x.com/b。')).toBe('见 <https://x.com/a>，<https://x.com/b>。');
    expect(delimitBareUrls('（https://x.com/a）')).toBe('（<https://x.com/a>）');
  });

  test('ends a URL opened by an emphasis run at the matching run', () => {
    expect(delimitBareUrls('*https://x.com/a*, ***https://x.com/b***; ~~https://x.com/c~~(old)')).toBe(
      '*<https://x.com/a>*, ***<https://x.com/b>***; ~~<https://x.com/c>~~(old)',
    );
    // A shorter run inside the URL is part of it.
    expect(delimitBareUrls('**https://x.com/*/a**(b)')).toBe('**<https://x.com/*/a>**(b)');
    // Not opened by emphasis: `*` stays in the URL, as in GFM.
    expect(delimitBareUrls('see https://x.com/a**b')).toBe('see <https://x.com/a**b>');
    // `_` and a lone `~` are URL characters, not delimiters.
    expect(delimitBareUrls('_https://x.com/a_b_ ~https://x.com/~u~')).toBe('_<https://x.com/a_b>_ ~<https://x.com/~u>~');
  });

  test('never keeps an unclosed paren', () => {
    expect(delimitBareUrls('https://x.com/pull/54(rebase to main)。')).toBe('<https://x.com/pull/54>(rebase to main)。');
    expect(delimitBareUrls('https://x.com/a_(b)(c ok')).toBe('<https://x.com/a_(b)>(c ok');
    expect(delimitBareUrls('https://x.com/((a)')).toBe('<https://x.com/>((a)');
  });

  test('keeps non-ASCII letters in a URL', () => {
    expect(delimitBareUrls('https://ja.wikipedia.org/wiki/佐々木 和 https://zh.wikipedia.org/wiki/中文。')).toBe(
      '<https://ja.wikipedia.org/wiki/佐々木> 和 <https://zh.wikipedia.org/wiki/中文>。',
    );
  });

  test('trims trailing marks the way GFM does', () => {
    expect(delimitBareUrls('see https://x.com/a.')).toBe('see <https://x.com/a>.');
    expect(delimitBareUrls('see https://x.com/a).')).toBe('see <https://x.com/a>).');
    expect(delimitBareUrls('see https://x.com/a_(b) ok')).toBe('see <https://x.com/a_(b)> ok');
    expect(delimitBareUrls('see https://x.com/(a)) ok')).toBe('see <https://x.com/(a)>) ok');
    expect(delimitBareUrls('see https://x.com/?a=1&amp; ok')).toBe('see <https://x.com/?a=1>&amp; ok');
    expect(delimitBareUrls('see https://x.com/?a=1&b=2; ok')).toBe('see <https://x.com/?a=1&b=2>; ok');
    expect(delimitBareUrls('_https://x.com/a_ ~https://x.com/b~ "https://x.com/c"')).toBe(
      '_<https://x.com/a>_ ~<https://x.com/b>~ "<https://x.com/c>"',
    );
  });

  test('stops at markdown delimiters and table pipes', () => {
    expect(delimitBareUrls('|https://x.com/a|b|')).toBe('|<https://x.com/a>|b|');
    expect(delimitBareUrls('https://x.com/a<b>')).toBe('<https://x.com/a><b>');
    expect(delimitBareUrls('https://x.com/a`b')).toBe('<https://x.com/a>`b');
  });

  test('leaves code spans alone', () => {
    expect(delimitBareUrls('a `https://x.com**（y` b https://x.com/c（d）')).toBe(
      'a `https://x.com**（y` b <https://x.com/c>（d）',
    );
    expect(delimitBareUrls('`` a ` https://x.com `` https://y.com')).toBe('`` a ` https://x.com `` <https://y.com>');
    // An unclosed backtick run is just text.
    expect(delimitBareUrls('` https://x.com/a')).toBe('` <https://x.com/a>');
  });

  test('leaves URLs that already have a delimiter alone', () => {
    expect(delimitBareUrls('<https://x.com/a> and [t](https://x.com/b) and [u](https://x.com/c "t")')).toBe(
      '<https://x.com/a> and [t](https://x.com/b) and [u](https://x.com/c "t")',
    );
    expect(delimitBareUrls('<a href="https://x.com/a">x</a>')).toBe('<a href="https://x.com/a">x</a>');
  });

  test('leaves what GFM would not link alone', () => {
    expect(delimitBareUrls('[see https://x.com/a](https://x.com/b) https://x.com/c')).toBe(
      '[see https://x.com/a](https://x.com/b) <https://x.com/c>',
    );
    expect(delimitBareUrls('\\[not a label https://x.com/a')).toBe('\\[not a label <https://x.com/a>');
    expect(delimitBareUrls('xhttps://x.com/a')).toBe('xhttps://x.com/a');
    expect(delimitBareUrls('https:// and https://. and https://[::1]/')).toBe('https:// and https://. and https://[::1]/');
    expect(delimitBareUrls('no links here')).toBe('no links here');
  });

  test('renders the reported message as a bold link followed by prose', () => {
    const render = (md: string) =>
      renderToStaticMarkup(React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, delimitBareUrls(md)));
    const link = '<strong><a href="https://github.com/vicoa-ai/vicoa/pull/54">https://github.com/vicoa-ai/vicoa/pull/54</a></strong>';
    expect(render('PR 已开：**https://github.com/vicoa-ai/vicoa/pull/54**（rebase 到最新 main，5 个文件，lint/tsc/vitest 都过）。')).toBe(
      `<p>PR 已开：${link}（rebase 到最新 main，5 个文件，lint/tsc/vitest 都过）。</p>`,
    );
    expect(render('PR 已开:**https://github.com/vicoa-ai/vicoa/pull/54**(rebase 到最新 main,5 个文件,lint/tsc/vitest 都过)。')).toBe(
      `<p>PR 已开:${link}(rebase 到最新 main,5 个文件,lint/tsc/vitest 都过)。</p>`,
    );
  });
});
