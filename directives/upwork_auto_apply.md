---
name: upwork-auto-apply
description: Fully automated Upwork job application pipeline. Ingests jobs from Apify and Gmail, pre-filters, generates proposals with HeyGen videos, sends Slack approval requests, and auto-submits via Playwright.
scripts:
  - executions/upwork_sheets_setup.py
  - executions/upwork_apify_scraper.py
  - executions/upwork_gmail_monitor.py
  - executions/upwork_deduplicator.py
  - executions/upwork_prefilter.py
  - executions/upwork_deep_extractor.py
  - executions/upwork_video_script_generator.py
  - executions/upwork_heygen_video.py
  - executions/upwork_deliverable_generator.py
  - executions/upwork_proposal_generator.py
  - executions/upwork_boost_decider.py
  - executions/upwork_slack_approval.py
  - executions/upwork_submitter.py
  - executions/upwork_pipeline_orchestrator.py
  - executions/modal_webhook.py
---

# Upwork Auto-Apply Pipeline

Fully automated Upwork job application system that ingests jobs from multiple sources, pre-filters for relevance, generates personalized proposals with HeyGen videos, sends Slack approval requests, and auto-submits via Playwright.

## Goal

Automate the entire Upwork application process to:
1. Save time on manual job searching and filtering
2. Generate high-quality, personalized proposals at scale
3. Include video cover letters for differentiation
4. Maintain human approval before submission
5. Track all applications in a centralized sheet

## Architecture

```
Apify (2hr) + Gmail (real-time)
           |
           v
    Deduplication (Google Sheet)
           |
           v
    AI Pre-Filter (Sonnet - cheap)
           | score >= 70
           v
    Deep Extraction (attachments, pricing)
           |
           v
    Deliverable Gen (Proposal Doc, PDF, HeyGen Video)
           |
           v
    Boost Decision (AI-based)
           |
           v
    Slack Approval [Approve][Edit][Reject]
           | approved
           v
    Playwright Submission
```

## Inputs

- **Apify Jobs**: Batch scrape every 2 hours via scheduled function
- **Gmail Alerts**: Real-time via Gmail push notifications
- **Manual Jobs**: Ad-hoc via `/upwork/trigger` webhook with job URLs

## Data Storage

### Google Sheet: `Upwork Job Pipeline`

Main tracking sheet with columns:
- `job_id` (primary key), `source`, `status`, `title`, `url`, `description`
- `attachments` (JSON), `budget_type`, `budget_min`, `budget_max`
- `client_country`, `client_spent`, `client_hires`, `payment_verified`
- `fit_score`, `fit_reasoning`, `proposal_doc_url`, `proposal_text`
- `video_url`, `pdf_url`, `boost_decision`, `boost_reasoning`
- `pricing_proposed`, `slack_message_ts`, `approved_at`, `submitted_at`, `error_log`

### Google Sheet: `Upwork Processed IDs`

Deduplication tracking:
- `job_id`, `first_seen`, `source`

## Execution Tools

### 1. Setup Sheets (one-time)
```bash
python executions/upwork_sheets_setup.py
```
Creates both sheets with all required columns.

### 2. Scrape Jobs (scheduled every 2hrs)
```bash
python executions/upwork_apify_scraper.py --limit 100 --days 1
```
Uses Apify actor to fetch new jobs matching AI/automation keywords.

### 3. Check Gmail for Alerts
```bash
python executions/upwork_gmail_monitor.py
```
Monitors inbox for Upwork alert emails, extracts job URLs.

### 4. Deduplicate Jobs
```bash
python executions/upwork_deduplicator.py --jobs jobs.json
```
Filters out already-processed jobs using Processed IDs sheet.

### 5. Pre-Filter for Relevance
```bash
python executions/upwork_prefilter.py --jobs new_jobs.json --min-score 70
```
Uses Claude Sonnet to score jobs 0-100 based on fit. Only jobs >= 70 proceed.

### 6. Deep Extract Job Details
```bash
python executions/upwork_deep_extractor.py --job-url "https://upwork.com/jobs/~123"
```
Uses Playwright to:
- Fetch full job description
- Download and parse attachments (PDF, DOCX)
- Extract budget info, client details
- Capture job screenshot for HeyGen

### 7. Generate Video Script
```bash
python executions/upwork_video_script_generator.py --job job_data.json
```
Creates 200-250 word video cover letter script using Opus 4.5 with extended thinking.

### 8. Create HeyGen Video
```bash
python executions/upwork_heygen_video.py --script script.txt --background job_snapshot.png
```
Generates video with avatar speaking the script, job listing as background.

### 9. Generate Proposal & Deliverables
```bash
python executions/upwork_deliverable_generator.py --job job_data.json
```
Orchestrates creation of:
- Proposal Google Doc
- PDF export
- HeyGen video

### 10. Decide on Boost
```bash
python executions/upwork_boost_decider.py --job job_data.json
```
AI analyzes client quality signals to recommend boost usage.

