'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, ListChecks, Maximize2, X } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MessageResponse } from '@/lib/backend-api';

export type AskUserQuestionOption = {
  label: string;
  description: string;
  /** Draft, mockup or snippet the agent attached for comparing options. */
  preview?: string;
};

export type AskUserQuestionItem = {
  question: string;
  header: string;
  options: AskUserQuestionOption[];
  multi_select: boolean;
};

export type AskUserQuestionPayload = {
  tool_use_id?: string;
  prompt?: string;
  questions: AskUserQuestionItem[];
};

export type AskUserQuestionAnswer =
  | {
      mode: 'option';
      option_index?: number;
      option_indexes?: number[];
      question_multi_select?: boolean;
      option_count?: number;
    }
  | { mode: 'text'; text: string; option_count?: number };

export type AskUserQuestionSubmitPayload = {
  message_id: string;
  answers: AskUserQuestionAnswer[];
  display_answers?: Array<{ header: string; label: string; question?: string }>;
};

// Previews are drafts and ASCII mockups whose columns must line up, so they
// stay monospace past the app-wide Geist Sans sweep of `font-mono` (see
// app/globals.css); same family as chat code in components/ui/message-markdown.tsx.
const PREVIEW_FONT_FAMILY =
  'var(--font-geist-mono), ui-monospace, SFMono-Regular, Menlo, monospace';

// Box-drawing characters or markdown table rows: a grid whose columns must
// stay aligned, so it scrolls sideways instead of wrapping. Prose and code wrap.
const GRID_PREVIEW = /[\u2500-\u257F]|^\s*\|.*\|\s*$/m;

export function isGridPreview(preview: string): boolean {
  return GRID_PREVIEW.test(preview);
}

