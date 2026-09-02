'use client';

import { useEffect, useState } from 'react';
import { Check, ListChecks } from 'lucide-react';
import { MessageResponse } from '@/lib/backend-api';

export type AskUserQuestionOption = {
  label: string;
  description: string;
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
              if (!label.trim()) return null;
              return { label, description };
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

type AskUserQuestionPanelProps = {
  message: MessageResponse;
  onSubmit?: (payload: AskUserQuestionSubmitPayload) => void;
  onCancel?: (messageId: string) => void;
};

export function AskUserQuestionPanel({ message, onSubmit, onCancel }: AskUserQuestionPanelProps) {
  const askUserQuestion = parseAskUserQuestionPayload(message);
  const [activeTab, setActiveTab] = useState(0);
  const [answers, setAnswers] = useState<AskUserQuestionAnswer[]>([]);

  useEffect(() => {
    if (!askUserQuestion) {
      setAnswers([]);
      setActiveTab(0);
      return;
    }
    setAnswers(
      askUserQuestion.questions.map((question) => {
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
      })
    );
    setActiveTab(0);
  }, [askUserQuestion?.tool_use_id, askUserQuestion?.questions.length]);

  if (!askUserQuestion) {
    return null;
  }

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
    <div className="mt-3 rounded-xl border border-border bg-muted/30 p-3">
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
          {askUserQuestion.questions[activeTab]?.question}
        </div>
        <div className="space-y-2">
          {askUserQuestion.questions[activeTab]?.options.map((option, optionIndex) => {
            const currentAnswer = answers[activeTab];
            const isMultiSelect = Boolean(askUserQuestion.questions[activeTab]?.multi_select);
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
                        option_count: askUserQuestion.questions[activeTab]?.options.length ?? 0,
                      };
                    } else {
                      next[activeTab] = {
                        mode: 'option',
                        option_index: optionIndex,
                        question_multi_select: false,
                        option_count: askUserQuestion.questions[activeTab]?.options.length ?? 0,
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
          <button
            onClick={() => {
              setAnswers((prev) => {
                const next = [...prev];
                next[activeTab] = {
                  mode: 'text',
                  text: currentAnswerText(next[activeTab]),
                  option_count: askUserQuestion.questions[activeTab]?.options.length ?? 0,
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
