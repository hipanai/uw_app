---
name: onboarding-post-kickoff
description: Automated post-kickoff onboarding - generate leads, create campaigns, set up auto-reply. Use after client kickoff calls.
scripts:
  - execution/onboarding_post_kickoff.py
---

# Post-Kickoff Client Onboarding

Automated onboarding workflow that runs after kickoff call. Generates leads, creates campaigns, and sets up auto-reply system.

## Trigger

This workflow is triggered after the kickoff call with the client, where you've gathered information about their service, target audience, and offers.

## Inputs

Required from kickoff call:
- `client_name`: Client's company name (e.g., "Acme Plumbing")
- `client_email`: Primary contact email
- `service_type`: What service they provide (e.g., "plumbing", "roofing", "hvac")
- `target_location`: Geographic area to target (e.g., "Austin TX", "Miami FL")
- `offers`: Three distinct offers to test (pipe-separated, e.g., "Free inspection|10% off first service|Emergency 24/7 response")
- `target_audience`: Who they're targeting (e.g., "property managers", "homeowners", "commercial building owners")
- `social_proof`: Key credentials or results to mention (e.g., "15 years in business, 500+ jobs completed")

Optional:
- `lead_limit`: Number of leads to generate (default: 500)
- `value_proposition`: Additional context about their unique selling points
- `email_account`: Which Instantly account to send from (default: main account)

## Process

### Step 1: Generate Lead Search Query
Construct Google Maps search query from inputs:
- Format: "{service_type} in {target_location}"
- Example: "plumbers in Austin TX"

### Step 2: Scrape and Enrich Leads
Call the lead generation script:
```bash
python3 execution/gmaps_lead_pipeline.py \
  --search "{service_type} in {target_location}" \
  --limit {lead_limit} \
  --sheet-name "{client_name} - Leads" \
  --workers 5
```

Expected output:
- Google Sheet URL with enriched leads
- Lead count
- Enrichment success rate

### Step 3: Casualize Company Names (AMF Processing)
Call casualization script on the generated sheet:
```bash
python3 execution/casualize_company_names_batch.py \
  --sheet-url "{sheet_url_from_step_2}" \
  --column "business_name" \
  --output-column "casualCompanyName"
```

This converts:
- "ABC Plumbing Services LLC" → "ABC Plumbing"
- "John's HVAC & Heating Solutions Inc" → "John's HVAC"

### Step 4: Create Instantly Campaigns
Call campaign creation script with three offers:
```bash
python3 execution/instantly_create_campaigns.py \
  --client_name "{client_name}" \
  --client_description "We help {client_name} generate qualified leads through personalized cold email outreach for their {service_type} services in {target_location}" \
  --offers "{offers}" \
  --target_audience "{target_audience}" \
  --social_proof "{social_proof}"
```

Expected output:
- 3 campaign IDs
- 3 campaign names
- Campaign URLs in Instantly

### Step 5: Upload Leads to Campaigns
Upload the leads from Google Sheet to the created campaigns:
- Distribute leads evenly across the 3 campaigns
- Use Instantly API to batch upload leads
- Each lead should include: email, first_name, last_name, company_name, casual_company_name

**Note:** This step requires valid Instantly API credentials. Leads are distributed to test each offer variant with different prospects.

### Step 6: Add Knowledge Base Entry for Auto-Reply
Add entry to the auto-reply knowledge base sheet:
- Spreadsheet ID: `1QS7MYDm6RUTzzTWoMfX-0G9NzT5EoE2KiCE7iR1DBLM`
- Sheet: `Sheet1`
- New row with:
  - ID: `{client_name}` (matching campaign ID pattern)
  - Campaign Name: `{client_name} | {service_type}`
  - Knowledge Base: Auto-generated context about their service
  - Reply Examples: Auto-generated example replies in their tone

Knowledge base content should include:
- Service type and location
- Three offers being tested
- Social proof / credentials
- How to book/contact
- Pricing structure (if provided)

### Step 7: Send Summary Email
Send completion email to client and team with:

