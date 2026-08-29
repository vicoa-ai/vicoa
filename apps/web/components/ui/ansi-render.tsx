import React from 'react';

export function hasAnsiCodes(text: string): boolean {
  return /<local-command-(stdout|stderr)>/.test(text) || /\[\d+m|\[38;2;\d+;\d+;\d+m|\[\?\d+[hl]/.test(text);
}

// Renders ANSI-escaped terminal output as React nodes with inline colors and
// bold. Used in the user-message bubble so pasted terminal output keeps its
// colors — the markdown pipeline can't carry arbitrary RGB so it uses the
// simpler `normalizeCommandOutput` strip instead.
export function parseAnsiToHtml(text: string): React.ReactNode {
  let cleaned = text.replace(/<local-command-stdout>(.*?)<\/local-command-stdout>/gs, '$1');
  cleaned = cleaned.replace(/<local-command-stderr>[\s\S]*?<\/local-command-stderr>/gs, '');
  cleaned = cleaned.replace(/\[\?\d+[hl]/g, '');

  const parts: React.ReactNode[] = [];
  let currentStyle: { color?: string; bold?: boolean } = {};
  let currentText = '';
  let i = 0;

  const flushText = () => {
    if (currentText) {
      if (currentStyle.color || currentStyle.bold) {
        parts.push(
          <span
            key={parts.length}
            style={{
              color: currentStyle.color,
              fontWeight: currentStyle.bold ? 'bold' : undefined,
            }}
          >
            {currentText}
          </span>
        );
      } else {
        parts.push(currentText);
      }
      currentText = '';
    }
  };

  while (i < cleaned.length) {
    if (cleaned[i] === '[') {
      const match = cleaned.slice(i).match(/^\[([0-9;]+)?m/);
      if (match) {
        flushText();

        const codes = match[1] ? match[1].split(';').map(Number) : [0];

        for (let j = 0; j < codes.length; j++) {
          const code = codes[j];

          if (code === 0) {
            currentStyle = {};
          } else if (code === 1) {
            currentStyle.bold = true;
          } else if (code === 22) {
            currentStyle.bold = false;
          } else if (code === 39) {
            delete currentStyle.color;
          } else if (code === 38 && codes[j + 1] === 2) {
            const r = codes[j + 2];
            const g = codes[j + 3];
            const b = codes[j + 4];
            currentStyle.color = `rgb(${r}, ${g}, ${b})`;
            j += 4;
          }
        }

        i += match[0].length;
        continue;
      }

      const rgbMatch = cleaned.slice(i).match(/^\[38;2;(\d+);(\d+);(\d+)m/);
      if (rgbMatch) {
        flushText();
        const r = rgbMatch[1];
        const g = rgbMatch[2];
        const b = rgbMatch[3];
        currentStyle.color = `rgb(${r}, ${g}, ${b})`;
        i += rgbMatch[0].length;
        continue;
      }
    }

    currentText += cleaned[i];
    i++;
  }

  flushText();
  return parts.length > 0 ? <>{parts}</> : cleaned;
}
