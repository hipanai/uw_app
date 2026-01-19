#!/usr/bin/env python3
"""Test runner for Feature #91 tests."""

import sys
sys.path.insert(0, 'executions')

from upwork_deliverable_generator import JobData, generate_proposal_content, generate_deliverables

def run_tests():
    """Run Feature #91 tests."""
    all_passed = True

    # Test 1: Check proposal has all required sections
    print("\n" + "="*60)
    print("Test 1: Proposal has all required sections")
    print("="*60)

    job = JobData(
        job_id='test91',
        title='AI Automation Project',
        description='Need automation',
        url='https://upwork.com/jobs/test91',
        skills=['Python'],
    )
    proposal = generate_proposal_content(job, mock=True)

    has_approach = 'My proposed approach' in proposal.full_text
    has_deliverables = "What you'll get" in proposal.full_text
    has_timeline = 'Timeline' in proposal.full_text

    print(f"  'My proposed approach': {has_approach}")
    print(f"  'What you'll get': {has_deliverables}")
    print(f"  'Timeline': {has_timeline}")

    if has_approach and has_deliverables and has_timeline:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Test 2: High confidence name greeting
    print("\n" + "="*60)
    print("Test 2: High confidence name greeting")
    print("="*60)

    job2 = JobData(
        job_id='test91b',
        title='Test',
        description='Test',
        url='https://upwork.com/jobs/test91b',
        contact_name='John',
        contact_confidence='high'
    )
    proposal2 = generate_proposal_content(job2, mock=True)

    has_name = 'John' in proposal2.greeting
    not_hedged = 'if I have' not in proposal2.greeting

    print(f"  Greeting: {proposal2.greeting}")
    print(f"  Contains 'John': {has_name}")
    print(f"  Not hedged: {not_hedged}")

    if has_name and not_hedged:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Test 3: Medium confidence name greeting (hedged)
    print("\n" + "="*60)
    print("Test 3: Medium confidence name greeting (hedged)")
    print("="*60)

    job3 = JobData(
        job_id='test91c',
        title='Test',
        description='Test',
        url='https://upwork.com/jobs/test91c',
        contact_name='Sarah',
        contact_confidence='medium'
    )
    proposal3 = generate_proposal_content(job3, mock=True)

    has_name = 'Sarah' in proposal3.greeting
    is_hedged = 'if I have' in proposal3.greeting

    print(f"  Greeting: {proposal3.greeting}")
    print(f"  Contains 'Sarah': {has_name}")
    print(f"  Is hedged: {is_hedged}")

    if has_name and is_hedged:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Test 4: No contact name greeting
    print("\n" + "="*60)
    print("Test 4: No contact name greeting")
    print("="*60)

    job4 = JobData(
        job_id='test91d',
        title='Test',
        description='Test',
        url='https://upwork.com/jobs/test91d',
    )
    proposal4 = generate_proposal_content(job4, mock=True)

    is_hey = proposal4.greeting == 'Hey'

    print(f"  Greeting: {proposal4.greeting}")
    print(f"  Is 'Hey': {is_hey}")

    if is_hey:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Test 5: Full deliverables with all sections
    print("\n" + "="*60)
    print("Test 5: Full deliverables generation with sections")
    print("="*60)

    job5 = JobData(
        job_id='test91e',
        title='AI Workflow Project',
        description='Build AI workflow',
        url='https://upwork.com/jobs/test91e',
        skills=['AI', 'Python'],
        contact_name='Alex',
        contact_confidence='high'
    )

    result = generate_deliverables(
        job=job5,
        generate_doc=True,
        generate_pdf=False,
        generate_video=False,
        mock=True
    )

    success = result.success
    has_doc_url = result.proposal_doc_url is not None
    has_text = result.proposal_text is not None
    text_has_sections = (
        'My proposed approach' in (result.proposal_text or '') and
        "What you'll get" in (result.proposal_text or '') and
        'Timeline' in (result.proposal_text or '')
    )

    print(f"  Success: {success}")
    print(f"  Has doc URL: {has_doc_url}")
    print(f"  Has proposal text: {has_text}")
    print(f"  Text has all sections: {text_has_sections}")

    if success and has_doc_url and has_text and text_has_sections:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Test 6: Section order
    print("\n" + "="*60)
    print("Test 6: Sections appear in correct order")
    print("="*60)

    job6 = JobData(
        job_id='test91f',
        title='Make.com Integration',
        description='Need Make.com workflow expert',
        url='https://upwork.com/jobs/test91f',
        skills=['Make.com', 'API']
    )

    proposal6 = generate_proposal_content(job6, mock=True)
    text = proposal6.full_text

    approach_pos = text.find('My proposed approach')
    deliverables_pos = text.find("What you'll get")
    timeline_pos = text.find('Timeline')

    correct_order = (approach_pos < deliverables_pos < timeline_pos) if (approach_pos >= 0 and deliverables_pos >= 0 and timeline_pos >= 0) else False

    print(f"  'My proposed approach' position: {approach_pos}")
    print(f"  'What you'll get' position: {deliverables_pos}")
    print(f"  'Timeline' position: {timeline_pos}")
    print(f"  Correct order: {correct_order}")

    if correct_order:
        print("  Status: PASS")
    else:
        print("  Status: FAIL")
        all_passed = False

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    if all_passed:
        print("All Feature #91 tests PASSED!")
        return 0
    else:
        print("Some tests FAILED!")
        return 1


if __name__ == '__main__':
    sys.exit(run_tests())
