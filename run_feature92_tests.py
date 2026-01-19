#!/usr/bin/env python3
"""Test runner for Feature #92: Contact name discovery."""

import sys
sys.path.insert(0, 'executions')

from upwork_deliverable_generator import (
    discover_contact_name,
    enrich_job_with_contact,
    JobData,
    ContactDiscoveryResult,
    format_greeting
)

def test_thanks_john():
    """Test 1: Thanks, John signature."""
    desc = """
    Looking for an AI automation expert to help with our workflow.

    Thanks, John
    """
    result = discover_contact_name(desc)
    assert result.contact_name == 'John', f'Expected John, got {result.contact_name}'
    assert result.contact_confidence == 'high', f'Expected high, got {result.contact_confidence}'
    assert result.source == 'signature', f'Expected signature, got {result.source}'
    print('Test 1: Thanks, John - PASS')
    return True

def test_best_sarah():
    """Test 2: Best, Sarah."""
    desc = 'Need help with automation project.\n\nBest, Sarah'
    result = discover_contact_name(desc)
    assert result.contact_name == 'Sarah', f'Expected Sarah, got {result.contact_name}'
    assert result.contact_confidence == 'high'
    print('Test 2: Best, Sarah - PASS')
    return True

def test_my_name_is():
    """Test 3: My name is David."""
    desc = 'Hi, my name is David and I need help with my project.'
    result = discover_contact_name(desc)
    assert result.contact_name == 'David', f'Expected David, got {result.contact_name}'
    assert result.source == 'introduction', f'Expected introduction, got {result.source}'
    print('Test 3: My name is David - PASS')
    return True

def test_name_at_end():
    """Test 4: Name at end (medium confidence)."""
    desc = """
    Need an expert for my project.

    Robert
    """
    result = discover_contact_name(desc)
    assert result.contact_name == 'Robert', f'Expected Robert, got {result.contact_name}'
    assert result.contact_confidence == 'medium', f'Expected medium, got {result.contact_confidence}'
    print('Test 4: Name at end Robert - PASS')
    return True

def test_no_name():
    """Test 5: No name found."""
    desc = 'Looking for Python developer with API experience.'
    result = discover_contact_name(desc)
    assert result.contact_name is None, f'Expected None, got {result.contact_name}'
    assert result.contact_confidence == 'low'
    print('Test 5: No name found - PASS')
    return True

def test_enrich_job():
    """Test 6: enrich_job_with_contact."""
    job = JobData(
        job_id='test123',
        title='Python Developer',
        description='Need help with project.\n\nThanks, Emily',
        url='https://upwork.com/jobs/~test123'
    )
    enriched = enrich_job_with_contact(job)
    assert enriched.contact_name == 'Emily', f'Expected Emily, got {enriched.contact_name}'
    assert enriched.contact_confidence == 'high', f'Expected high, got {enriched.contact_confidence}'
    print('Test 6: enrich_job_with_contact - PASS')
    return True

def test_format_greeting_high():
    """Test 7: format_greeting high confidence."""
    greeting = format_greeting('John', 'high')
    assert greeting == 'Hey John', f'Expected Hey John, got {greeting}'
    print('Test 7: format_greeting high - PASS')
    return True

def test_format_greeting_medium():
    """Test 8: format_greeting medium confidence."""
    greeting = format_greeting('Robert', 'medium')
    expected = 'Hey Robert (if I have the right person)'
    assert greeting == expected, f'Unexpected: {greeting}'
    print('Test 8: format_greeting medium - PASS')
    return True

def test_regards_mike():
    """Test 9: Regards, Mike."""
    desc = 'Looking for Python developer.\n\nRegards, Mike'
    result = discover_contact_name(desc)
    assert result.contact_name == 'Mike', f'Expected Mike, got {result.contact_name}'
    print('Test 9: Regards, Mike - PASS')
    return True

def test_im_lisa():
    """Test 10: I'm Lisa."""
    desc = "I'm Lisa and I run a small business."
    result = discover_contact_name(desc)
    assert result.contact_name == 'Lisa', f'Expected Lisa, got {result.contact_name}'
    print("Test 10: I'm Lisa - PASS")
    return True

def test_dash_signature():
    """Test 11: Thanks - Alex."""
    desc = "Need automation help.\n\nThanks - Alex"
    result = discover_contact_name(desc)
    assert result.contact_name == 'Alex', f'Expected Alex, got {result.contact_name}'
    print('Test 11: Thanks - Alex - PASS')
    return True

def test_case_insensitive():
    """Test 12: Case insensitive THANKS, Jennifer."""
    desc = "Looking for developer.\n\nTHANKS, Jennifer"
    result = discover_contact_name(desc)
    assert result.contact_name == 'Jennifer', f'Expected Jennifer, got {result.contact_name}'
    print('Test 12: THANKS, Jennifer - PASS')
    return True

def test_excludes_false_positives():
    """Test 13: Excludes false positives."""
    desc = "Thanks for reading this job post.\n\nBest"
    result = discover_contact_name(desc)
    assert result.contact_name is None, f'Expected None, got {result.contact_name}'
    print('Test 13: Excludes false positives - PASS')
    return True

def test_preserves_existing():
    """Test 14: Preserves existing contact."""
    job = JobData(
        job_id='test123',
        title='Python Developer',
        description='Need help.\n\nThanks, Emily',
        url='https://upwork.com/jobs/~test123',
        contact_name='ManuallySet',
        contact_confidence='high'
    )
    enriched = enrich_job_with_contact(job)
    assert enriched.contact_name == 'ManuallySet', f'Should preserve: {enriched.contact_name}'
    print('Test 14: Preserves existing contact - PASS')
    return True

def test_to_dict():
    """Test 15: ContactDiscoveryResult to_dict."""
    result = ContactDiscoveryResult(
        contact_name='John',
        contact_confidence='high',
        source='signature'
    )
    d = result.to_dict()
    assert d['contact_name'] == 'John'
    assert d['contact_confidence'] == 'high'
    assert d['source'] == 'signature'
    print('Test 15: ContactDiscoveryResult to_dict - PASS')
    return True

def main():
    """Run all Feature #92 tests."""
    tests = [
        test_thanks_john,
        test_best_sarah,
        test_my_name_is,
        test_name_at_end,
        test_no_name,
        test_enrich_job,
        test_format_greeting_high,
        test_format_greeting_medium,
        test_regards_mike,
        test_im_lisa,
        test_dash_signature,
        test_case_insensitive,
        test_excludes_false_positives,
        test_preserves_existing,
        test_to_dict,
    ]

    passed = 0
    failed = 0

    print('\n' + '='*60)
    print('Feature #92: Contact name discovery from job description')
    print('='*60 + '\n')

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f'{test.__name__}: FAILED - {e}')
            failed += 1
        except Exception as e:
            print(f'{test.__name__}: ERROR - {e}')
            failed += 1

    print('\n' + '-'*60)
    print(f'Results: {passed} passed, {failed} failed')
    print('-'*60)

    if failed == 0:
        print('\n[Feature #92] ALL TESTS PASSED!')
        print('  - Contact name discovery works from signatures like "Thanks, John"')
        print('  - Returns contact_name="John" and contact_confidence="high"')
        print('  - Also supports introduction patterns and medium-confidence detection')
        return 0
    else:
        print('\nSome tests failed.')
        return 1

if __name__ == '__main__':
    sys.exit(main())