**To:** `{client_email}` (client) + `nick@leftclick.ai` (CC)
**Subject:** "LeftClick Setup Complete - {client_name}"

**Body:**
```
Hey {client_first_name},

Your cold email system is live! Here's what we set up:

CAMPAIGNS (3 offers being split-tested):
1. {campaign_1_name}: {offer_1}
   → https://app.instantly.ai/app/campaign/{campaign_1_id}/leads
   → {leads_in_campaign_1} leads loaded

2. {campaign_2_name}: {offer_2}
   → https://app.instantly.ai/app/campaign/{campaign_2_id}/leads
   → {leads_in_campaign_2} leads loaded

3. {campaign_3_name}: {offer_3}
   → https://app.instantly.ai/app/campaign/{campaign_3_id}/leads
   → {leads_in_campaign_3} leads loaded

LEADS:
→ {lead_count} qualified {service_type} leads in {target_location}
→ Spreadsheet: {sheet_url}
→ All leads uploaded and ready to send

AUTO-REPLY:
→ Configured for all campaign IDs
→ Will respond intelligently using your offers and credentials
→ You can review/adjust the knowledge base here:
  https://docs.google.com/spreadsheets/d/1QS7MYDm6RUTzzTWoMfX-0G9NzT5EoE2KiCE7iR1DBLM/edit

NEXT STEPS:
1. Campaigns will start sending within 24 hours (you can pause/adjust in Instantly)
2. Auto-replies handle all responses automatically
3. Monitor results in your Instantly dashboard

Questions? Just reply to this email.

- Nick @ LeftClick
```

## Output

Return structured summary:
```json
{
  "status": "success",
  "client_name": "...",
  "sheet_url": "...",
  "lead_count": 50,
  "campaigns": [
    {"id": "...", "name": "...", "offer": "...", "url": "...", "leads_count": 17},
    {"id": "...", "name": "...", "offer": "...", "url": "...", "leads_count": 17},
    {"id": "...", "name": "...", "offer": "...", "url": "...", "leads_count": 16}
  ],
  "leads_uploaded": true,
  "knowledge_base_updated": true,
  "summary_email_sent": true
}
```

## Error Handling

### Lead Generation Fails
- If < 10 leads found: Warn but continue (may need different search query)
- If 0 leads found: Error and stop (bad search query or location)
- If API errors: Retry once, then notify user to run manually

### Campaign Creation Fails
- If Instantly API error: Capture error, send to user for manual fix
- If missing API key: Error immediately with instructions

### Lead Upload Fails
- If Instantly API authentication error: Skip upload, note in summary email that leads need manual upload
- If partial upload succeeds: Report count of successful uploads, continue workflow
- Non-critical: Campaign creation succeeded, leads can be uploaded manually

### Sheet/Email Failures
- Non-critical: Log error but complete workflow
- Send summary to Slack if email fails

## Notes

- **Parallelization:** Lead scraping uses 5 workers by default (can be adjusted)
- **Timing:** Full workflow takes ~10-15 minutes for 50 leads
- **Lead Quality:** AMF enrichment + casualization improves email personalization
- **Campaign Defaults:** Weekday 9-5, stop on reply, link tracking enabled
- **Knowledge Base:** Must match campaign ID for auto-reply to work
- **Column Naming:** The casualization script supports both `email`/`emails` and `company_name`/`business_name` columns
- **B2B vs Local Services:** The GMaps pipeline works best for local services. For B2B targeting (professional services firms, etc.), consider using LinkedIn Sales Navigator or Apollo for lead sourcing instead
- **Lead Upload:** No automated upload script exists yet - leads must be manually uploaded to Instantly campaigns

## Testing

Test with minimal leads:
```json
{
  "client_name": "TestPlumbing",
  "client_email": "test@example.com",
  "service_type": "plumbers",
  "target_location": "Austin TX",
  "lead_limit": 5,
  "offers": "Free inspection|10% off|24/7 emergency",
  "target_audience": "homeowners",
  "social_proof": "15 years experience"
}
```

Expected runtime: ~3-5 minutes with 5 leads
