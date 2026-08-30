import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Convert a project path with tilde (~) to an absolute path using the home directory
 * @param project - Project path (may contain ~)
 * @param homeDir - Home directory path for expansion
 * @returns Absolute path, or undefined if project is null/undefined
 */
export function toAbsolutePath(
  project: string | null | undefined,
  homeDir: string | null | undefined
): string | undefined {
  if (!project) return undefined;
  if (!project.startsWith('~')) return project; // Already absolute
  if (!homeDir) return project; // Can't convert, return as-is

  return project.replace(/^~/, homeDir);
}
