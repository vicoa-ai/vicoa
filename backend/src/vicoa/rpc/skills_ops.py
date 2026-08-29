"""Daemon RPC handlers for the Skills tab: list / get / install / uninstall.

Agent skills live on disk in the same dirs the slash-command index
(`command_index.scan_commands`) reads, so an install here shows up in the
composer's `/` menu on its next scan and an uninstall removes it there too —
no second store to sync. This module owns the *management* surface (paths,
provenance, install/remove/read); `scan-commands` stays the composer's read
path.

Per-agent locations (confirmed against the agents' own docs + the `skills`
CLI, github.com/vercel-labs/skills):
  - claude   own ~/.claude/skills             — does NOT read ~/.agents/skills
  - codex    own ~/.codex/skills  + shared ~/.agents/skills
  - opencode own ~/.config/opencode/skills + shared ~/.agents/skills
`~/.agents/skills` is the cross-agent ("universal") dir read by the
`.agents/skills`-family agents (codex/opencode/…) but NOT by Claude Code.

Provenance is recorded DB-less in a hidden per-root manifest
(`<root>/.vicoa-skills.json`) mapping skill name -> {source_url, subdir,
installed_at}; it starts with a dot so the scanners skip it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.cli_wrappers.claude_code.command_sync import (
    _extract_command_description,
    _scan_skills_dir_detailed,
    claude_skill_roots,
    codex_skill_roots,
)
from vicoa.rpc.paths import OutsideRoot, resolve_inside_root

_MANIFEST_NAME = ".vicoa-skills.json"

# Guardrails on a cloned repo before it lands on disk (mirrors rpc.file_ops caps).
_MAX_FILE_BYTES = 1 * 1024 * 1024
_MAX_TOTAL_BYTES = 25 * 1024 * 1024
_MAX_FILE_COUNT = 512
# Must finish inside the WS RPC budget (~30s server / 35s client).
_CLONE_TIMEOUT_S = 25
# Caps for the detail view (get_skill).
_MAX_CONTENT_CHARS = 200_000
_MAX_SUPPORTING_FILES = 200

_GIT_URL_SCHEMES = ("https://", "http://", "git://", "ssh://", "file://", "git@")

# The composer index tags roots "global"/"universal"; the tab shows user/shared.
_SCOPE_LABELS = {"global": "user", "universal": "shared"}

# Where a form-driven install lands per agent (its own dir, except Codex where
# the documented user location is the shared ~/.agents/skills).
_INSTALL_SCOPE = {"claude": "user", "codex": "shared", "opencode": "user"}


# --------------------------------------------------------------------------- #
# Agent → roots
# --------------------------------------------------------------------------- #
def _normalize_agent(agent_type: str | None) -> str | None:
    """Map an agent_type string to a supported agent id, or None."""
    normalized = (agent_type or "").lower()
    if "claude" in normalized:
        return "claude"
    if "codex" in normalized:
        return "codex"
    if "opencode" in normalized:
        return "opencode"
    return None


def _read_roots(agent: str) -> list[tuple[Path, str]]:
    """Machine-global skill roots the tab reads for `agent`, scope-tagged.

    Claude/Codex reuse the composer's root helpers (single source of truth with
    the `/` menu); OpenCode's dirs are defined here since the composer index
    doesn't scan it (its commands come from the agent process).
    """
    if agent == "claude":
        base = claude_skill_roots(None)
    elif agent == "codex":
        base = codex_skill_roots(None)
    elif agent == "opencode":
        home = Path.home()
        base = [
            (home / ".config" / "opencode" / "skills", "global"),
            (home / ".agents" / "skills", "universal"),
        ]
    else:
        return []
    return [(path, _SCOPE_LABELS.get(scope, scope)) for path, scope in base]


def _install_root(agent: str) -> Path:
    """Where a newly installed skill is written for `agent`."""
    home = Path.home()
    roots = {
        "claude": home / ".claude" / "skills",
        "codex": home / ".agents" / "skills",
        "opencode": home / ".config" / "opencode" / "skills",
    }
    if agent not in roots:
        raise ValueError(f"unsupported agent: {agent}")
    return roots[agent]


# --------------------------------------------------------------------------- #
# Manifest (provenance)
# --------------------------------------------------------------------------- #
def _manifest_path(root: Path) -> Path:
    return root / _MANIFEST_NAME


def _read_manifest(root: Path) -> dict[str, dict]:
    try:
        with open(_manifest_path(root), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".vicoa-tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _write_manifest_entry(root: Path, name: str, entry: dict) -> None:
    data = _read_manifest(root)
    data[name] = entry
    _atomic_write_json(_manifest_path(root), data)


def _drop_manifest_entry(root: Path, name: str) -> None:
    data = _read_manifest(root)
    if name in data:
        del data[name]
        _atomic_write_json(_manifest_path(root), data)


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _valid_git_url(url: Any) -> bool:
    return (
        isinstance(url, str)
        and bool(url.strip())
        and url.strip().startswith(_GIT_URL_SCHEMES)
    )


def _sanitize_skill_name(name: str | None) -> str | None:
    """A skill name is a single dir component (nested skills use ':').

    Rejects path separators, traversal, leading dots, and control chars so the
    name can never escape the skills root. Returns the cleaned name or None.
    """
    if not name:
        return None
    cleaned = name.strip()
    if cleaned in (".", "..") or not cleaned:
        return None
    if cleaned.startswith("."):
        return None
    if "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        return None
    if os.sep in cleaned or (os.altsep and os.altsep in cleaned):
        return None
    return cleaned


def _skill_name_from_frontmatter(content: str) -> str | None:
    """Read the top-level `name:` from a SKILL.md YAML frontmatter block."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith((" ", "\t")):
            continue
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[0].strip().lower() == "name":
            return parts[1].strip().strip("'\" ")
    return None


