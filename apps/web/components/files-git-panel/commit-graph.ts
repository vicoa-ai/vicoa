// Pure commit lane-graph engine — a port of orca's GitHistoryPanel graph,
// which itself ports VS Code's SCM swimlane layout. No React/DOM deps: it turns
// a topo-ordered commit list into per-row swimlane view-models and SVG geometry.

import type { CommitEntry, CommitRef, RefRevision } from './rpc';

export type GraphColorId =
  | 'git-graph-ref'
  | 'git-graph-remote-ref'
  | 'git-graph-lane-1'
  | 'git-graph-lane-2'
  | 'git-graph-lane-3'
  | 'git-graph-lane-4'
  | 'git-graph-lane-5';

export const LANE_COLORS: readonly GraphColorId[] = [
  'git-graph-lane-1',
  'git-graph-lane-2',
  'git-graph-lane-3',
  'git-graph-lane-4',
  'git-graph-lane-5',
];

// Geometry constants (px). Rows must stack at ROW_H pitch for seamless lanes.
export const LANE_W = 11;
export const ROW_H = 24;
const MID = 12;
const R = 5;
const NODE_R = 3.5;

export interface GraphNode {
  id: string; // commit this lane is heading toward
  color: GraphColorId;
}

export interface CommitViewModel {
  item: CommitEntry;
  inputSwimlanes: GraphNode[]; // lanes entering the top of the row (left→right)
  outputSwimlanes: GraphNode[]; // lanes leaving the bottom of the row
  kind: 'HEAD' | 'node';
}

function rotate(i: number, n: number): number {
  return ((i % n) + n) % n;
}

export function buildDefaultColorMap(
  currentRef?: RefRevision,
  remoteRef?: RefRevision,
): Map<string, GraphColorId> {
  const map = new Map<string, GraphColorId>();
  if (currentRef) map.set(currentRef.name, 'git-graph-ref');
  if (remoteRef) map.set(remoteRef.name, 'git-graph-remote-ref');
  return map;
}

function labelColor(
  commit: CommitEntry,
  colorMap: Map<string, GraphColorId>,
): GraphColorId | undefined {
  for (const ref of commit.refs) {
    const c = colorMap.get(ref.name);
    if (c) return c;
  }
  return undefined;
}

export function buildCommitViewModels(
  commits: CommitEntry[],
  colorMap: Map<string, GraphColorId>,
  currentRef?: RefRevision,
): CommitViewModel[] {
  const viewModels: CommitViewModel[] = [];
  let colorIndex = -1; // persistent cursor into LANE_COLORS across all rows

  for (const item of commits) {
    const kind: 'HEAD' | 'node' =
      currentRef && item.id === currentRef.revision ? 'HEAD' : 'node';
    const prev = viewModels[viewModels.length - 1];
    const inputSwimlanes: GraphNode[] = (prev?.outputSwimlanes ?? []).map((n) => ({ ...n }));
    const outputSwimlanes: GraphNode[] = [];
    let firstParentAdded = false;

    if (item.parent_ids.length > 0) {
      for (const node of inputSwimlanes) {
        if (node.id === item.id) {
          // Collapse the commit's lane to its first parent; drop duplicate
          // merge-in lanes (they converge into the node).
          if (!firstParentAdded) {
            outputSwimlanes.push({
              id: item.parent_ids[0],
              color: labelColor(item, colorMap) ?? node.color,
            });
            firstParentAdded = true;
          }
          continue;
        }
        outputSwimlanes.push({ ...node }); // unrelated lane passes through
      }
    }

    // Emit remaining parents (extra merge parents, or the sole parent of a tip).
    for (let index = firstParentAdded ? 1 : 0; index < item.parent_ids.length; index += 1) {
      let color: GraphColorId | undefined;
      if (index === 0) {
        color = labelColor(item, colorMap);
      } else {
        const parent = commits.find((c) => c.id === item.parent_ids[index]);
        color = parent ? labelColor(parent, colorMap) : undefined;
      }
      if (!color) {
        colorIndex = rotate(colorIndex + 1, LANE_COLORS.length);
        color = LANE_COLORS[colorIndex];
      }
      outputSwimlanes.push({ id: item.parent_ids[index], color });
    }

    viewModels.push({ item, inputSwimlanes, outputSwimlanes, kind });
  }

  return viewModels;
}

export function getLaneIndex(vm: CommitViewModel): number {
  const i = vm.inputSwimlanes.findIndex((n) => n.id === vm.item.id);
  return i !== -1 ? i : vm.inputSwimlanes.length;
}

export function getMergeParentLaneIndex(vm: CommitViewModel, parentId: string): number {
  for (let i = vm.outputSwimlanes.length - 1; i >= 0; i -= 1) {
    if (vm.outputSwimlanes[i].id === parentId) return i;
  }
  return -1;
}

