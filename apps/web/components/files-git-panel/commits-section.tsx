'use client';

import { useMemo } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { useCommits } from './use-commits';
import { buildCommitViewModels, buildDefaultColorMap } from './commit-graph';
import { CommitRow } from './commit-row';
import { CommitFiles } from './commit-files';
import { SCROLL_STYLE } from './styles';

type CommitsApi = ReturnType<typeof useCommits>;

/** The scrollable body of the Commits pane: a virtualized commit list (rows
 *  expand inline to files → diffs) plus a Load-more footer. The collapse/resize
 *  chrome is owned by the parent FilesGitPanel. */
export function CommitsSection({
  commits,
  wrapLines,
  splitView,
}: {
  commits: CommitsApi;
  wrapLines: boolean;
  splitView: boolean;
}) {
  const colorMap = useMemo(
    () => buildDefaultColorMap(commits.currentRef, commits.upstreamRef),
    [commits.currentRef, commits.upstreamRef],
  );
  const viewModels = useMemo(
    () => buildCommitViewModels(commits.commits, colorMap, commits.currentRef),
    [commits.commits, colorMap, commits.currentRef],
  );

  if (commits.logError && commits.commits.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-xs text-muted-foreground font-mono">
        {commits.logError === 'not_a_repo'
          ? 'Not a git repository'
          : `Could not load history (${commits.logError})`}
      </div>
    );
  }
  if (commits.commits.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-muted-foreground font-mono">
        {commits.logLoading ? 'Loading history…' : 'No commits yet'}
      </div>
    );
  }

  return (
    <Virtuoso
      className={`h-full ${SCROLL_STYLE}`}
      data={viewModels}
      itemContent={(_index, vm) => {
        const expanded = commits.expandedCommits.has(vm.item.id);
        return (
          <div>
            <CommitRow
              viewModel={vm}
              colorMap={colorMap}
              expanded={expanded}
              onToggle={() => commits.toggleCommit(vm.item.id)}
            />
            {expanded && (
              <CommitFiles
                commit={vm.item}
                files={commits.filesByCommit.get(vm.item.id)}
                diffs={commits.commitDiffs}
                expandedFiles={commits.expandedFiles}
                wrapLines={wrapLines}
                splitView={splitView}
                onToggleFile={commits.toggleFile}
              />
            )}
          </div>
        );
      }}
      components={{
        Footer: () =>
          commits.hasMore ? (
            <button
              type="button"
              onClick={commits.loadMore}
              className="w-full py-2 text-center text-xs font-mono text-muted-foreground hover:text-foreground"
            >
              {commits.logLoading ? 'Loading…' : 'Load more'}
            </button>
          ) : null,
      }}
    />
  );
}