def _safe_relpath(rel: str) -> str | None:
    """Normalize a caller-supplied subdirectory to a repo-relative path, or None
    if it tries to escape (absolute, `..`)."""
    if not isinstance(rel, str):
        return None
    cleaned = rel.strip().strip("/")
    if not cleaned:
        return None
    normalized = os.path.normpath(cleaned)
    if normalized.startswith("..") or os.path.isabs(normalized):
        return None
    return normalized


def _within_caps(src: Path) -> tuple[bool, str]:
    """Check the cloned tree (excluding .git) fits the install size/count caps."""
    total = 0
    count = 0
    for dirpath, dirnames, filenames in os.walk(src):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in filenames:
            try:
                size = (Path(dirpath) / filename).stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES:
                return False, "file_too_large"
            total += size
            count += 1
            if count > _MAX_FILE_COUNT:
                return False, "too_many_files"
            if total > _MAX_TOTAL_BYTES:
                return False, "skill_too_large"
    return True, ""


def _list_supporting_files(skill_dir: Path) -> list[dict[str, Any]]:
    """Relative paths + sizes of files under a skill dir, excluding SKILL.md/.git."""
    files: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(skill_dir):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for filename in sorted(filenames):
            if dirpath == str(skill_dir) and filename == "SKILL.md":
                continue
            abs_path = Path(dirpath) / filename
            try:
                size = abs_path.stat().st_size
            except OSError:
                continue
            files.append({"path": str(abs_path.relative_to(skill_dir)), "size": size})
            if len(files) >= _MAX_SUPPORTING_FILES:
                return files
    return files


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# RPC handlers
# --------------------------------------------------------------------------- #
def list_skills(agent_type: str, cwd: str | None = None) -> dict[str, Any]:
    """Return the machine-global skills installed for ``agent_type``.

    ``supported`` is False for agents with no managed local skill source — an
    empty, non-error answer the tab renders as a note.
    """
    _ = cwd  # machine-global; project-local skills stay a composer concern
    agent = _normalize_agent(agent_type)
    if agent is None:
        return {"skills": [], "supported": False}

    seen: set[str] = set()
    skills: list[dict[str, Any]] = []
    for root, scope in _read_roots(agent):
        manifest = _read_manifest(root)
        for name, meta in _scan_skills_dir_detailed(root).items():
            if name in seen:
                continue  # first (own-dir) root wins; a duplicate name is cosmetic
            seen.add(name)
            prov = manifest.get(name) or {}
            skills.append(
                {
                    "name": name,
                    "description": meta["description"],
                    "path": meta["path"],
                    "scope": scope,
                    "source": prov.get("source_url"),
                    "installed_at": prov.get("installed_at"),
                }
            )
    skills.sort(key=lambda entry: entry["name"].lower())
    return {"skills": skills, "supported": True}


