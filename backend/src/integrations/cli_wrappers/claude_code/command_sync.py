"""Helpers for scanning agent slash commands and skills from local folders.

Each entry is ``{name: {"description": str, "kind": "command" | "skill"}}``.
Codex skill entries additionally carry ``"insert"`` — the text a client should
put in the composer when the entry is picked (Codex invokes skills with
``$name``, not ``/name``).
"""

import codecs
import os
from pathlib import Path

# YAML block-scalar indicators: `description: >` (or `|`, with optional
# chomping +/-) puts the actual text on the following indented lines.
_BLOCK_SCALARS = {">", "|", ">-", "|-", ">+", "|+"}

# A description only ever comes from the front matter or the first line, so
# the start of the file is enough, and a stray huge file isn't read in full
# on every `/` panel open.
_READ_CAP = 64 * 1024


def _read_text_head(path: Path) -> str | None:
    """Return the start of a command/skill file, or None if it isn't text.

    Text means no NUL byte and strict UTF-8. Both checks are needed: a ZIP
    renamed to SKILL.md fails the decode, while UTF-16 text decodes cleanly
    with a NUL after every character. Anything else is skipped rather than
    decoded with ``errors="replace"``, which listed binary files as skills
    with a garbage description, and the NUL in it failed the whole
    ``/commands/sync`` upload in Postgres.

    ``utf-8-sig`` drops a BOM, which would otherwise hide the front matter.
    """
    with open(path, "rb") as f:
        data = f.read(_READ_CAP)
    if b"\x00" in data:
        return None
    try:
        # Not final when the cap was hit: the cut may split a multi-byte
        # character, which is not an encoding error.
        return codecs.getincrementaldecoder("utf-8-sig")().decode(
            data, final=len(data) < _READ_CAP
        )
    except UnicodeDecodeError:
        return None


def _extract_command_description(content: str, command_name: str) -> str:
    """Extract the best available description from command markdown."""
    description = ""
    lines = content.split("\n")

    # Check for YAML-style front matter.
    if lines and lines[0].strip() == "---":
        end_index = None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_index = idx
                break

        if end_index:
            for line_index in range(1, end_index):
                parts = lines[line_index].split(":", 1)
                if len(parts) != 2:
                    continue
                if lines[line_index].startswith((" ", "\t")):
                    # Indented: a nested mapping or a block-scalar body line,
                    # not a top-level key.
                    continue
                key, value = parts[0].strip().lower(), parts[1].strip()
                if key != "description":
                    continue
                if value in _BLOCK_SCALARS or not value:
                    collected = []
                    for cont in lines[line_index + 1 : end_index]:
                        if not cont.strip():
                            continue
                        if not cont.startswith((" ", "\t")):
                            break
                        collected.append(cont.strip())
                    description = " ".join(collected).strip("'\" ")
                else:
                    description = value.strip("'\" ")
                if description:
                    break

    # Fallback to first non-empty content or heading line.
    if not description:
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                description = stripped.lstrip("#").strip()
            else:
                description = stripped
            break

    if not description:
        description = f"Custom command: {command_name}"

    return description


def _has_hidden_component(path: Path, relative_to: Path) -> bool:
    """Return True if any path component (relative to base) starts with '.'."""
    return any(part.startswith(".") for part in path.relative_to(relative_to).parts)


def _scan_commands_dir(commands_dir: Path) -> dict:
    """Scan one commands directory and return command metadata."""
    commands = {}
    if not commands_dir.exists():
        return commands

    md_files: list[Path] = []
    for dirpath, _, filenames in os.walk(commands_dir, followlinks=True):
        for filename in filenames:
            if filename.endswith(".md"):
                md_files.append(Path(dirpath) / filename)

    for file_path in sorted(md_files):
        if not file_path.is_file():
            continue
        if _has_hidden_component(file_path, commands_dir):
            continue

        rel_path = file_path.relative_to(commands_dir)
        command_parts = list(rel_path.parts[:-1]) + [file_path.stem]
        command_name = ":".join(command_parts)
        try:
            content = _read_text_head(file_path)
            if content is None:
                print(f"Warning: Skipping command file {file_path}: not UTF-8 text")
                continue

            description = _extract_command_description(content, command_name)
            commands[command_name] = {"description": description, "kind": "command"}
        except Exception as e:
            print(f"Warning: Could not read command file {file_path}: {e}")

    return commands


def _scan_skills_dir_detailed(skills_dir: Path) -> dict:
    """Scan one skills root, returning ``{name: {"description", "path"}}``.

    Per the Agent Skills spec, a skill is a *direct child directory* of the
    skills root that contains a ``SKILL.md`` (``~/.claude/skills/<name>/SKILL.md``),
    named by that directory. A skill's own subfolders (``scripts/``,
    ``references/``, ``templates/``, …) are supporting files, NOT nested skills,
    so we do not recurse: a bundle can vendor a ``skills/`` dir deep inside its
    ``node_modules`` or ship ``test/fixtures`` with their own ``SKILL.md``, and
    recursing would list those as installed skills. Namespaced skills
    (``plugin:name``, ``apps/web:deploy``) come from *separate* roots/plugins the
    caller assembles, never from descending into one root.

    ``path`` is the absolute on-disk skill directory. Shared with
    `_scan_skills_dir` (composer index) and `rpc.skills_ops` (Skills tab).
    """
    skills: dict = {}
    try:
        children = sorted(skills_dir.iterdir())
    except OSError:
        return skills  # missing or unreadable root

    for child in children:
        name = child.name
        # Hidden entries aren't skills: .git, editor cruft, the provenance
        # manifest (.vicoa-skills.json), and per-agent installer dirs (.agents,
        # .cursor, …) some bundles drop beside their real skills.
        if name.startswith("."):
            continue
        skill_file = child / "SKILL.md"
        try:
            # is_dir()/is_file() follow symlinks, so symlinked skills resolve.
            if not (child.is_dir() and skill_file.is_file()):
                continue
            content = _read_text_head(skill_file)
        except OSError as e:
            print(f"Warning: Could not read skill file {skill_file}: {e}")
            continue
        if content is None:
            print(f"Warning: Skipping skill file {skill_file}: not UTF-8 text")
            continue
        skills[name] = {
            "description": _extract_command_description(content, name),
            "path": str(child),
        }

    return skills