### 11. Send Slack Approval
```bash
python executions/upwork_slack_approval.py --job job_data.json
```
Posts interactive message with [Approve][Edit][Reject] buttons.

### 12. Submit Application
```bash
python executions/upwork_submitter.py --job-id "~123"
```
Uses Playwright with persistent browser profile to:
- Navigate to apply page
- Fill cover letter
- Attach video and PDF
- Set proposed rate
- Apply boost if recommended
- Submit application

### 13. Run Full Pipeline
```bash
python executions/upwork_pipeline_orchestrator.py --source apify
```
Runs all steps in sequence for a batch of jobs.

## Modal Webhook Endpoints

Deploy: `modal deploy executions/modal_webhook.py`

### POST /upwork/trigger
Trigger pipeline manually or from scheduler.
```json
{"source": "apify|gmail|manual", "jobs": [...]}
```

### POST /upwork/slack-action
Handle Slack button callbacks (approve, edit, reject).

### POST /upwork/gmail-push
Receive Gmail push notifications for new Upwork alerts.

## Status Flow

Jobs progress through these statuses:
1. `new` - Just added to sheet
2. `scoring` - Pre-filter in progress
3. `filtered_out` - Score below threshold
4. `extracting` - Deep extraction in progress
5. `generating` - Deliverables being created
6. `pending_approval` - Slack message sent, awaiting decision
7. `approved` - User clicked Approve
8. `rejected` - User clicked Reject
9. `submitting` - Playwright submission in progress
10. `submitted` - Successfully applied
11. `error` - Something failed (see error_log)

## Cover Letter Format

Must stay above the fold (~35 words max):
```
Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Free walkthrough: [PROPOSAL_DOC_LINK]
```

## Proposal Format

Conversational, first-person format:
```
Hey [name if available].

I spent ~15 minutes putting this together for you. In short, it's how I would create your [paraphrased thing] system end to end.

I've worked with companies like Anthropic and have experience designing similar workflows.

Here's my step-by-step approach:

## My proposed approach
[4-6 numbered steps with reasoning]

## What you'll get
[2-3 concrete deliverables]

## Timeline
[Realistic estimate, conversational tone]
```

## Video Script Structure (60-90 seconds)

1. **Opening** (10-15 sec): Reference specific job details + relevant results
2. **Experience** (20-30 sec): 1-2 portfolio examples matching requirements
3. **Approach** (15-20 sec): How you'd tackle the project with specific tools
4. **Closing** (10-15 sec): Invite to 10-min call, state availability

Rules:
- 200-250 words max
- NO emojis
- First 2 sentences = most impactful
- Only mention industry if job specifies one

## Environment Variables

Required in `.env`:
```
ANTHROPIC_API_KEY=xxx
HEYGEN_API_KEY=xxx
HEYGEN_AVATAR_ID=xxx
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_SIGNING_SECRET=xxx
SLACK_APPROVAL_CHANNEL=C0123456789
UPWORK_PIPELINE_SHEET_ID=xxx
UPWORK_PROCESSED_IDS_SHEET_ID=xxx
PREFILTER_MIN_SCORE=70
```

## Cost Per Job

| Component | Cost |
|-----------|------|
| Pre-filter (Sonnet) | ~$0.003 |
| Proposal (Opus 4.5) | ~$0.15 |
| HeyGen video | ~$0.20 |
| **Total** | **~$0.35-0.40** |

Pre-filtering at 70+ score means only ~20-30% of jobs reach full processing.

## Edge Cases

- **No jobs found**: Increase Apify limit or broaden keywords
- **Anthropic rate limit**: Reduce parallel workers, apply exponential backoff
- **Google Docs API quota**: Max ~100 doc creates/day on free tier
- **HeyGen video timeout**: 5 minute max poll time, then error
- **Upwork login expired**: Re-authenticate browser profile manually
- **Attachment too large**: Skip attachment, note in error_log
- **Duplicate from different source**: Keep original, log duplicate attempt

## Error Handling

- **API failures**: Retry 4x with exponential backoff (1.5s, 3s, 6s, 12s)
- **Playwright errors**: Screenshot page, log HTML, update error_log
- **Sheet errors**: Batch updates with retry, semaphore for concurrent writes
- **Pipeline failures**: Continue with next job, mark failed job as error

## Monitoring

- All webhook activity streams to Slack in real-time
- Check Modal logs: `modal logs claude-orchestrator`
- Review error_log column in Pipeline sheet for failures
- Track conversion rates: jobs_processed / jobs_submitted

## Notes

- Opus 4.5 model ID: `claude-opus-4-5-20251101`
- Extended thinking budget: 3000 tokens for video scripts, 8000 for proposals
- Google Docs API needs serialization via `threading.Semaphore(1)`
- Playwright uses persistent browser profile at `~/.upwork_browser_profile`
- Job URL format: `https://www.upwork.com/jobs/~{id}`
- Apply URL format: `https://www.upwork.com/nx/proposals/job/~{id}/apply/`
