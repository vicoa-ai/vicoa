export function diffKey(path: string, staged: boolean): string {
  return `${staged ? 'S' : 'U'}:${path}`;
}

/** Key for one file *inside* submodule `sub`. NUL-separated because a path may
 * legally contain any character except NUL, so nothing else guarantees the two
 * halves can't collide. Carries `staged` for the same reason `diffKey` does:
 * one path can sit in both the staged and unstaged sections at once. */
export function submoduleFileKey(sub: string, file: string, staged: boolean): string {
  return `SUB:${staged ? 'S' : 'U'}:${sub}\u0000${file}`;
}

/** Absolute cwd of a submodule — the git RPCs take a repo directory, and a
 * submodule is a full repo in its own right. */
export function submoduleCwd(parentCwd: string, sub: string): string {
  return `${parentCwd.replace(/\/+$/, '')}/${sub}`;
}

export class ConcurrencyQueue {
  private active = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(private readonly limit: number) {}

  async run<T>(task: () => Promise<T>): Promise<T> {
    if (this.active >= this.limit) {
      await new Promise<void>((resolve) => {
        this.waiting.push(resolve);
      });
    }
    this.active++;
    try {
      return await task();
    } finally {
      this.active--;
      const next = this.waiting.shift();
      if (next) next();
    }
  }
}