def get_skill(agent_type: str, name: str) -> dict[str, Any]:
    """Return the full SKILL.md content + supporting-file list for one skill."""
    agent = _normalize_agent(agent_type)
    if agent is None:
        return {"error": "unsupported_agent"}
    safe = _sanitize_skill_name(name)
    if safe is None:
        return {"error": "invalid_skill_name"}

    rel = safe.replace(":", os.sep)
    for root, scope in _read_roots(agent):
        try:
            target = resolve_inside_root(root, rel)
        except OutsideRoot:
            continue
        skill_md = target / "SKILL.md"
        if not (target.is_dir() and skill_md.is_file()):
            continue
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"error": "read_failed"}
        prov = _read_manifest(root).get(safe) or {}
        return {
            "name": safe,
            "content": content[:_MAX_CONTENT_CHARS],
            "truncated": len(content) > _MAX_CONTENT_CHARS,
            "files": _list_supporting_files(target),
            "path": str(target),
            "scope": scope,
            "source": prov.get("source_url"),
            "installed_at": prov.get("installed_at"),
        }
    return {"error": "not_found"}


def install_skill(
    agent_type: str,
    git_url: str,
    subdir: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Clone a git repo and install the skill it contains for ``agent_type``.

    The repo root (or ``subdir`` within it) must contain a ``SKILL.md``. Returns
    the installed skill summary, or ``{"error": <code>}``: invalid_url /
    clone_failed / install_timeout / git_not_available / invalid_subdir /
    skill_md_not_found / invalid_skill_name / {file_too_large, too_many_files,
    skill_too_large} / skill_exists / unsupported_agent.
    """
    agent = _normalize_agent(agent_type)
    if agent is None:
        return {"error": "unsupported_agent"}
    if not _valid_git_url(git_url):
        return {"error": "invalid_url"}

    tmp = tempfile.mkdtemp(prefix="vicoa-skill-")
    try:
        clone_dir = os.path.join(tmp, "repo")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    git_url.strip(),
                    clone_dir,
                ],
                capture_output=True,
                timeout=_CLONE_TIMEOUT_S,
                check=True,
            )
        except subprocess.TimeoutExpired:
            return {"error": "install_timeout"}
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace")[-400:].strip()
            return {"error": "clone_failed", "detail": detail}
        except FileNotFoundError:
            return {"error": "git_not_available"}

        src = Path(clone_dir)
        if subdir:
            safe = _safe_relpath(subdir)
            if safe is None:
                return {"error": "invalid_subdir"}
            src = src / safe

        skill_md = src / "SKILL.md"
        if not skill_md.is_file():
            return {"error": "skill_md_not_found"}

        content = skill_md.read_text(encoding="utf-8", errors="replace")
        name = _sanitize_skill_name(_skill_name_from_frontmatter(content) or src.name)
        if name is None:
            return {"error": "invalid_skill_name"}

        ok, cap_error = _within_caps(src)
        if not ok:
            return {"error": cap_error}

        root = _install_root(agent)
        try:
            dest = resolve_inside_root(root, name)
        except OutsideRoot:
            return {"error": "invalid_skill_name"}

        if dest.exists():
            if not overwrite:
                return {"error": "skill_exists"}
            shutil.rmtree(dest)

        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))

        installed_at = _utcnow_iso()
        _write_manifest_entry(
            root,
            name,
            {
                "source_url": git_url.strip(),
                "subdir": subdir or "",
                "installed_at": installed_at,
            },
        )
        return {
            "name": name,
            "description": _extract_command_description(content, name),
            "path": str(dest),
            "scope": _INSTALL_SCOPE.get(agent, "user"),
            "source": git_url.strip(),
            "installed_at": installed_at,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uninstall_skill(agent_type: str, name: str) -> dict[str, Any]:
    """Delete an installed skill directory for ``agent_type``.

    Searches the agent's global roots for a ``<root>/<name>`` dir holding a
    SKILL.md, confined by `resolve_inside_root`. Returns {"ok": True} or
    {"error": not_found | invalid_skill_name | unsupported_agent}.
    """
    agent = _normalize_agent(agent_type)
    if agent is None:
        return {"error": "unsupported_agent"}
    safe = _sanitize_skill_name(name)
    if safe is None:
        return {"error": "invalid_skill_name"}

    # Nested skills key on ':' (parity with the scanners); map to a path.
    rel = safe.replace(":", os.sep)
    for root, _scope in _read_roots(agent):
        try:
            target = resolve_inside_root(root, rel)
        except OutsideRoot:
            continue
        if target.is_dir() and (target / "SKILL.md").is_file():
            # A symlinked skill (linked in from a repo): remove only the link,
            # never the source tree it points at. shutil.rmtree also refuses to
            # run on a symlink, so this guard is required, not just polite.
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
            _drop_manifest_entry(root, safe)
            return {"ok": True}
    return {"error": "not_found"}
