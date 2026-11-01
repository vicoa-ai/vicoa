"""Naming a new worktree (and its session) from the spawn's prompt.

A ``spawn-session`` that creates a new worktree with no user-typed name used to
get a random ``adjective-noun`` branch. When it carries a prompt, the server now
asks an LLM for a branch name and a session title while relaying the request,
so the call overlaps the daemon's ``git worktree add`` instead of delaying it:

1. The server adds ``worktree.auto_name = <token>`` to the params it forwards,
   meaning "a name for this spawn is on its way".
2. When the LLM answers, the server pushes a ``worktree-name`` frame —
   ``{"type", "token", "branch"?, "title"?}`` — to the same daemon connection.
   A frame with neither field means naming failed; the daemon stops waiting.
3. Once the checkout exists, the daemon waits for that frame until a short
   budget, counted from the spawn request's arrival, runs out. In time, it
   renames the branch and the folder before the agent starts (nothing
   has run in the folder yet), and hands the title to the agent's registration.
   Late, it launches on the random name and never renames afterwards.

Either side may be older than the other: an old daemon ignores the extra param
and the unknown frame, and an old server never sends the token, so the daemon
does not wait.
"""

# Key inside the spawn-session `worktree` param carrying the naming token.
AUTO_NAME_PARAM = "auto_name"

# Server -> daemon frame carrying the generated names for one token.
WORKTREE_NAME_FRAME = "worktree-name"
