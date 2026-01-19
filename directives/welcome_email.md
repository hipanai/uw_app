---
name: welcome-email
description: Send welcome email to new client after payment with kickoff call link. Use for new client onboarding.
scripts:
  - execution/welcome_client_emails.py
---

# Welcome Email - New Client

Send welcome email to new client after payment with kickoff call link.

## Trigger

This workflow is triggered when a new client completes payment (Stripe webhook or manual trigger).

## Inputs

Required:
- `client_name`: Client's full name (e.g., "John Smith")
- `client_email`: Client's email address
- `company_name`: Client's company name (e.g., "Acme Plumbing")

Optional:
- `kickoff_link`: Calendly or meeting link (default: your standard kickoff link)
- `cc_emails`: Additional team members to CC (comma-separated)

## Process

### Step 1: Generate Welcome Email

Send email using the `send_email` tool:

**To:** `{client_email}`
**CC:** `nick@leftclick.ai` + any additional `cc_emails`
**Subject:** "Welcome to LeftClick - Let's Get Started, {client_name}!"

**Body:**
```
Hey {client_name},

Welcome to LeftClick! We're excited to help {company_name} scale with cold email automation.

🎯 NEXT STEP: Kickoff Call

Let's schedule a 30-minute kickoff call to understand your:
→ Target audience
→ Service offerings
→ Unique value proposition
→ Goals and expectations

Book your kickoff here:
{kickoff_link}

During the call, we'll map out your campaigns and get everything set up. After the call, your system will be live within 24-48 hours.

🛠️ WHAT TO EXPECT

After our kickoff, we'll:
1. Generate 50+ qualified leads for your target market
2. Create 3 split-tested email campaigns
3. Set up intelligent auto-replies
4. Start sending within 24 hours

You'll be able to review everything before we go live.

📞 Questions before the call?

Just reply to this email - I'm here to help.

Looking forward to our kickoff!

- Nick @ LeftClick
nick@leftclick.ai
```

### Step 2: Log to Tracking Sheet (Optional)

If you maintain a client tracking sheet, add a row with:
- Client name
- Email
- Company
- Kickoff scheduled: No
- Status: Awaiting kickoff
- Date added: Today

## Output

Return confirmation:
```json
{
  "status": "success",
  "email_sent": true,
  "client_name": "...",
  "client_email": "...",
  "next_step": "Client should book kickoff call"
}
```

## Error Handling

- If email fails: Retry once, then notify team via Slack
- If no kickoff link provided: Use default Calendly link

## Notes

- Keep email warm and friendly, not corporate
- Emphasize quick timeline (24-48 hours after kickoff)
- Make booking the call frictionless
- Set expectation that they'll review before going live

## Testing

Test payload:
```json
{
  "client_name": "John Smith",
  "client_email": "john@example.com",
  "company_name": "Test Plumbing Co",
  "kickoff_link": "https://calendly.com/your-link"
}
```
