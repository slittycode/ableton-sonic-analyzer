# Pi setup for ASA

Project-local Pi config so sessions in this repo do **not** inherit the global
default (`grok-build`). Product work should use Claude; sandbox model bakeoffs
belong in an empty `/tmp` folder, never here.

## Start here

```bash
cd ~/code/projects/ableton-sonic-analyzer/asa
pi
```

**Do not** start Pi from the parent `ableton-sonic-analyzer/` shelf. That folder
is multi-project (`asa/`, `asa-ableton/`, `inspiration/`) and is **not** the git
root. Agent docs, hooks, and this `.pi/` tree only apply under `asa/`.

On first open in this directory:

1. Trust the project when prompted (`/trust` if needed) so `.pi/settings.json`,
   prompts, and skills load.
2. Confirm the model is Claude Sonnet (not Grok). Ctrl+P cycles
   `enabledModels` from settings.
3. Optional warm-up: `/asa-start`

## What this config sets

| Setting | Value | Why |
|---|---|---|
| `defaultProvider` / `defaultModel` | `anthropic` / `claude-sonnet-4-6` | Best quality/$ coding default for ASA; 1M context |
| `defaultThinkingLevel` | `medium` | Reasoning without Opus-level think bills |
| `enabledModels` | Sonnet 4.6/4.5, Opus 4.6/4.5, Haiku 4.5 | Fast cycle for hard vs bulk work |
| `skills` | `../.claude/skills` | Reuse Claude Code ASA skills (`asa-context`, `asa-verify`, …) |
| `sessionDir` | `.pi/sessions` | Sessions stay local (gitignored) |
| `compaction` | on | Long DSP/UI threads stay usable |

Global Pi packages (`pi-mcp-adapter`, `pi-web-access`, `pi-hermes-memory`) still
load from `~/.pi/agent/settings.json`. This file only **overrides** model +
project resources.

## Prompt templates (type `/` in Pi)

| Command | Use |
|---|---|
| `/asa-start` | Session boot: cwd check, PURPOSE/CLAUDE, no sandbox dirs |
| `/asa-verify` | Pre-ship verification checklist |
| `/asa-backend` | Backend/DSP contract change checklist |
| `/asa-ui` | UI change checklist |

## Skills

From `.claude/skills` (via settings):

- `asa-context` — warm-up / mission + architecture summary
- `asa-dev` — guarded full-stack launch
- `asa-verify` — full test orchestration
- `asa-explain` — Phase 1 field explainer
- `asa-verify-device` — Live 12 device spelling check

Design skills (single realpath each — do **not** re-copy into `.pi/skills/`):

- `hallmark` — project `.agents` / `.claude` → `~/.agents/skills/hallmark`
- `impeccable` — project `.agents/skills/impeccable` (`.claude` symlink)

Also available globally when present: `asa-sonic-iterate` under
`~/.agents/skills/` (Pi discovers that path automatically).

Invoke with `/skill:asa-context` (or read the skill file) when the task matches.

**Collision rule:** Pi loads `.pi/skills`, project `.agents/skills`, settings
`skills` (here: `.claude/skills`), plus `~/.agents/skills` and
`~/.pi/agent/skills`. Same skill name with different realpaths → warn and keep
first. Prefer one canonical dir + symlinks; never duplicate skill trees.

## MCP (global, not duplicated here)

Pi MCP lives in `~/.pi/agent/mcp.json` (not project-scoped in current Pi).
For ASA coding sessions, prefer a **small** set:

1. `ableton` — Live device truth for Phase 2 recommendations  
2. `github` — PRs/issues  
3. `fetch` or `deepwiki` — docs lookup  

Keep music discovery MCPs (MusicBrainz, Discogs, Last.fm, Apple Music,
live-coding-music) for research sessions, not default `analyze.py` refactors.

To align Pi MCP with the shared registry:

```bash
# edit ~/.config/ai/servers.json / tools.json if needed
~/.config/ai/sync.sh --tool pi   # if your sync supports pi
# or hand-edit ~/.pi/agent/mcp.json
```

## Hard workspace rules (agents)

1. Work only inside this git root (`asa/`).
2. Do **not** create top-level eval/demo sandboxes (`agent-eval/`, `tmp-cli/`, …).
3. Throwaway experiments → `/tmp/asa-scratch/` or `.worktrees/`.
4. Never claim tests green without running them.
5. Contract changes update schema + both sides (see `CLAUDE.md` tripwires).
6. Secrets stay in `~/.asa/env` — never commit keys.

## Model routing (suggested)

| Work | Model | Thinking |
|---|---|---|
| Default implement / UI / tests | Sonnet 4.6 (or 4.5) | medium |
| Hard architecture / Phase 2 citation design | Opus 4.6 | medium–high |
| Bulk mechanical renames / greps | Haiku 4.5 | low / off |
| Cheap draft outside product | Grok/MiniMax in empty `/tmp` only | — |

## Companion docs

Precedence: `PURPOSE.md` > `CLAUDE.md` > per-app `AGENTS.md` > this file.

See also: `apps/backend/AGENTS.md`, `apps/ui/AGENTS.md`,
`docs/ARCHITECTURE_STRATEGY.md`.
