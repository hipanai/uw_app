# Agent Instructions

> This file is mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Directive (What to do)**
- SOPs written in Markdown, live in `directives/`
- Define goals, inputs, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee
- **Each directive has YAML front matter** with `name`, `description`, and `scripts` fields
- The `scripts` field lists exactly which execution files to call—scan this first before reading full directive

**Layer 2: Orchestration (Decision making)**
- This is you. Your job: intelligent routing.
- Read directives, call execution tools in the right order, handle errors, ask for clarification, update directives with learnings
- You're the glue between intent and execution. E.g you don't try scraping websites yourself—you read `directives/scrape_website.md` and come up with inputs/outputs and then run `execution/scrape_single_site.py`

**Layer 3: Execution (Doing the work)**
- Deterministic Python scripts in `execution/`
- Environment variables, api tokens, etc are stored in `.env`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast. Use scripts instead of manual work.

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution is push complexity into deterministic code. That way you just focus on decision-making.

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits/etc—in which case you check w user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: you hit an API rate limit → you then look into API → find a batch endpoint that would fix → rewrite script to accommodate → test → update directive.

**3. Update directives as you learn**
Directives are living documents. When you discover API constraints, better approaches, common errors, or timing expectations—update the directive. But don't create or overwrite directives without asking unless explicitly told to. Directives are your instruction set and must be preserved (and improved upon over time, not extemporaneously used and then discarded).

## Reading Directives Efficiently

**Context efficiency matters.** Don't read entire directive files when you only need to find the right one. Use YAML front matter to scan first.

**Front matter format (Claude Skills compatible):**
```yaml
---
name: skill-name
description: What it does. Use when [trigger conditions].
scripts:
  - execution/script1.py
  - execution/script2.py
---
```

**How to find and use the right directive:**
1. List files in `directives/` to see what exists
2. Read only the first 10 lines of candidate files to check the front matter
3. The `scripts` field tells you exactly which execution files to call
4. For simple tasks: just run the listed scripts directly with appropriate args
5. For complex tasks: read the full directive for detailed instructions

**Example workflow:**
- User asks: "Generate some leads"
- You list `directives/` → see `scrape_leads.md`, `lead_scraping.md`, `gmaps_lead_generation.md`
- Read first 10 lines of each → front matter tells you:
  - `scrape_leads.md`: name=`scrape-leads`, scripts=`[scrape_apify.py, enrich_emails.py]`
  - `lead_scraping.md`: name=`lead-scraping`, scripts=`[scrape_apify.py, scrape_apify_parallel.py]`
  - `gmaps_lead_generation.md`: name=`gmaps-leads`, scripts=`[gmaps_lead_pipeline.py]`
- Pick the right one based on user context
- Run the scripts directly, or read full directive if you need detailed process steps

**When creating new directives:** Always include YAML front matter with `name`, `description`, and `scripts` fields.

## Self-annealing loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool
3. Test tool, make sure it works
4. Update directive to include new flow
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or other cloud-based outputs that the user can access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files (dossiers, scraped data, temp exports). Never commit, always regenerated.
- `config/` - OAuth credentials and tokens (Google, Gmail accounts). All credential files live here.
  - `credentials.json`, `token.json` - Primary Google OAuth
  - `credentials_leftclick.json`, `token_leftclick.json` - LeftClick account
  - `token_nicksaraev.json` - Personal account
  - `gmail_accounts.json` - Gmail account registry
- `execution/` - Python scripts (the deterministic tools)
- `directives/` - SOPs in Markdown (the instruction set)
- `.env` - Environment variables and API keys (stays in root - tooling convention)

**Key principle:** Local files are only for processing. Deliverables live in cloud services (Google Sheets, Slides, etc.) where the user can access them. Everything in `.tmp/` can be deleted and regenerated.

## Cloud Webhooks (Modal)

The system supports event-driven execution via Modal webhooks. Each webhook maps to exactly one directive with scoped tool access.

**When user says "add a webhook that...":**
1. Read `directives/add_webhook.md` for complete instructions
2. Create the directive file in `directives/`
3. Add entry to `execution/webhooks.json`
4. Deploy: `modal deploy execution/modal_webhook.py`
5. Test the endpoint

**All webhook activity streams to Slack in real-time.**

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.

Also, use Opus-4.5 for everything while building. It came out a few days ago and is an order of magnitude better than Sonnet and other models. If you can't find it, look it up first.