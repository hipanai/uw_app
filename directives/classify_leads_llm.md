---
name: classify-leads
description: Use Claude to classify leads based on custom criteria (product vs service, high-ticket vs low-ticket). Use when filtering leads by business model.
scripts:
  - execution/classify_leads_llm.py
---

# LLM-Based Lead Classification

## Goal
Use AI (Claude Sonnet 4.5) to accurately classify scraped leads based on custom criteria. This is critical for **harder niches** where simple keyword matching fails (e.g., distinguishing product SaaS from IT consulting, or filtering specific business models).

## When to Use This
**Harder Niches** - Use LLM classification when:
- Simple industries like "realtors" or "dentists" → NO, keyword matching works fine
- Complex distinctions like "product SaaS vs agencies" → YES, use LLM
- Ambiguous categories like "high-ticket vs low-ticket" → YES, use LLM
- Business model filtering (subscription vs one-time, B2B vs B2C) → YES, use LLM

**Rule of thumb**: If you can't reliably tell from company name/industry alone, use LLM classification.

## Inputs
- **Input file**: JSON file with scraped leads (usually from `.tmp/`)
- **Classification type**: Pre-defined (e.g., `product_saas`) or custom
- **Confidence level**: high, medium (default), or low

## Tools/Scripts
- Script: `execution/classify_leads_llm.py`
- API: Anthropic Message Batches API (parallel processing)
- Model: Claude Sonnet 4.5 (`claude-sonnet-4-20250514`)
- Dependencies: `ANTHROPIC_API_KEY` in `.env`

## Process

### 1. Run Classification

**For Product SaaS filtering** (most common use case):
```bash
python3 execution/classify_leads_llm.py input_file.json \
  --classification_type product_saas \
  --output .tmp/classified_leads.json
```

**For custom classification**:
```bash
python3 execution/classify_leads_llm.py input_file.json \
  --classification_type custom \
  --custom_prompt "Classify as HIGH_TICKET, LOW_TICKET, or UNCLEAR based on: {desc}" \
  --primary_class high_ticket \
  --exclude_class low_ticket \
  --output .tmp/classified_leads.json
```

**Confidence levels**:
- `--min_confidence high`: Only includes primary class (strictest filter)
- `--min_confidence medium`: Includes primary + unclear (default, balanced)
- `--min_confidence low`: Excludes only the exclude_class (loosest filter)

### 2. Upload to Google Sheet
```bash
python3 execution/update_sheet.py .tmp/classified_leads.json \
  --sheet_name "Classified Leads"
```

## Performance
- **Speed**: ~2 minutes for 3,000 leads (parallel batch processing)
- **Cost**: ~$0.30 per 1,000 leads (20 tokens/lead × $0.015/1K tokens)
- **Accuracy**: 95%+ for clear cases, ~40-50% "unclear" for ambiguous data

## Outputs
- **JSON file**: `.tmp/classified_leads.json` (intermediate, includes `_classification` field)
- **Google Sheet**: Final deliverable with filtered, classified leads

## Edge Cases
- **All unclear**: If >80% unclear, the data quality is poor. Consider:
  - Scraping with different keywords to get better descriptions
  - Using a custom prompt with more specific indicators
  - Manual review of sample leads
- **API rate limits**: Script auto-polls batch status, no action needed
- **Classification disagreement**: If unsure, classification defaults to "unclear" (included by default in medium confidence)

## Example: Product SaaS Classification

**Input**: 3,000 companies scraped with "software" keyword
**Command**:
```bash
python3 execution/classify_leads_llm.py .tmp/scraped_leads.json \
  --classification_type product_saas \
  --output .tmp/product_saas_leads.json
```

**Expected Output**:
```
Total companies: 3000
Product SaaS: 1213 (40.4%)
Services/Agencies: 1626 (54.2%)
Unclear: 161 (5.4%)

Filtering: MEDIUM confidence (product_saas + unclear)
Final count: 1374 companies
```

**Result**: 1,374 leads (1,213 confirmed + 161 unclear) saved to output file.

## Classification Criteria (Product SaaS)

The default `product_saas` classifier uses these indicators:

**PRODUCT_SAAS** = Software products/platforms (SaaS, licenses, apps)
- Indicators: "our platform", "subscription", "sign up", "dashboard", "API access", "pricing plans"

**SERVICE** = Agencies, consultancies, custom dev shops
- Indicators: "we help companies", "consulting", "agency", "custom development", "professional services"

**UNCLEAR** = Not enough information to determine
- Used when company description is vague or missing

## Notes
- Default behavior includes "unclear" classifications (medium confidence)
- Use high confidence only when you need maximum precision
- The `_classification` field is added to each company record
- Classification can be customized for any use case using `--custom_prompt`