export function refColor(
  vm: CommitViewModel,
  ref: CommitRef,
  colorMap: Map<string, GraphColorId>,
): GraphColorId {
  const mapped = colorMap.get(ref.name);
  if (mapped) return mapped;
  const idx = getLaneIndex(vm);
  return vm.outputSwimlanes[idx]?.color ?? vm.inputSwimlanes[idx]?.color ?? 'git-graph-ref';
}

// ── SVG geometry (pure) ──────────────────────────────────────────────────────

export interface GraphPathSpec {
  d: string;
  color: GraphColorId;
}

export interface GraphCircleSpec {
  cx: number;
  cy: number;
  r: number;
  fill: GraphColorId | 'bg';
  stroke?: GraphColorId | 'bg';
  strokeWidth?: number;
}

export interface GraphRow {
  width: number;
  paths: GraphPathSpec[];
  circles: GraphCircleSpec[];
}

const x = (i: number) => LANE_W * (i + 1);

export function buildGraphRow(vm: CommitViewModel): GraphRow {
  const { inputSwimlanes, outputSwimlanes, item } = vm;
  const circleIndex = getLaneIndex(vm);
  const inputIndex = inputSwimlanes.findIndex((n) => n.id === item.id);
  const circleColor: GraphColorId =
    circleIndex < outputSwimlanes.length
      ? outputSwimlanes[circleIndex].color
      : circleIndex < inputSwimlanes.length
        ? inputSwimlanes[circleIndex].color
        : 'git-graph-ref';

  const paths: GraphPathSpec[] = [];
  let outIdx = 0;

  for (let index = 0; index < inputSwimlanes.length; index += 1) {
    const node = inputSwimlanes[index];
    if (node.id === item.id) {
      if (index === circleIndex) {
        outIdx += 1; // this lane maps to the first-parent output slot
      } else {
        // (a) merge-in curve bending into the node column
        paths.push({
          color: node.color,
          d: `M ${x(index)} 0 A ${LANE_W} ${LANE_W} 0 0 1 ${LANE_W * index} ${MID} H ${x(circleIndex)}`,
        });
      }
      continue;
    }
    if (index === outIdx) {
      // (b) straight pass-through
      paths.push({ color: node.color, d: `M ${x(index)} 0 V ${ROW_H}` });
    } else {
      // (c) column-shift S-curve
      paths.push({
        color: node.color,
        d:
          `M ${x(index)} 0 V 6 ` +
          `A ${R} ${R} 0 0 1 ${x(index) - R} ${MID} ` +
          `H ${x(outIdx) + R} ` +
          `A ${R} ${R} 0 0 0 ${x(outIdx)} ${MID + R} V ${ROW_H}`,
      });
    }
    outIdx += 1;
  }

  // (d) extra merge-parent branches
  for (let index = 1; index < item.parent_ids.length; index += 1) {
    const p = getMergeParentLaneIndex(vm, item.parent_ids[index]);
    if (p < 0) continue;
    const px = LANE_W * p;
    const color = outputSwimlanes[p].color;
    paths.push({
      color,
      d: `M ${px} ${MID} A ${LANE_W} ${LANE_W} 0 0 1 ${px + LANE_W} ${ROW_H}`,
    });
    paths.push({ color, d: `M ${px} ${MID} H ${x(circleIndex)}` });
  }

  // (e) into-node stub
  if (inputIndex !== -1) {
    paths.push({ color: inputSwimlanes[inputIndex].color, d: `M ${x(circleIndex)} 0 V ${MID}` });
  }
  // (f) out-of-node stub
  if (item.parent_ids.length > 0) {
    paths.push({ color: circleColor, d: `M ${x(circleIndex)} ${MID} V ${ROW_H}` });
  }

  // node circle(s)
  const cx = x(circleIndex);
  const circles: GraphCircleSpec[] = [];
  const isMerge = item.parent_ids.length > 1;
  if (vm.kind === 'HEAD') {
    circles.push({ cx, cy: MID, r: NODE_R + 3, fill: circleColor, stroke: 'bg', strokeWidth: 1.5 });
    circles.push({ cx, cy: MID, r: 1.5, fill: 'bg' });
  } else if (isMerge) {
    circles.push({ cx, cy: MID, r: NODE_R + 1, fill: circleColor });
    circles.push({ cx, cy: MID, r: NODE_R - 1.5, fill: 'bg' });
  } else {
    circles.push({ cx, cy: MID, r: NODE_R, fill: circleColor });
  }

  const width = LANE_W * (Math.max(inputSwimlanes.length, outputSwimlanes.length, 1) + 1);
  return { width, paths, circles };
}