def _scan_skills_dir(skills_dir: Path) -> dict:
    """Scan one skills directory and return skill metadata keyed as slash commands."""
    return {
        name: {"description": meta["description"], "kind": "skill"}
        for name, meta in _scan_skills_dir_detailed(skills_dir).items()
    }


def claude_skill_roots(project_root: Path | None = None) -> list[tuple[Path, str]]:
    """The skills dirs Claude reads, global first, each tagged with its scope.

    Project-local ``<root>/.claude/skills`` is appended only when
    ``project_root`` is given — the single source of truth for where Claude
    skills live, shared by `scan_claude_commands` (composer index) and
    `rpc.skills_ops` (the Skills tab, which passes ``None`` for machine-global).
    """
    roots: list[tuple[Path, str]] = [(Path.home() / ".claude" / "skills", "global")]
    if project_root is not None:
        roots.append((project_root / ".claude" / "skills", "project"))
    return roots


def codex_skill_roots(project_root: Path | None = None) -> list[tuple[Path, str]]:
    """The skills dirs Codex reads, tagged with scope (see `claude_skill_roots`).

    ``~/.agents/skills`` is the cross-agent (`npx skills add`) location;
    ``~/.codex/skills`` is Codex-managed. Repo-scoped ``<root>/.agents/skills``
    is appended only when ``project_root`` is given.
    """
    roots: list[tuple[Path, str]] = [
        (Path.home() / ".agents" / "skills", "universal"),
        (Path.home() / ".codex" / "skills", "global"),
    ]
    if project_root is not None:
        roots.append((project_root / ".agents" / "skills", "project"))
    return roots


def scan_claude_commands(
    agent_type: str = "claude", project_root: Path | None = None
) -> dict:
    """Scan Claude command/skill directories for custom user slash commands.

    Args:
        agent_type: Kept for call-site compatibility; ignored.
        project_root: Project directory whose local `.claude` is scanned.
            Defaults to the process CWD (correct for the CLI, which runs in
            the project; RPC/server callers must pass the session's path).

    Returns:
        Dict of commands {name: {description: ..., kind: "command" | "skill"}}
    """
    _ = agent_type

    commands = {}
    # The CLI runs inside the project, so a missing project_root falls back to
    # cwd for the project-local `.claude` (unchanged behavior).
    skills_base = project_root or Path.cwd()
    command_roots = [Path.home() / ".claude", skills_base / ".claude"]
    for claude_root in command_roots:
        # Local ./.claude commands overwrite same-named global commands.
        commands.update(_scan_commands_dir(claude_root / "commands"))

    # Scan skills as slash commands as well.
    # Example: .claude/skills/foo/SKILL.md -> /foo
    # Nested skills are represented with ':' separators for parity with commands.
    # Global is scanned before project, so a global skill wins a same-named
    # project skill; explicit commands stay authoritative over any skill.
    for skills_dir, _scope in claude_skill_roots(skills_base):
        for skill_name, skill_metadata in _scan_skills_dir(skills_dir).items():
            if skill_name in commands:
                continue
            commands[skill_name] = skill_metadata

    return commands


def scan_codex_commands(project_root: Path | None = None) -> dict:
    """Scan Codex custom prompts and skills.

    Sources:
        ~/.codex/prompts        custom prompts, surfaced as slash commands
        ~/.agents/skills        cross-agent skills dir (`npx skills add`)
        ~/.codex/skills         Codex-managed skills (`.system` excluded by
                                the hidden-component filter, deliberately)
        <project>/.agents/skills  repo-scoped skills

    Codex invokes a skill with ``$name`` rather than ``/name``, so each skill
    entry carries an ``insert`` clients use verbatim on selection.
    """
    commands = _scan_commands_dir(Path.home() / ".codex" / "prompts")

    # Later dirs override earlier ones, so repo-scoped skills override same-named
    # global ones, matching Codex's own user < repo scope precedence.
    skills: dict = {}
    for skills_dir, _scope in codex_skill_roots(project_root):
        skills.update(_scan_skills_dir(skills_dir))

    # Keep explicit prompts authoritative when names collide.
    for skill_name, skill_metadata in skills.items():
        if skill_name in commands:
            continue
        commands[skill_name] = {**skill_metadata, "insert": f"${skill_name}"}

    return commands


def scan_agent_commands(agent_type: str, project_root: Path | None = None) -> dict:
    """Scan the local command/skill sources for ``agent_type``.

    Agents without a local source (opencode, amp, generic ACP) return {} —
    their commands, if any, come from the agent process itself.
    """
    normalized = (agent_type or "").lower()
    if "claude" in normalized:
        return scan_claude_commands(agent_type, project_root=project_root)
    if "codex" in normalized:
        return scan_codex_commands(project_root=project_root)
    return {}
