/**
 * Opt-in console trace of a drag-selection inside the transcript, for chasing
 * selection jumps that only reproduce on a real trackpad / in the desktop app.
 *
 * Enable in DevTools with `localStorage.setItem('vicoa:sel-debug', '1')` and
 * reload; every primary-button drag then logs the pointer path, each Blink
 * selection update (anchor/focus with surrounding text), and any DOM mutation
 * under the transcript while the button is down. Disable by removing the key.
 */

const ENABLE_KEY = 'vicoa:sel-debug';

export function selectionTraceEnabled(): boolean {
  try {
    return typeof window !== 'undefined' && window.localStorage.getItem(ENABLE_KEY) === '1';
  } catch {
    return false;
  }
}

function describeNode(node: Node | null, offset: number): string {
  if (!node) return 'null';
  if (node.nodeType === Node.TEXT_NODE) {
    const text = (node as Text).data;
    return `#text"${text.slice(Math.max(0, offset - 12), offset)}|${text.slice(offset, offset + 12)}"@${offset}`;
  }
  const el = node as Element;
  const cls = typeof el.className === 'string' && el.className ? '.' + el.className.split(' ').slice(0, 2).join('.') : '';
  return `${el.tagName.toLowerCase()}${cls}@${offset}`;
}

function describeSelection(): string {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return 'none';
  const text = sel.toString();
  const snippet = text.length > 60 ? `${text.slice(0, 40)}…${text.slice(-16)}` : text;
  return `${sel.type} anchor=${describeNode(sel.anchorNode, sel.anchorOffset)} focus=${describeNode(sel.focusNode, sel.focusOffset)} len=${text.length} "${snippet.replace(/\s+/g, ' ')}"`;
}

/** Attach to the transcript container. Returns the detach function. */
export function attachSelectionDragTrace(container: HTMLElement): () => void {
  let dragging = false;
  let moves = 0;
  const log = (...args: unknown[]) => console.log('[sel-trace]', ...args);
  const observer = new MutationObserver((records) => {
    if (!dragging) return;
    for (const r of records) {
      const moved = r.addedNodes[0] ?? r.removedNodes[0] ?? null;
      const parent = r.target instanceof Element ? r.target : null;
      const chain = parent ? [parent, parent.parentElement, parent.parentElement?.parentElement].filter(Boolean).map((e) => describeNode(e as Element, 0)).join(' < ') : describeNode(r.target, 0);
      log(`MUTATION ${r.type} on ${chain} +${r.addedNodes.length} -${r.removedNodes.length}${r.attributeName ? ' attr=' + r.attributeName : ''}${moved ? ' node=' + describeNode(moved, 0) : ''}`);
    }
  });

  const onMouseDown = (e: MouseEvent) => {
    if (e.button !== 0) return;
    dragging = true;
    moves = 0;
    const target = e.target instanceof Element ? e.target : null;
    const round = document.caretRangeFromPoint?.(Math.round(e.clientX), Math.round(e.clientY));
    const floor = document.caretRangeFromPoint?.(Math.floor(e.clientX), Math.floor(e.clientY));
    log(`DOWN (${e.clientX}, ${e.clientY}) detail=${e.detail} on ${target ? describeNode(target, 0) : '?'} caret@round=${round ? describeNode(round.startContainer, round.startOffset) : 'null'} caret@floor=${floor ? describeNode(floor.startContainer, floor.startOffset) : 'null'} dpr=${window.devicePixelRatio}`);
    observer.observe(container, { subtree: true, childList: true, characterData: true });
  };
  const onMouseMove = (e: MouseEvent) => {
    if (!dragging) return;
    moves += 1;
    if (moves <= 5 || moves % 5 === 0) log(`MOVE#${moves} (${e.clientX}, ${e.clientY}) buttons=${e.buttons}`);
  };
  const onSelectionChange = () => {
    if (!dragging) return;
    log(`SEL ${describeSelection()}`);
  };
  const onMouseUp = (e: MouseEvent) => {
    if (!dragging) return;
    dragging = false;
    observer.disconnect();
    log(`UP (${e.clientX}, ${e.clientY}) after ${moves} moves → ${describeSelection()}`);
  };

  container.addEventListener('mousedown', onMouseDown, { passive: true });
  document.addEventListener('mousemove', onMouseMove, { passive: true });
  document.addEventListener('mouseup', onMouseUp, { passive: true });
  document.addEventListener('selectionchange', onSelectionChange);
  log('enabled on', describeNode(container, 0));
  return () => {
    observer.disconnect();
    container.removeEventListener('mousedown', onMouseDown);
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    document.removeEventListener('selectionchange', onSelectionChange);
  };
}
