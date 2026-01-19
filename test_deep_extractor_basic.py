#!/usr/bin/env python3
"""Basic tests for upwork_deep_extractor.py"""
import sys
sys.path.insert(0, '.')

from executions.upwork_deep_extractor import (
    extract_job_id_from_url,
    parse_budget,
    parse_client_spent,
    parse_hires_count,
    BudgetInfo,
    ClientInfo,
    ExtractedJob,
    Attachment
)

def test_all():
    passed = 0
    failed = 0

    # Test job ID extraction
    print("Testing job ID extraction...")
    try:
        url1 = 'https://www.upwork.com/jobs/~01abc123def456'
        assert extract_job_id_from_url(url1) == '~01abc123def456', 'Job ID extraction failed'
        print('  Standard URL: PASS')
        passed += 1
    except Exception as e:
        print(f'  Standard URL: FAIL - {e}')
        failed += 1

    try:
        url2 = 'https://www.upwork.com/nx/proposals/job/~01abc123/apply/'
        assert extract_job_id_from_url(url2) == '~01abc123', 'Apply URL extraction failed'
        print('  Apply URL: PASS')
        passed += 1
    except Exception as e:
        print(f'  Apply URL: FAIL - {e}')
        failed += 1

    # Test budget parsing
    print("Testing budget parsing...")
    try:
        budget = parse_budget('Fixed-price: $500')
        assert budget.budget_type == 'fixed', f'Expected fixed, got {budget.budget_type}'
        assert budget.budget_min == 500, f'Expected 500, got {budget.budget_min}'
        print('  Fixed $500: PASS')
        passed += 1
    except Exception as e:
        print(f'  Fixed $500: FAIL - {e}')
        failed += 1

    try:
        budget = parse_budget('$25.00-$50.00/hr')
        assert budget.budget_type == 'hourly', f'Expected hourly, got {budget.budget_type}'
        assert budget.budget_min == 25.00, f'Expected 25, got {budget.budget_min}'
        assert budget.budget_max == 50.00, f'Expected 50, got {budget.budget_max}'
        print('  Hourly $25-$50: PASS')
        passed += 1
    except Exception as e:
        print(f'  Hourly $25-$50: FAIL - {e}')
        failed += 1

    try:
        budget = parse_budget('')
        assert budget.budget_type == 'unknown', f'Expected unknown, got {budget.budget_type}'
        assert budget.budget_min is None, 'Expected None for min'
        print('  Empty budget: PASS')
        passed += 1
    except Exception as e:
        print(f'  Empty budget: FAIL - {e}')
        failed += 1

    # Test client spent parsing
    print("Testing client spent parsing...")
    try:
        raw, num = parse_client_spent('$10K')
        assert num == 10000, f'Expected 10000, got {num}'
        print('  $10K: PASS')
        passed += 1
    except Exception as e:
        print(f'  $10K: FAIL - {e}')
        failed += 1

    try:
        raw, num = parse_client_spent('$1.5M')
        assert num == 1500000, f'Expected 1500000, got {num}'
        print('  $1.5M: PASS')
        passed += 1
    except Exception as e:
        print(f'  $1.5M: FAIL - {e}')
        failed += 1

    # Test hires count parsing
    print("Testing hires count parsing...")
    try:
        result = parse_hires_count('12 hires')
        assert result == 12, f'Expected 12, got {result}'
        print('  12 hires: PASS')
        passed += 1
    except Exception as e:
        print(f'  12 hires: FAIL - {e}')
        failed += 1

    # Test dataclass creation
    print("Testing dataclass creation...")
    try:
        job = ExtractedJob(
            job_id='~123',
            url='https://upwork.com/jobs/~123',
            title='Test Job',
            budget=BudgetInfo(budget_type='fixed', budget_min=500, budget_max=500),
            client=ClientInfo(country='US', payment_verified=True),
            attachments=[Attachment(filename='requirements.pdf')]
        )
        assert job.job_id == '~123'
        assert job.budget.budget_type == 'fixed'
        assert job.client.payment_verified == True
        assert len(job.attachments) == 1
        print('  ExtractedJob creation: PASS')
        passed += 1
    except Exception as e:
        print(f'  ExtractedJob creation: FAIL - {e}')
        failed += 1

    try:
        d = job.to_dict()
        assert d['job_id'] == '~123'
        assert d['budget']['budget_type'] == 'fixed'
        print('  to_dict(): PASS')
        passed += 1
    except Exception as e:
        print(f'  to_dict(): FAIL - {e}')
        failed += 1

    try:
        row = job.to_sheet_row()
        assert row['payment_verified'] == True
        print('  to_sheet_row(): PASS')
        passed += 1
    except Exception as e:
        print(f'  to_sheet_row(): FAIL - {e}')
        failed += 1

    print()
    print('='*50)
    print(f'Results: {passed} passed, {failed} failed')
    print('='*50)

    return failed == 0

if __name__ == '__main__':
    success = test_all()
    sys.exit(0 if success else 1)