function encodeAskUserQuestionPayload(payload: AskUserQuestionSubmitPayload): string {
  const json = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(json);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function buildAskUserQuestionSummaryContent(
  displayAnswers?: Array<{ header: string; label: string; question?: string }>
): string {
  if (!displayAnswers?.length) {
    return '';
  }

  const lines = displayAnswers
    .map((answer) => {
      const question = (answer.question || answer.header || '').trim();
      const label = (answer.label || '').trim() || '(empty)';
      if (!question) return '';
      return `Q: ${question}\nA: ${label}`;
    })
    .filter(Boolean);

  // Blank line between Q/A pairs (none after the last) for readability.
  return lines.join('\n\n');
}

function encodeAskUserQuestionSummaryPayload(payload: {
  message_id: string;
  answers: AskUserQuestionSubmitPayload['answers'];
  display_answers?: AskUserQuestionSubmitPayload['display_answers'];
}): string {
  const json = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(json);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export function buildAskUserQuestionSummaryMessage(payload: AskUserQuestionSubmitPayload): string {
  const summaryContent = buildAskUserQuestionSummaryContent(payload.display_answers);
  if (!summaryContent) {
    return '';
  }

  const encoded = encodeAskUserQuestionSummaryPayload({
    message_id: payload.message_id,
    answers: payload.answers,
    display_answers: payload.display_answers,
  });

  const control = JSON.stringify({
    type: 'control',
    action: 'persist_only',
    kind: 'ask_user_question_summary',
    value: `v1:${encoded}`,
  });

  return `${summaryContent}\n${control}`;
}

export function buildAskUserQuestionCancelPersistMessage(): string {
  const control = JSON.stringify({
    type: 'control',
    action: 'persist_only',
  });

  return `Declined to answer\n${control}`;
}

export function buildAskUserQuestionControlMessage(
  action: 'submit' | 'cancel',
  payload?: AskUserQuestionSubmitPayload
): string {
  const value = action === 'submit' && payload
    ? `submit:${encodeAskUserQuestionPayload(payload)}`
    : 'cancel';
  const humanReadable = action === 'submit'
    ? 'Submit AskUserQuestion answers.'
    : 'Cancel AskUserQuestion prompt.';
  return `${humanReadable} ${JSON.stringify({ type: 'control', setting: 'ask_user_question', value })}`;
}

export function parseAskUserQuestionPayload(message: MessageResponse): AskUserQuestionPayload | null {
  const metadata = message.message_metadata as Record<string, unknown> | null | undefined;
  const askPayloadRaw = metadata?.ask_user_question as Record<string, unknown> | undefined;
  if (!askPayloadRaw || !Array.isArray(askPayloadRaw.questions)) {
    if (message.requires_user_input && typeof window !== 'undefined') {
      console.debug('[AskUserQuestion] Missing structured metadata for message', {
        messageId: message.id,
        hasMetadata: Boolean(metadata),
        metadataKeys: metadata ? Object.keys(metadata) : [],
      });
    }
    return null;
  }

  const parsedQuestions = askPayloadRaw.questions
    .map((raw, index) => {
      if (!raw || typeof raw !== 'object') {
        return null;
      }
      const questionRecord = raw as Record<string, unknown>;
      const question = typeof questionRecord.question === 'string' ? questionRecord.question : '';
      if (!question.trim()) {
        return null;
      }
      const headerRaw = typeof questionRecord.header === 'string' ? questionRecord.header : `Question ${index + 1}`;
      const options = Array.isArray(questionRecord.options)
        ? questionRecord.options
            .map((option) => {
              if (!option || typeof option !== 'object') return null;
              const optionRecord = option as Record<string, unknown>;
              const label = typeof optionRecord.label === 'string' ? optionRecord.label : '';
              const description = typeof optionRecord.description === 'string' ? optionRecord.description : '';
              const preview = optionRecord.preview;
              if (!label.trim()) return null;
              return typeof preview === 'string' && preview.trim()
                ? { label, description, preview }
                : { label, description };
            })
            .filter((option): option is AskUserQuestionOption => option !== null)
        : [];

      return {
        question,
        header: headerRaw.trim() || `Question ${index + 1}`,
        options,
        multi_select: Boolean(questionRecord.multi_select),
      };
    });

  const questions = parsedQuestions.filter((item): item is AskUserQuestionItem => item !== null);

  if (!questions.length) {
    if (typeof window !== 'undefined') {
      console.debug('[AskUserQuestion] Structured metadata parsed but no valid questions', {
        messageId: message.id,
      });
    }
    return null;
  }

  if (typeof window !== 'undefined') {
    console.debug('[AskUserQuestion] Parsed structured payload', {
      messageId: message.id,
      questionCount: questions.length,
      headers: questions.map((question) => question.header),
    });
  }

  return {
    tool_use_id: typeof askPayloadRaw.tool_use_id === 'string' ? askPayloadRaw.tool_use_id : undefined,
    prompt: typeof askPayloadRaw.prompt === 'string' ? askPayloadRaw.prompt : undefined,
    questions,
  };
}

function initialAnswers(askUserQuestion: AskUserQuestionPayload | null): AskUserQuestionAnswer[] {
  if (!askUserQuestion) return [];
  return askUserQuestion.questions.map((question) => {
    if (question.options.length === 0) {
      return { mode: 'text', text: '' } as AskUserQuestionAnswer;
    }
    if (question.multi_select) {
      return {
        mode: 'option',
        option_indexes: [],
        question_multi_select: true,
        option_count: question.options.length,
      } as AskUserQuestionAnswer;
    }
    return {
      mode: 'option',
      option_index: 0,
      question_multi_select: false,
      option_count: question.options.length,
    } as AskUserQuestionAnswer;
  });
}

type ScrollEdges = { left: boolean; right: boolean };

// Fade whichever edge still has content past it, so a sideways-scrolling grid
// reads as "more this way" even where the scrollbar stays hidden (macOS).
function edgeFadeMask({ left, right }: ScrollEdges): string | undefined {
  if (!left && !right) return undefined;
  const start = left ? 'transparent, black 2.5rem' : 'black';
  const end = right ? 'black calc(100% - 2.5rem), transparent' : 'black';
  return `linear-gradient(to right, ${start}, ${end})`;
}

function OptionPreviewPane({ preview, label }: { preview: string; label: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState<ScrollEdges>({ left: false, right: false });
  const [expanded, setExpanded] = useState(false);
  const grid = isGridPreview(preview);
  const layoutClass = grid ? 'custom-scrollbar overflow-x-auto whitespace-pre' : 'whitespace-pre-wrap break-words';

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !grid) return;
    const update = () =>
      setEdges({
        left: el.scrollLeft > 1,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1,
      });
    update();
    el.addEventListener('scroll', update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener('scroll', update);
      observer.disconnect();
    };
  }, [grid, preview]);

  const mask = edgeFadeMask(edges);
  return (
    // <div>s, not <pre>: globals.css forces a muted background on every <pre>.
    <div className="relative min-w-0 rounded-lg bg-foreground/10 text-xs text-foreground">
      <div
        ref={scrollRef}
        className={`select-text px-3 py-2.5 ${layoutClass}`}
        style={{ fontFamily: PREVIEW_FONT_FAMILY, maskImage: mask, WebkitMaskImage: mask }}
      >
        {preview}
      </div>
      {(edges.left || edges.right) && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          aria-label="Expand preview"
          title="Expand preview"
          className="absolute right-1.5 top-1.5 cursor-pointer rounded-md bg-background/80 p-1 text-muted-foreground transition-colors hover:text-foreground"
        >
          <Maximize2 className="size-3.5" aria-hidden="true" />
        </button>
      )}
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="w-max min-w-[min(95vw,28rem)] max-w-[95vw] gap-3 p-4">
          <DialogHeader className="flex-row items-center justify-end space-y-0">
            <DialogTitle className="sr-only">{label}</DialogTitle>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              aria-label="Close"
              className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </DialogHeader>
          <div
            className={`custom-scrollbar max-h-[80vh] select-text overflow-auto rounded-lg bg-foreground/5 px-4 py-3 text-xs text-foreground ${
              grid ? 'whitespace-pre' : 'whitespace-pre-wrap break-words'
            }`}
            style={{ fontFamily: PREVIEW_FONT_FAMILY }}
          >
            {preview}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

type AskUserQuestionPanelProps = {
  message: MessageResponse;
  onSubmit?: (payload: AskUserQuestionSubmitPayload) => void;
  onCancel?: (messageId: string) => void;
};

export function AskUserQuestionPanel({ message, onSubmit, onCancel }: AskUserQuestionPanelProps) {
  const askUserQuestion = parseAskUserQuestionPayload(message);
  const [activeTab, setActiveTab] = useState(0);
  // Seeded on the first render, not only in the effect below: a free-text
  // question's textarea is part of the row's height, and the transcript's
  // virtual list remounts this panel whenever the row scrolls back into range.
  // Filling answers after paint made every remount grow the row a frame late,
  // which the list reacts to (see collapsible-user-message.tsx).
  const [answers, setAnswers] = useState<AskUserQuestionAnswer[]>(() => initialAnswers(askUserQuestion));
  // Per question: the option whose preview fills the preview pane. Follows
  // clicks, and stays put while "Type something" is chosen.
  const [previewFocus, setPreviewFocus] = useState<Record<number, number>>({});

  useEffect(() => {
    setAnswers(initialAnswers(askUserQuestion));
    setActiveTab(0);
    setPreviewFocus({});
  }, [askUserQuestion?.tool_use_id, askUserQuestion?.questions.length]);

  if (!askUserQuestion) {
    return null;
  }

  const activeQuestion = askUserQuestion.questions[activeTab];
  const hasPreviews = Boolean(activeQuestion?.options.some((option) => option.preview));
  const focusedIndex = previewFocus[activeTab] ?? 0;
  const focusedOption = activeQuestion?.options[focusedIndex];
  const focusedPreview = focusedOption?.preview;

  const currentAnswerText = (answer: AskUserQuestionAnswer | undefined): string => {
    if (!answer || answer.mode !== 'text') {
      return '';
    }
    return answer.text;
  };

  const handleSubmit = () => {
    onSubmit?.({
      message_id: message.id,
      answers: askUserQuestion.questions.map((question, index) => {
        const answer = answers[index];
        if (!answer) {
          return {
            mode: 'option',
            option_index: 0,
            question_multi_select: question.multi_select,
            option_count: question.options.length,
          } as AskUserQuestionAnswer;
        }
        if (answer.mode === 'text') {
          return {
            mode: 'text',
            text: answer.text,
            option_count: question.options.length,
          } as AskUserQuestionAnswer;
        }
        return {
          mode: 'option',
          option_index: answer.option_index,
          option_indexes: answer.option_indexes,
          question_multi_select: question.multi_select,
          option_count: question.options.length,
        } as AskUserQuestionAnswer;
      }),
      display_answers: askUserQuestion.questions.map((question, index) => {
        const answer = answers[index];
        if (!answer) {
          const fallbackLabel = question.options[0]?.label ?? '';
          return { header: question.header, label: fallbackLabel, question: question.question };
        }
        if (answer.mode === 'text') {
          return { header: question.header, label: answer.text.trim(), question: question.question };
        }
        if (question.multi_select) {
          const labels = (answer.option_indexes ?? [])
            .map((idx) => question.options[idx]?.label ?? '')
            .filter((label) => label.trim().length > 0);
          return { header: question.header, label: labels.join(', '), question: question.question };
        }
        const optionLabel = question.options[answer.option_index ?? 0]?.label ?? '';
        return { header: question.header, label: optionLabel, question: question.question };
      }),
    });
  };

  return (
    <div className="@container mt-3 rounded-xl border border-border bg-muted/30 p-3">
      {askUserQuestion.questions.length > 1 && (
        <div className="mb-3 flex items-center gap-1.5">
          {askUserQuestion.questions.map((question, questionIndex) => (
            <button
              key={`${message.id}-ask-tab-${questionIndex}`}
              onClick={() => setActiveTab(questionIndex)}
              className={`rounded-md border px-2 py-1 text-xs font-mono transition-colors ${
                activeTab === questionIndex
                  ? 'border-transparent bg-foreground/10 text-foreground'
                  : 'border-border text-muted-foreground hover:bg-muted/40 hover:text-foreground/90'
              }`}
            >
              <span className="inline-flex items-center gap-1">
                {question.multi_select && <ListChecks className="size-3.5" aria-hidden="true" />}
                <span>{question.header}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      <div>
        <div className="mb-3 select-text whitespace-pre-wrap text-xs font-mono text-foreground">
          {activeQuestion?.question}
        </div>
        {/* With previews: options and "Type something" on the left, one preview
            pane spanning both rows on the right. A narrow panel stacks them as
            options, preview, "Type something". */}
        <div
          className={`grid gap-y-2 ${
            hasPreviews ? '@xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] @xl:grid-rows-[auto_1fr] @xl:gap-x-3' : ''
          }`}
        >
          <div className="min-w-0 space-y-2 @xl:col-start-1 @xl:row-start-1">
            {activeQuestion?.options.map((option, optionIndex) => {
              const currentAnswer = answers[activeTab];
              const isMultiSelect = Boolean(activeQuestion.multi_select);
              const selectedIndexes =
                currentAnswer?.mode === 'option' ? (currentAnswer.option_indexes ?? []) : [];
              const isSelected = currentAnswer?.mode === 'option' && (
                isMultiSelect
                  ? selectedIndexes.includes(optionIndex)
                  : currentAnswer.option_index === optionIndex
              );
              return (
                <button
                  key={`${message.id}-ask-option-${activeTab}-${optionIndex}`}
                  onClick={() => {
                    setPreviewFocus((prev) => ({ ...prev, [activeTab]: optionIndex }));
                    setAnswers((prev) => {
                      const next = [...prev];
                      if (isMultiSelect) {
                        const existing =
                          next[activeTab]?.mode === 'option'
                            ? (next[activeTab].option_indexes ?? [])
                            : [];
                        const nextIndexes = existing.includes(optionIndex)
                          ? existing.filter((idx) => idx !== optionIndex)
                          : [...existing, optionIndex].sort((a, b) => a - b);
                        next[activeTab] = {
                          mode: 'option',
                          option_indexes: nextIndexes,
                          question_multi_select: true,
                          option_count: activeQuestion.options.length,
                        };
                      } else {
                        next[activeTab] = {
                          mode: 'option',
                          option_index: optionIndex,
                          question_multi_select: false,
                          option_count: activeQuestion.options.length,
                        };
                      }
                      return next;
                    });
                  }}
                  className={`block w-full rounded-lg px-3 py-2 text-left transition-colors ${
                    isSelected ? 'bg-foreground/10' : 'hover:bg-muted/40'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="select-text text-xs font-medium text-foreground font-mono">{option.label}</div>
                      <div className="mt-1 select-text text-xs text-muted-foreground font-mono whitespace-pre-wrap">{option.description}</div>
                    </div>
                    {isSelected && <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground" />}
                  </div>
                </button>
              );
            })}
          </div>
          {/* An option without a preview leaves the column empty, so the list doesn't shift. */}
          {focusedPreview && (
            <div className="min-w-0 @xl:col-start-2 @xl:row-span-2 @xl:row-start-1">
              {/* Keyed so switching options starts the new preview scrolled to its left edge. */}
              <OptionPreviewPane
                key={`${activeTab}-${focusedIndex}`}
                preview={focusedPreview}
                label={focusedOption?.label ?? ''}
              />
            </div>
          )}
          <div className="min-w-0 space-y-2 @xl:col-start-1 @xl:row-start-2">
            <button
              onClick={() => {
                setAnswers((prev) => {
                  const next = [...prev];
                  next[activeTab] = {
                    mode: 'text',
                    text: currentAnswerText(next[activeTab]),
                    option_count: activeQuestion?.options.length ?? 0,
                  };
                  return next;
                });
              }}
              className={`block w-full rounded-lg px-3 py-2 text-left transition-colors ${
                answers[activeTab]?.mode === 'text' ? 'bg-foreground/10' : 'hover:bg-muted/40'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-foreground font-mono">Type something</div>
                {answers[activeTab]?.mode === 'text' && (
                  <Check className="h-3.5 w-3.5 shrink-0 text-foreground" />
                )}
              </div>
            </button>
            {answers[activeTab]?.mode === 'text' && (
              <textarea
                value={currentAnswerText(answers[activeTab])}
                onChange={(event) => {
                  const value = event.target.value;
                  setAnswers((prev) => {
                    const next = [...prev];
                    next[activeTab] = { mode: 'text', text: value };
                    return next;
                  });
                }}
                rows={3}
                className="custom-scrollbar w-full resize-y rounded-md bg-foreground/5 px-2.5 py-1.5 text-xs font-mono text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                placeholder="Type your answer"
              />
            )}
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-1.5">
        <button
          onClick={handleSubmit}
          className="cursor-pointer rounded-md bg-foreground/15 px-3 py-1.5 text-xs font-mono text-foreground transition-colors hover:bg-foreground/25"
        >
          Submit
        </button>
        <button
          onClick={() => onCancel?.(message.id)}
          className="cursor-pointer rounded-md px-3 py-1.5 text-xs font-mono text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
