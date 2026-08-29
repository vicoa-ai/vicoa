// Snake sequence: dotIndex → sequenceIndex in the clockwise 2×3 grid path
// Path: top-left(0) → top-right(1) → mid-right(2) → bot-right(3) → bot-left(4) → mid-left(5)
// Grid dot positions by index: 0=TL, 1=TR, 2=ML, 3=MR, 4=BL, 5=BR
const SNAKE_SEQUENCE_OF_DOT = [0, 1, 5, 2, 4, 3] as const;
const SNAKE_DURATION_MS = 950;
const SNAKE_STEP_MS = SNAKE_DURATION_MS / 6;

export function SnakeLoader({ size = 12 }: { size?: number }) {
  const gap = Math.max(1, Math.round(size * 0.12));
  const dotSize = Math.max(2, Math.floor((size - gap * 2) / 3) - 1);
  const gridW = dotSize * 2 + gap;
  const gridH = dotSize * 3 + gap * 2;
  const offsetX = (size - gridW) / 2;
  const offsetY = (size - gridH) / 2;

  return (
    <div className="flex-shrink-0" style={{ width: size, height: size, position: 'relative' }}>
      {Array.from({ length: 6 }).map((_, dotIndex) => {
        const col = dotIndex % 2;
        const row = Math.floor(dotIndex / 2);
        const seqIdx = SNAKE_SEQUENCE_OF_DOT[dotIndex]!;
        // Negative delay pre-syncs each dot into the correct phase at t=0
        const delayMs = seqIdx * SNAKE_STEP_MS - SNAKE_DURATION_MS;
        return (
          <div
            key={dotIndex}
            style={{
              position: 'absolute',
              width: dotSize,
              height: dotSize,
              backgroundColor: 'currentColor',
              left: offsetX + col * (dotSize + gap),
              top: offsetY + row * (dotSize + gap),
              animation: `snake-dot ${SNAKE_DURATION_MS}ms linear infinite`,
              animationDelay: `${delayMs}ms`,
            }}
          />
        );
      })}
    </div>
  );
}
