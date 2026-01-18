---
name: instantly-campaigns
description: Create email campaigns in Instantly based on client description and offers. Use when setting up cold email campaigns.
scripts:
  - execution/instantly_create_campaigns.py
---

# Instantly Campaign Creation

Create three email campaigns in Instantly based on a client description and offers.

## Inputs

1. **Client Description**: High-level info about the client (company name, industry, target audience, value proposition)
2. **Offers** (optional): List of 3 offers. If not provided, generate from client description.

## Process

### Step 1: Load Examples
- Read `.tmp/instantly_campaign_examples/campaigns.md` for inspiration
- These examples demonstrate the personalization + social proof + offer structure

### Step 2: Generate Campaigns
Call `execution/instantly_create_campaigns.py` with:
```bash
python3 execution/instantly_create_campaigns.py \
  --client_name "ClientName" \
  --client_description "Description of the client..." \
  --offers "Offer 1|Offer 2|Offer 3" \
  --target_audience "Who we're emailing" \
  --social_proof "Credentials/results to mention"
```

### Step 3: Review Output
The script will:
1. Generate 3 campaigns (one per offer)
2. Each campaign has 2-3 email steps
3. First step has 2 variants (A/B split test)
4. Create campaigns in Instantly via API

## Campaign Structure

Each campaign follows this format:

### Email 1 (Step 1) - Two Variants
**Variant A & B** - Different approaches, same offer:
- Personalization hook (`{{icebreaker}}` or custom opener)
- Social proof (credentials, results, experience)
- Offer (clear value proposition with low barrier)
- Soft CTA

### Email 2 (Step 2) - Follow-up
- Brief, friendly bump
- Reference original email
- Restate value
- Clear CTA

### Email 3 (Step 3) - Breakup
- Short, direct
- Last chance framing
- Simple yes/no ask

## Available Variables

From Instantly's lead data:
- `{{firstName}}` - Lead's first name
- `{{lastName}}` - Lead's last name
- `{{email}}` - Lead's email
- `{{companyName}}` - Lead's company name
- `{{casualCompanyName}}` - Informal company name
- `{{icebreaker}}` - AI-generated icebreaker
- `{{sendingAccountFirstName}}` - Sender's first name

## Edge Cases

- **No offers provided**: Generate 3 distinct offers based on client description
- **API errors**: Script will retry once, then fail with detailed error
- **Rate limits**: Script handles rate limits with exponential backoff
- **Missing API key**: Script exits early with helpful error (before spending Claude tokens)

## Environment

Requires in `.env`:
```
INSTANTLY_API_KEY=your_api_key_here
ANTHROPIC_API_KEY=your_anthropic_key
```

**Getting the Instantly API Key:**
1. Go to https://app.instantly.ai/app/settings/integrations
2. Generate an API v2 key (requires Growth plan or above)
3. Add to `.env` file

**Note:** Script validates API key before generating campaigns to avoid wasting tokens.

**Timezone:** Uses `America/Chicago` by default. Must match Instantly's allowed IANA values (not all are supported - e.g., `America/New_York` fails but `America/Chicago` works).

**HTML formatting:** Instantly strips plain text outside HTML tags. Script wraps paragraphs in `<p>` tags and converts single line breaks to `<br>`.

## Example Usage

```bash
# Full specification
python3 execution/instantly_create_campaigns.py \
  --client_name "LeftClick" \
  --client_description "AI automation agency helping businesses automate workflows" \
  --offers "Free workflow audit|AI agent demo|Revenue share partnership" \
  --target_audience "Agency owners, consultants, service businesses" \
  --social_proof "Built AI systems generating $1M+ in client revenue"

# Minimal (will generate offers)
python3 execution/instantly_create_campaigns.py \
  --client_name "LeftClick" \
  --client_description "AI automation agency helping businesses automate workflows"

# Dry run (test without creating in Instantly)
python3 execution/instantly_create_campaigns.py \
  --client_name "Test" \
  --client_description "Test company" \
  --dry_run
```

## Output

The script prints JSON with:
```json
{
  "status": "success",
  "campaigns_created": 3,
  "campaign_ids": ["id1", "id2", "id3"],
  "campaign_names": ["Campaign 1", "Campaign 2", "Campaign 3"]
}
```

## API Learnings (Self-Annealed)

These were discovered during development and are handled automatically by the script:

1. **Schedule requires `name` field**: Each schedule object must have a `name` property
2. **Timezone enum is restrictive**: Not all IANA timezones work (e.g., `America/New_York` fails, `America/Chicago` works)
3. **HTML stripping**: Instantly strips all plain text outside HTML tags - must wrap content in `<p>`, `<div>`, or `<span>` tags
4. **Model IDs**: Uses `claude-opus-4-5-20251101` for campaign generation (thinking enabled)
5. **Campaign defaults**: Weekday 9-5 schedule, stop on reply, link/open tracking enabled
