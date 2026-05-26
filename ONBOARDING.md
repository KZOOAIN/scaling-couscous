# Welcome to Kalamazoo AI Lab

## How We Use Claude

Based on kai's usage over the last 30 days (58 sessions):

Work Type Breakdown:
  Build Feature   ████████████████░░░░  40%
  Plan & Design   ██████████░░░░░░░░░░  25%
  Write Docs      ████████░░░░░░░░░░░░  20%
  Improve Quality ███░░░░░░░░░░░░░░░░░   8%
  Analyze Data    ██░░░░░░░░░░░░░░░░░░   7%

Top Skills & Commands:
  /plan           ████████████████░░░░  16x/month
  /clear          ███████████████░░░░░  15x/month
  /model          ███████████████░░░░░  15x/month
  /insights       ████████░░░░░░░░░░░░   8x/month
  /gstack-upgrade ██████░░░░░░░░░░░░░░   6x/month
  /claude-api     █████░░░░░░░░░░░░░░░   5x/month
  /context-save   █████░░░░░░░░░░░░░░░   5x/month
  /autoplan       ██░░░░░░░░░░░░░░░░░░   2x/month
  /office-hours   ██░░░░░░░░░░░░░░░░░░   2x/month
  /resume         ██░░░░░░░░░░░░░░░░░░   2x/month

Top MCP Servers:
  gbrain          ████████████████░░░░   5 calls

## Your Setup Checklist

### Codebases
- [ ] scaling-couscous — https://github.com/kzooain/scaling-couscous
- [ ] gstack — https://github.com/garrytan/gstack (gstack skills source)

### MCP Servers to Activate
- [ ] **gbrain** — Semantic search and memory across your codebase and curated notes. Run `/setup-gbrain` in Claude Code to install and configure. After setup, run `/sync-gbrain` to index the repo.

### Skills to Know About
- `/plan` — Enter plan mode before multi-step or destructive work. The team uses this constantly — present a plan, get approval, then execute. Never skip this for anything that touches config or infra.
- `/context-save` / `/context-restore` — Save and restore your working context across sessions. Use before hitting a usage limit or switching tasks so you can pick up exactly where you left off.
- `/resume` — Auto-discover the most recent in-flight pipeline and resume from the last completed phase. Pair with `/resumable-pipeline` for large deliverables (white papers, system audits, multi-phase builds).
- `/autoplan` — Full review pipeline: plan, implement, and ship a feature end-to-end.
- `/office-hours` — Brainstorm, validate product ideas, or decide if something is worth building before writing any code.
- `/claude-api` — Build and debug Anthropic SDK integrations. Includes prompt caching setup.
- `/insights` — Review what Claude learned about the codebase or workflow during a session.
- `/gstack-upgrade` — Keep gstack skills current. Run this periodically.
- `/sentinel-review` — Triage and acknowledge sentinel incidents (they never auto-resolve on their own).
- `/skill-creator` — Build new reusable slash commands from scratch.

## Team Tips

- **Plan before you act.** Type `/plan` before asking Claude to do anything that changes a file or config. Claude will show you what it's going to do — read it, approve it, then let it run. This one habit prevents most surprises.
- **Save your place.** If you're in the middle of something and need to stop, type `/context-save`. Next session, type `/context-restore` and Claude picks up exactly where you left off — no re-explaining.
- **Talk to Claude like a smart colleague, not a search engine.** Instead of "summarize X," try "I'm meeting a potential partner tomorrow — what should I know about X and what questions should I ask?" The more context you give, the better the output.
- **Use `/office-hours` to think out loud.** Got a half-formed idea? Type `/office-hours` and just describe it. Claude will pressure-test it, ask the right questions, and help you figure out if it's worth building before anyone writes a line of code.

## Get Started

Your first task — no coding required:

**Pitch an idea through `/office-hours`**

Think of one thing you believe KAI could do, automate, or improve — for a customer, a partner, or internally. It doesn't need to be polished.

1. Open Claude Code and type `/office-hours`
2. When it asks what you want to work on, describe your idea in a few sentences — as rough as you like
3. Let Claude ask you questions and push back
4. At the end, ask: *"Give me a one-paragraph summary I could send to a teammate"*
5. Copy that summary and share it in the team channel

This introduces the core loop the team uses for everything: start with `/plan` or `/office-hours`, get alignment, then execute. You'll have done it for real by the end of your first session.

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
