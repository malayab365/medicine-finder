# Subagents

Project-scoped Claude Code subagents live here. Each agent is a Markdown file with YAML frontmatter.

## File format

```markdown
---
name: agent-name              # required, kebab-case
description: When to use it.  # required — Claude reads this to decide when to invoke
tools: Read, Bash, Grep       # optional — omit to inherit all tools
model: sonnet                 # optional — sonnet | opus | haiku | inherit
---

System prompt for the agent.
```

## How they get invoked

- **Automatic delegation**: Claude picks an agent based on the `description` field. Write descriptions that name the trigger ("Use when...", "Use proactively after...").
- **Explicit**: ask Claude to "use the X agent to ..." or, in a parent agent prompt, call the Agent tool with `subagent_type: X`.

## Scope

- Project agents: `.claude/agents/` (this folder) — checked into the repo.
- User agents: `~/.claude/agents/` — available across all projects.
- Project agents override user agents with the same name.

## Examples in this folder

- `code-reviewer.md` — reviews diffs for bugs/security
- `test-runner.md` — runs and diagnoses Python tests
- `researcher.md` — web research with citations
