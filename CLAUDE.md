## Approach Discipline

- Do NOT execute or edit until the user explicitly approves the plan. After presenting a plan, wait for confirmation before any tool use beyond read-only exploration.
- Avoid excessive clarifying questions or exploration when the request is concrete (e.g., 'edit marketplace.json'). Make the change, then explain.
- For multi-step work, present a numbered plan first, then pause.

## Honesty Over Hallucination

- If asked about an unfamiliar term, plugin, or command (e.g., 'Bramblesnit', unknown skills), say 'I don't recognize this — can you point me to docs or context?' Do NOT fabricate plausible-sounding answers.
- Before claiming a slash command exists, verify it is registered in ~/.claude/skills/ or the active plugin set.

## Workflow Discipline

- Present plans/diagrams inline FIRST before writing files
- Wait for explicit approval before moving from planning to execution
- When user says 'proceed', confirm scope before tool execution if multiple paths exist

## Project Context

This project uses OpenClaw with Ollama for local LLM inference, Telegram bot integration, and Cloudflare tunnels on Docker. The primary agent model is `openai-codex/gpt-5.5` (cloud-routed via the `openai-codex` provider); the local fallback is `ollama/qwen3.5:9b`, with `hf.co/unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_XL` also registered. Do not assume or suggest other models without checking `ollama list` first (for local models) or `~/.openclaw/openclaw.json` under `agents.defaults.models` (for agent bindings).

## Kalamazoo AI Lab Context

- Project: AI-native corporate OS / KAI identity architecture / AI-defense security
- When research requires Google Docs, ask user to paste content (Claude cannot authenticate)
- Default to grounded analysis: inspect actual codebase/config before strategic recommendations

## Configuration Files

When editing JSON config files (especially openclaw.json), always validate JSON syntax after edits using `cat <file> | python3 -m json.tool` or `jq .` before reporting success. Never edit JSON files that the user may be concurrently editing without confirming first.

## OpenClaw Stack Conventions

- Config lives in openclaw.json; Telegram credentials are under `.channels` (NOT `.integrations`).
- Validate JSON after every edit to settings.json or openclaw.json (use `jq . <file>` or the JSON validation hook).
- PM2 Node processes need `max-old-space-size` set in the ecosystem file when memory pressure is observed.
- Never edit settings.json or openclaw.json without first reading current contents — concurrent user edits have caused conflicts.

## General Rules

If you cannot perform a task (browser-based setup, authenticated URL access, actions blocked by plan mode), say so immediately rather than attempting workarounds that waste time. Never fabricate answers—if you don't know something, say so.

## OpenClaw/Sentinel Stack

- Sentinel config uses `.channels` not `.integrations` in JSON paths
- PreToolUse hooks: exit code 2 blocks, exit code 1 does not
- Verify display detection includes ALL connected displays before framebuffer ops
- Never auto-revert openclaw.json Phase 1 edits
- **Model update atomicity**: When changing `.agents.defaults.model.primary` in openclaw.json, ALSO update `EXPECTED_PRIMARY_MODEL` in `~/.claude/sentinel/checks/model-routing.sh`. Mismatched values produce a permanent WARNING incident every 5 min that never auto-resolves.
- **`"to "` prefix trap**: Manually editing openclaw.json with nano can accidentally produce `"to openai-codex/gpt-5.5"` instead of `"openai-codex/gpt-5.5"`. Always verify after edits: `jq '.agents.defaults.model.primary' ~/.openclaw/openclaw.json`
- **`qwen3.5:4b` is broken as a fallback**: It loops infinitely on the OpenAI-compat `/v1/chat/completions` endpoint. Approved local fallback is `ollama/qwen3.5:9b` only.
- **Codex token refresh is human-only**: `codex login status` never advances `last_refresh`. Only `codex login` (interactive browser flow) actually refreshes OAuth tokens. Run it immediately when sentinel reports `codex_token_expiry`.
- **`pending_approval` incidents never auto-resolve**: Handle via `/sentinel-review` or manually set `status` to `"acknowledged"` in the incident JSON. They do NOT escalate to Telegram — they accumulate silently.
- **Sentinel `stopped` status is normal**: `sentinel-orchestrator` and `sentinel-coordinator` always show `stopped` in `pm2 list` between cron fires. Correct pattern: `autorestart: false`, fire-and-exit. Only investigate if restart count (↺) spikes unexpectedly.
- **SecretRefs resolved from `.openclaw/.env`, not shell env**: OpenClaw's `secrets.providers.default.source = "env"` reads `~/.openclaw/.env` (dotenv file), NOT the current shell's exported variables. Setting `TELEGRAM_TOKEN=x` in shell has no effect.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills:
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`

When spawning Claude Code sessions for coding work via OpenClaw, tell the session to use gstack skills. Examples:
- Security audit: "Load gstack. Run /cso"
- Code review: "Load gstack. Run /review"
- QA test a URL: "Load gstack. Run /qa https://..."
- Build a feature end-to-end: "Load gstack. Run /autoplan, implement the plan, then run /ship"
- Plan before building: "Load gstack. Run /office-hours then /autoplan. Save the plan, don't implement."

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. The
skill has multi-step workflows, checklists, and quality gates that produce better
results than an ad-hoc answer. When in doubt, invoke the skill. A false positive is
cheaper than a false negative.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke /office-hours
- Strategy, scope, "think bigger", "what should we build" → invoke /plan-ceo-review
- Architecture, "does this design make sense" → invoke /plan-eng-review
- Design system, brand, "how should this look" → invoke /design-consultation
- Design review of a plan → invoke /plan-design-review
- Developer experience of a plan → invoke /plan-devex-review
- "Review everything", full review pipeline → invoke /autoplan
- Bugs, errors, "why is this broken", "wtf", "this doesn't work" → invoke /investigate
- Test the site, find bugs, "does this work" → invoke /qa (or /qa-only for report only)
- Code review, check the diff, "look at my changes" → invoke /review
- Visual polish, design audit, "this looks off" → invoke /design-review
- Developer experience audit, try onboarding → invoke /devex-review
- Ship, deploy, create a PR, "send it" → invoke /ship
- Merge + deploy + verify → invoke /land-and-deploy
- Configure deployment → invoke /setup-deploy
- Post-deploy monitoring → invoke /canary
- Update docs after shipping → invoke /document-release
- Weekly retro, "how'd we do" → invoke /retro
- Second opinion, codex review → invoke /codex
- Safety mode, careful mode, lock it down → invoke /careful or /guard
- Restrict edits to a directory → invoke /freeze or /unfreeze
- Upgrade gstack → invoke /gstack-upgrade
- Save progress, "save my work" → invoke /context-save
- Resume, restore, "where was I" → invoke /context-restore
- Security audit, OWASP, "is this secure" → invoke /cso
- Make a PDF, document, publication → invoke /make-pdf
- Launch real browser for QA → invoke /open-gstack-browser
- Import cookies for authenticated testing → invoke /setup-browser-cookies
- Performance regression, page speed, benchmarks → invoke /benchmark
- Review what gstack has learned → invoke /learn
- Tune question sensitivity → invoke /plan-tune
- Code quality dashboard → invoke /health
- Display config, screen tearing, xorg, nvidia-settings, monitor layout → invoke /nvidia-display-audit

## Ultraplan / Git Prerequisites

- Ultraplan and batch operations REQUIRE the working directory to be a git repo with at least one commit
- Before suggesting ultraplan, verify: `git rev-parse --git-dir && git log -1` succeed
- gh CLI: confirm `gh auth status` shows the correct account before any GitHub operations
