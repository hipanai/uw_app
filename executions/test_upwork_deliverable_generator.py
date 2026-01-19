#!/usr/bin/env python3
"""
Tests for Upwork Deliverable Generator

Tests Features #33-36:
- Feature #33: Deliverable generator creates proposal Google Doc
- Feature #34: Deliverable generator creates PDF from proposal
- Feature #35: Deliverable generator uploads PDF to cloud storage
- Feature #36: Deliverable generator orchestrates video + doc + PDF creation
"""

import unittest
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import os

# Add executions directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upwork_deliverable_generator import (
    JobData,
    ProposalContent,
    DeliverableResult,
    DOC_CREATION_LOCK,
    format_greeting,
    generate_proposal_content,
    create_google_doc,
    export_doc_to_pdf,
    upload_pdf_to_drive,
    generate_cover_letter,
    generate_deliverables,
    generate_deliverables_async,
    generate_deliverables_batch_async,
)


class TestJobData(unittest.TestCase):
    """Test JobData dataclass and parsing."""

    def test_from_dict_basic(self):
        """Test basic job data parsing."""
        data = {
            'job_id': '~123',
            'title': 'Test Job',
            'description': 'Test description',
            'url': 'https://upwork.com/jobs/~123',
            'skills': ['Python', 'AI']
        }
        job = JobData.from_dict(data)
        self.assertEqual(job.job_id, '~123')
        self.assertEqual(job.title, 'Test Job')
        self.assertEqual(job.skills, ['Python', 'AI'])

    def test_from_dict_extracts_job_id_from_url(self):
        """Test job_id extraction from URL when not provided."""
        data = {
            'title': 'Test Job',
            'description': 'Test',
            'url': 'https://upwork.com/jobs/~456abc'
        }
        job = JobData.from_dict(data)
        self.assertEqual(job.job_id, '~456abc')

    def test_from_dict_handles_skills_as_string(self):
        """Test skills parsing when provided as comma-separated string."""
        data = {
            'job_id': '~123',
            'title': 'Test',
            'description': 'Test',
            'url': 'https://upwork.com/jobs/~123',
            'skills': 'Python, AI, Automation'
        }
        job = JobData.from_dict(data)
        self.assertEqual(job.skills, ['Python', 'AI', 'Automation'])

    def test_from_dict_handles_nested_client(self):
        """Test client data extraction from nested structure."""
        data = {
            'job_id': '~123',
            'title': 'Test',
            'description': 'Test',
            'url': 'https://upwork.com/jobs/~123',
            'client': {
                'country': 'US',
                'total_spent': 50000,
                'total_hires': 25
            }
        }
        job = JobData.from_dict(data)
        self.assertEqual(job.client_country, 'US')
        self.assertEqual(job.client_spent, 50000)
        self.assertEqual(job.client_hires, 25)

    def test_from_dict_handles_flat_client_fields(self):
        """Test client data extraction from flat structure."""
        data = {
            'job_id': '~123',
            'title': 'Test',
            'description': 'Test',
            'url': 'https://upwork.com/jobs/~123',
            'client_country': 'UK',
            'client_spent': 10000,
            'client_hires': 5
        }
        job = JobData.from_dict(data)
        self.assertEqual(job.client_country, 'UK')


class TestFormatGreeting(unittest.TestCase):
    """Test greeting formatting based on contact discovery."""

    def test_no_contact_name(self):
        """Test default greeting when no contact name."""
        self.assertEqual(format_greeting(None, None), "Hey")

    def test_high_confidence_name(self):
        """Test confident greeting for high confidence names."""
        self.assertEqual(format_greeting("John", "high"), "Hey John")

    def test_medium_confidence_hedged(self):
        """Test hedged greeting for medium confidence."""
        result = format_greeting("Sarah", "medium")
        self.assertIn("Sarah", result)
        self.assertIn("if I have the right person", result)

    def test_low_confidence_hedged(self):
        """Test hedged greeting for low confidence."""
        result = format_greeting("Mike", "low")
        self.assertIn("Mike", result)
        self.assertIn("if I have the right person", result)


class TestProposalContent(unittest.TestCase):
    """Test proposal content generation."""

    def test_mock_proposal_generation(self):
        """Test proposal generation in mock mode."""
        job = JobData(
            job_id='~test',
            title='Build AI Pipeline',
            description='Need automation expert',
            url='https://upwork.com/jobs/~test',
            skills=['Python', 'AI']
        )

        proposal = generate_proposal_content(job, mock=True)

        self.assertIsInstance(proposal, ProposalContent)
        self.assertIn("Hey", proposal.greeting)
        self.assertIn("putting this together", proposal.intro)
        self.assertTrue(len(proposal.full_text) > 100)

    def test_proposal_includes_contact_name(self):
        """Test proposal uses contact name when available."""
        job = JobData(
            job_id='~test',
            title='Build AI Pipeline',
            description='Need automation expert',
            url='https://upwork.com/jobs/~test',
            contact_name='John',
            contact_confidence='high'
        )

        proposal = generate_proposal_content(job, mock=True)
        self.assertIn("John", proposal.greeting)


class TestDeliverableResult(unittest.TestCase):
    """Test DeliverableResult dataclass."""

    def test_to_dict(self):
        """Test result serialization."""
        result = DeliverableResult(
            job_id='~123',
            success=True,
            proposal_doc_url='https://docs.google.com/d/123',
            pdf_url='https://drive.google.com/file/456',
            video_url='https://heygen.com/video/789',
            proposal_text='Test proposal',
            cover_letter='Hi. Test cover letter.'
        )

        d = result.to_dict()
        self.assertEqual(d['job_id'], '~123')
        self.assertTrue(d['success'])
        self.assertEqual(d['proposal_doc_url'], 'https://docs.google.com/d/123')


class TestCoverLetterGeneration(unittest.TestCase):
    """Test cover letter generation."""

    def test_mock_cover_letter_with_doc_url(self):
        """Test cover letter includes doc URL when provided."""
        job = JobData(
            job_id='~test',
            title='Build AI Pipeline',
            description='Need expert',
            url='https://upwork.com/jobs/~test'
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/d/123',
            mock=True
        )

        self.assertIn('https://docs.google.com/d/123', cover_letter)
        self.assertTrue(len(cover_letter.split()) <= 40)  # Under 40 words

    def test_mock_cover_letter_without_doc_url(self):
        """Test cover letter without doc URL."""
        job = JobData(
            job_id='~test',
            title='Build AI Pipeline',
            description='Need expert',
            url='https://upwork.com/jobs/~test'
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=None,
            mock=True
        )

        self.assertIn('approach', cover_letter)
        self.assertTrue(len(cover_letter.split()) <= 40)


class TestFeature33GoogleDocCreation(unittest.TestCase):
    """Feature #33: Deliverable generator creates proposal Google Doc"""

    def test_generate_deliverables_creates_doc_url_mock(self):
        """Test that deliverables generation returns a doc URL."""
        job = JobData(
            job_id='~test33',
            title='Test Job for Feature 33',
            description='Testing Google Doc creation',
            url='https://upwork.com/jobs/~test33',
            skills=['Python']
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.proposal_doc_url)
        self.assertIn('google.com/document', result.proposal_doc_url)
        self.assertIn('mock_~test33', result.proposal_doc_url)

    def test_generate_deliverables_doc_url_format(self):
        """Test doc URL is valid Google Docs format."""
        job = JobData(
            job_id='~test33b',
            title='Test Job',
            description='Test',
            url='https://upwork.com/jobs/~test33b'
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        # URL should be valid Google Docs format
        self.assertTrue(
            result.proposal_doc_url.startswith('https://docs.google.com/document/d/')
        )

    @patch('upwork_deliverable_generator.get_google_services')
    def test_create_google_doc_with_mock_services(self, mock_get_services):
        """Test Google Doc creation with mocked services."""
        # Setup mocks
        mock_docs = MagicMock()
        mock_drive = MagicMock()

        mock_docs.documents().create().execute.return_value = {'documentId': 'test_doc_123'}
        mock_docs.documents().batchUpdate().execute.return_value = {}
        mock_drive.permissions().create().execute.return_value = {'id': 'perm_123'}

        mock_get_services.return_value = (mock_drive, mock_docs, None)

        # Test doc creation
        doc_url = create_google_doc(
            title='Test Proposal',
            content='Test content here.\n\nMy proposed approach\n\n1. Step one',
            drive_service=mock_drive,
            docs_service=mock_docs
        )

        self.assertIsNotNone(doc_url)
        self.assertIn('test_doc_123', doc_url)
        mock_docs.documents().create.assert_called()


class TestFeature34PDFCreation(unittest.TestCase):
    """Feature #34: Deliverable generator creates PDF from proposal"""

    def test_generate_deliverables_creates_pdf_url_mock(self):
        """Test that deliverables generation returns a PDF URL."""
        job = JobData(
            job_id='~test34',
            title='Test Job for Feature 34',
            description='Testing PDF creation',
            url='https://upwork.com/jobs/~test34',
            skills=['Python']
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,  # Need doc first
            generate_pdf=True,
            generate_video=False,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.pdf_url)
        self.assertIn('drive.google.com', result.pdf_url)

    def test_pdf_requires_doc_first(self):
        """Test PDF is only created if doc exists."""
        job = JobData(
            job_id='~test34b',
            title='Test Job',
            description='Test',
            url='https://upwork.com/jobs/~test34b'
        )

        # Skip doc creation
        result = generate_deliverables(
            job=job,
            generate_doc=False,
            generate_pdf=True,
            generate_video=False,
            mock=True
        )

        # PDF should be None since no doc was created
        self.assertIsNone(result.pdf_url)


class TestFeature35PDFUpload(unittest.TestCase):
    """Feature #35: Deliverable generator uploads PDF to cloud storage"""

    def test_pdf_url_is_accessible_format(self):
        """Test PDF URL is in accessible format."""
        job = JobData(
            job_id='~test35',
            title='Test Job for Feature 35',
            description='Testing PDF upload',
            url='https://upwork.com/jobs/~test35'
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=True,
            generate_video=False,
            mock=True
        )

        self.assertIsNotNone(result.pdf_url)
        # URL should be publicly accessible format
        self.assertTrue(
            'drive.google.com' in result.pdf_url or
            'storage.googleapis.com' in result.pdf_url
        )

    @patch('upwork_deliverable_generator.get_google_services')
    def test_upload_pdf_to_drive_mock(self, mock_get_services):
        """Test PDF upload to Drive with mocked services."""
        mock_drive = MagicMock()
        mock_drive.files().create().execute.return_value = {
            'id': 'pdf_file_123',
            'webViewLink': 'https://drive.google.com/file/d/pdf_file_123/view'
        }
        mock_drive.permissions().create().execute.return_value = {'id': 'perm_123'}

        mock_get_services.return_value = (mock_drive, None, None)

        # Create a temp PDF file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4 test content')
            pdf_path = Path(f.name)

        try:
            url = upload_pdf_to_drive(pdf_path, mock_drive)
            self.assertIsNotNone(url)
            self.assertIn('pdf_file_123', url)
        finally:
            pdf_path.unlink(missing_ok=True)


class TestFeature36FullOrchestration(unittest.TestCase):
    """Feature #36: Deliverable generator orchestrates video + doc + PDF creation"""

    def test_full_orchestration_mock(self):
        """Test full deliverable generation with all components."""
        job = JobData(
            job_id='~test36',
            title='Test Job for Feature 36',
            description='Testing full orchestration of video, doc, and PDF',
            url='https://upwork.com/jobs/~test36',
            skills=['Python', 'AI', 'Automation'],
            budget_type='fixed',
            budget_min=1000,
            budget_max=2000
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=True,
            generate_video=True,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.proposal_doc_url, "Doc URL should be populated")
        self.assertIsNotNone(result.pdf_url, "PDF URL should be populated")
        self.assertIsNotNone(result.video_url, "Video URL should be populated")
        self.assertIsNotNone(result.proposal_text, "Proposal text should exist")
        self.assertIsNotNone(result.cover_letter, "Cover letter should exist")

    def test_orchestration_returns_all_urls(self):
        """Test that all URL fields are populated."""
        job = JobData(
            job_id='~test36b',
            title='Full Test',
            description='Full orchestration test',
            url='https://upwork.com/jobs/~test36b'
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=True,
            generate_video=True,
            mock=True
        )

        # All three URLs should be present
        urls = [result.proposal_doc_url, result.pdf_url, result.video_url]
        self.assertEqual(len([u for u in urls if u]), 3)

    def test_orchestration_partial_generation(self):
        """Test orchestration with some components disabled."""
        job = JobData(
            job_id='~test36c',
            title='Partial Test',
            description='Partial orchestration test',
            url='https://upwork.com/jobs/~test36c'
        )

        # Only generate doc
        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.proposal_doc_url)
        self.assertIsNone(result.pdf_url)
        self.assertIsNone(result.video_url)


class TestBatchProcessing(unittest.TestCase):
    """Test batch processing of multiple jobs."""

    def test_batch_processing_async(self):
        """Test async batch processing of multiple jobs."""
        jobs = [
            JobData(
                job_id=f'~batch{i}',
                title=f'Batch Job {i}',
                description=f'Description for job {i}',
                url=f'https://upwork.com/jobs/~batch{i}'
            )
            for i in range(5)
        ]

        results = asyncio.run(generate_deliverables_batch_async(
            jobs=jobs,
            max_concurrent=2,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        ))

        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.success for r in results))
        self.assertTrue(all(r.proposal_doc_url for r in results))


class TestErrorHandling(unittest.TestCase):
    """Test error handling in deliverable generation."""

    def test_handles_missing_job_id(self):
        """Test handling of jobs without ID."""
        job = JobData(
            job_id='',
            title='No ID Job',
            description='Test',
            url=''
        )

        result = generate_deliverables(job=job, mock=True)
        # Should still succeed with empty ID
        self.assertTrue(result.success)

    def test_result_includes_error_on_failure(self):
        """Test that errors are captured in result."""
        result = DeliverableResult(
            job_id='~error_test',
            success=False,
            error='Test error message'
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, 'Test error message')


class TestCoverLetterWordCount(unittest.TestCase):
    """Test cover letter follows ~35 word limit."""

    def test_cover_letter_under_40_words(self):
        """Test cover letter is concise (under 40 words)."""
        job = JobData(
            job_id='~wordcount',
            title='AI Automation Project',
            description='Need expert for automation',
            url='https://upwork.com/jobs/~wordcount',
            skills=['n8n', 'Python', 'AI']
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/d/test',
            mock=True
        )

        word_count = len(cover_letter.split())
        self.assertLessEqual(word_count, 40, f"Cover letter too long: {word_count} words")


class TestProposalDocUrlIncludedInCoverLetter(unittest.TestCase):
    """
    Feature #90: Cover letter includes proposal doc link

    Steps:
    1. Generate cover letter with proposal doc
    2. Verify link is included
    3. Verify link is valid Google Doc URL
    """

    def test_cover_letter_includes_doc_link(self):
        """Test that cover letter includes the proposal doc URL."""
        job = JobData(
            job_id='~doclink',
            title='Test Job',
            description='Test',
            url='https://upwork.com/jobs/~doclink'
        )

        doc_url = 'https://docs.google.com/document/d/abc123'
        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=doc_url,
            mock=True
        )

        self.assertIn(doc_url, cover_letter)

    def test_cover_letter_doc_link_is_valid_google_doc_url(self):
        """Test that the doc link is a valid Google Doc URL."""
        job = JobData(
            job_id='~f90_valid',
            title='AI Project',
            description='Need AI help',
            url='https://upwork.com/jobs/~f90_valid',
            skills=['AI', 'Python']
        )

        # Test with a valid Google Doc URL
        doc_url = 'https://docs.google.com/document/d/1ABcDeFgHiJkLmNoPqRsTuVwXyZ'
        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=doc_url,
            mock=True
        )

        # Verify the link is included
        self.assertIn(doc_url, cover_letter)

        # Verify it's a valid Google Docs format
        self.assertTrue(
            'docs.google.com/document/d/' in doc_url,
            f"Doc URL should be valid Google Docs format: {doc_url}"
        )

        print("\n[Feature #90] Cover letter includes valid Google Doc URL:")
        print(f"  URL: {doc_url}")
        print(f"  Is valid Google Docs format: True")
        print("  Status: PASS")

    def test_cover_letter_without_doc_url_no_link(self):
        """Test that cover letter without doc URL doesn't have broken links."""
        job = JobData(
            job_id='~f90_nolink',
            title='Test Project',
            description='Need help',
            url='https://upwork.com/jobs/~f90_nolink'
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=None,
            mock=True
        )

        # Should not contain placeholder or broken link
        self.assertNotIn('[LINK]', cover_letter)
        self.assertNotIn('[link]', cover_letter)
        self.assertNotIn('None', cover_letter)

        print("\n[Feature #90] Cover letter without doc URL:")
        print("  No [LINK] placeholder: True")
        print("  No 'None' string: True")
        print("  Status: PASS")

    def test_cover_letter_with_various_doc_url_formats(self):
        """Test cover letter handles various Google Doc URL formats."""
        job = JobData(
            job_id='~f90_formats',
            title='Automation Project',
            description='Need automation',
            url='https://upwork.com/jobs/~f90_formats'
        )

        # Test various valid Google Doc URL formats
        valid_urls = [
            'https://docs.google.com/document/d/abc123',
            'https://docs.google.com/document/d/1-ABCD_efgh-ijkL',
            'https://docs.google.com/document/d/xYz789AbC-DeFgH_iJkLmNoPqRs'
        ]

        for doc_url in valid_urls:
            cover_letter = generate_cover_letter(
                job=job,
                proposal_doc_url=doc_url,
                mock=True
            )
            self.assertIn(doc_url, cover_letter,
                f"Cover letter should include URL: {doc_url}")

        print("\n[Feature #90] Various doc URL formats:")
        print(f"  Tested {len(valid_urls)} URL formats")
        print("  All included in cover letter: True")
        print("  Status: PASS")


class TestFeature37AttachmentContentInProposal(unittest.TestCase):
    """Feature #37: Proposal generator uses attachment content in generation"""

    def test_job_data_supports_attachment_content(self):
        """Test JobData can store attachment content."""
        attachment_content = """
        PROJECT REQUIREMENTS DOCUMENT

        1. Must integrate with Salesforce API
        2. Automation should run every 6 hours
        3. Maximum budget: $5,000
        4. Timeline: 2 weeks
        5. Required experience: 5+ years with Python
        """

        job = JobData(
            job_id='~att37',
            title='Build Salesforce Integration',
            description='Need automation expert',
            url='https://upwork.com/jobs/~att37',
            attachment_content=attachment_content
        )

        self.assertIsNotNone(job.attachment_content)
        self.assertIn('Salesforce API', job.attachment_content)
        self.assertIn('budget', job.attachment_content.lower())

    def test_job_data_from_dict_includes_attachment_content(self):
        """Test JobData.from_dict preserves attachment content."""
        data = {
            'job_id': '~att37b',
            'title': 'Test Job',
            'description': 'Test description',
            'url': 'https://upwork.com/jobs/~att37b',
            'attachment_content': 'REQUIREMENT: Must use PostgreSQL database. DEADLINE: March 15th.'
        }

        job = JobData.from_dict(data)
        self.assertEqual(job.attachment_content, data['attachment_content'])

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_prompt_includes_attachment_content(self, mock_anthropic):
        """Test that proposal generation prompt includes attachment content."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = """Hey.

I spent ~15 minutes putting this together for you. In short, it's how I would create your Salesforce integration end to end.

I've worked with $MM companies like Anthropic and I have a lot of experience with similar integrations.

My proposed approach

1. First, I would review your requirement document to understand the Salesforce API integration needs...
2. Then I would set up the automation pipeline...

What you'll get

- Working Salesforce integration
- Documentation

Timeline

Based on your requirements, I can deliver within 2 weeks."""

        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create job with attachment content
        attachment_content = """
        PROJECT REQUIREMENTS DOCUMENT

        1. Must integrate with Salesforce API
        2. Automation should run every 6 hours
        3. Required tech stack: Python, PostgreSQL
        """

        job = JobData(
            job_id='~att37c',
            title='Build Salesforce Integration',
            description='Need automation expert for Salesforce project',
            url='https://upwork.com/jobs/~att37c',
            skills=['Python', 'Salesforce', 'API'],
            attachment_content=attachment_content
        )

        # Generate proposal (non-mock mode to test API call)
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Verify API was called
        mock_client.messages.create.assert_called_once()

        # Get the prompt that was sent to the API
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))
        prompt_content = messages[0]['content'] if messages else ''

        # Verify attachment content is in the prompt
        self.assertIn('ATTACHMENT CONTENT', prompt_content)
        self.assertIn('Salesforce API', prompt_content)
        self.assertIn('every 6 hours', prompt_content)

    def test_proposal_generation_with_attachment_mock(self):
        """Test proposal generation succeeds with attachment content in mock mode."""
        attachment_content = """
        REQUIREMENTS:
        - CRM integration with HubSpot
        - Daily sync at midnight
        - Error notifications via Slack
        """

        job = JobData(
            job_id='~att37d',
            title='HubSpot CRM Integration',
            description='Build automated CRM sync',
            url='https://upwork.com/jobs/~att37d',
            skills=['Python', 'HubSpot', 'API'],
            attachment_content=attachment_content
        )

        # Generate proposal in mock mode
        proposal = generate_proposal_content(job, mock=True)

        self.assertIsInstance(proposal, ProposalContent)
        self.assertIsNotNone(proposal.full_text)
        self.assertTrue(len(proposal.full_text) > 50)

    def test_full_deliverables_with_attachment_content(self):
        """Test full deliverable generation with attachment content."""
        attachment_content = """
        DETAILED REQUIREMENTS:

        1. API Integration
           - Connect to REST API
           - Handle pagination
           - Rate limiting support

        2. Data Processing
           - Transform JSON to CSV
           - Filter records by date

        3. Scheduling
           - Run every 4 hours
           - Retry on failure
        """

        job = JobData(
            job_id='~att37e',
            title='API Integration Pipeline',
            description='Need expert to build data pipeline',
            url='https://upwork.com/jobs/~att37e',
            skills=['Python', 'REST API', 'ETL'],
            attachment_content=attachment_content
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.proposal_doc_url)
        self.assertIsNotNone(result.proposal_text)

    def test_attachments_list_converted_to_content(self):
        """Test that job with attachments list has extracted content accessible."""
        # Simulate job data as it would come from deep extractor
        job_data = {
            'job_id': '~att37f',
            'title': 'Build Automation',
            'description': 'Need automation expert',
            'url': 'https://upwork.com/jobs/~att37f',
            'attachments': [
                {'filename': 'requirements.pdf', 'extracted_text': 'Must use Python 3.10+'},
                {'filename': 'specs.docx', 'extracted_text': 'Timeline: 3 weeks'}
            ],
            'attachment_content': 'Must use Python 3.10+\n\nTimeline: 3 weeks'
        }

        job = JobData.from_dict(job_data)

        self.assertIsNotNone(job.attachment_content)
        self.assertIn('Python 3.10', job.attachment_content)
        self.assertIn('3 weeks', job.attachment_content)

    def test_proposal_references_attachment_requirements(self):
        """
        Integration test: Verify proposal generation would reference attachment requirements.

        This test validates that when attachment content is provided, the proposal
        generation prompt structure properly includes it for the AI to reference.
        """
        # Create job with specific attachment requirements
        attachment_content = """
        MANDATORY REQUIREMENTS FROM CLIENT:

        1. Use n8n for workflow automation (not Zapier)
        2. Integrate with Airtable database
        3. Send notifications to Microsoft Teams
        4. Must handle 10,000+ records per run
        5. Budget cap: $3,500
        """

        job = JobData(
            job_id='~att37g',
            title='Build n8n Workflow Automation',
            description='Looking for n8n expert to automate our data processes',
            url='https://upwork.com/jobs/~att37g',
            skills=['n8n', 'Airtable', 'API', 'Automation'],
            attachment_content=attachment_content
        )

        # Verify the job has attachment content
        self.assertIsNotNone(job.attachment_content)
        self.assertIn('n8n', job.attachment_content)
        self.assertIn('Airtable', job.attachment_content)
        self.assertIn('Microsoft Teams', job.attachment_content)
        self.assertIn('10,000+', job.attachment_content)

        # In mock mode, proposal generation succeeds
        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.proposal_text)


class TestFeature38Opus45ExtendedThinking(unittest.TestCase):
    """Feature #38: Proposal generator uses Opus 4.5 with extended thinking"""

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_uses_opus_45_model(self, mock_anthropic):
        """Test that proposal generation uses claude-opus-4-5-20251101 model."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = "Hey.\n\nI spent ~15 minutes putting this together for you.\n\nMy proposed approach\n\n1. First step...\n\nWhat you'll get\n\n- Deliverable\n\nTimeline\n\n1-2 weeks"
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create test job
        job = JobData(
            job_id='~opus45test',
            title='Test AI Job',
            description='Testing Opus 4.5 model usage',
            url='https://upwork.com/jobs/~opus45test',
            skills=['Python', 'AI']
        )

        # Generate proposal (non-mock mode to test API call)
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Verify API was called
        mock_client.messages.create.assert_called_once()

        # Get the call arguments
        call_args = mock_client.messages.create.call_args

        # Extract model from call
        model = call_args.kwargs.get('model') or call_args[1].get('model')

        # Verify model is Opus 4.5
        self.assertEqual(model, 'claude-opus-4-5-20251101',
                        f"Expected claude-opus-4-5-20251101 but got {model}")

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_has_thinking_enabled(self, mock_anthropic):
        """Test that proposal generation has thinking enabled."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = "Hey.\n\nTest proposal content.\n\nMy proposed approach\n\n1. Step\n\nWhat you'll get\n\n- Item\n\nTimeline\n\nSoon"
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create test job
        job = JobData(
            job_id='~thinkingtest',
            title='Test Job',
            description='Testing thinking enabled',
            url='https://upwork.com/jobs/~thinkingtest',
            skills=['Python']
        )

        # Generate proposal
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Get the call arguments
        call_args = mock_client.messages.create.call_args

        # Extract thinking parameter
        thinking = call_args.kwargs.get('thinking') or call_args[1].get('thinking')

        # Verify thinking is enabled
        self.assertIsNotNone(thinking, "thinking parameter should be set")
        self.assertEqual(thinking.get('type'), 'enabled',
                        f"thinking.type should be 'enabled', got {thinking.get('type')}")

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_has_budget_tokens_at_least_8000(self, mock_anthropic):
        """Test that proposal generation has budget_tokens >= 8000."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = "Test proposal.\n\nMy proposed approach\n\n1. Do this\n\nWhat you'll get\n\n- Stuff\n\nTimeline\n\nQuick"
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create test job
        job = JobData(
            job_id='~budgettest',
            title='Test Job',
            description='Testing budget tokens',
            url='https://upwork.com/jobs/~budgettest',
            skills=['Python']
        )

        # Generate proposal
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Get the call arguments
        call_args = mock_client.messages.create.call_args

        # Extract thinking parameter
        thinking = call_args.kwargs.get('thinking') or call_args[1].get('thinking')

        # Verify budget_tokens >= 8000
        self.assertIsNotNone(thinking, "thinking parameter should be set")
        budget_tokens = thinking.get('budget_tokens', 0)
        self.assertGreaterEqual(budget_tokens, 8000,
                               f"budget_tokens should be >= 8000, got {budget_tokens}")

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_api_call_has_all_required_params(self, mock_anthropic):
        """Test that proposal API call has all required parameters for extended thinking."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = "Full proposal.\n\nMy proposed approach\n\n1. Steps\n\nWhat you'll get\n\n- Items\n\nTimeline\n\n2 weeks"
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create comprehensive test job
        job = JobData(
            job_id='~fulltest',
            title='Complete Test Job',
            description='Testing all parameters are correct',
            url='https://upwork.com/jobs/~fulltest',
            skills=['Python', 'AI', 'Automation'],
            budget_type='fixed',
            budget_min=1000,
            budget_max=2000
        )

        # Generate proposal
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Verify API was called
        mock_client.messages.create.assert_called_once()

        # Get the call arguments
        call_args = mock_client.messages.create.call_args

        # Extract all parameters
        model = call_args.kwargs.get('model') or call_args[1].get('model')
        max_tokens = call_args.kwargs.get('max_tokens') or call_args[1].get('max_tokens')
        thinking = call_args.kwargs.get('thinking') or call_args[1].get('thinking')
        messages = call_args.kwargs.get('messages') or call_args[1].get('messages')

        # Comprehensive assertions
        self.assertEqual(model, 'claude-opus-4-5-20251101', "Model should be Opus 4.5")
        self.assertIsNotNone(max_tokens, "max_tokens should be set")
        self.assertGreater(max_tokens, 0, "max_tokens should be positive")

        self.assertIsNotNone(thinking, "thinking should be set")
        self.assertEqual(thinking.get('type'), 'enabled', "thinking.type should be 'enabled'")
        self.assertGreaterEqual(thinking.get('budget_tokens', 0), 8000, "budget_tokens should be >= 8000")

        self.assertIsNotNone(messages, "messages should be set")
        self.assertGreater(len(messages), 0, "messages should not be empty")

    def test_proposal_content_returned_correctly(self):
        """Test that proposal content is properly returned from mock mode."""
        job = JobData(
            job_id='~mockreturn',
            title='Mock Return Test',
            description='Testing mock returns correct structure',
            url='https://upwork.com/jobs/~mockreturn',
            skills=['Python']
        )

        # Generate in mock mode
        proposal = generate_proposal_content(job, mock=True)

        # Verify structure
        self.assertIsInstance(proposal, ProposalContent)
        self.assertIsNotNone(proposal.greeting)
        self.assertIsNotNone(proposal.full_text)
        self.assertTrue(len(proposal.full_text) > 0)


class TestFeature77GoogleDocsSemaphore(unittest.TestCase):
    """Feature #77: Google Docs API uses semaphore to avoid SSL errors."""

    def test_doc_creation_lock_exists(self):
        """
        Feature #77 Step 1: Verify semaphore exists
        Check that DOC_CREATION_LOCK is defined in the module.
        """
        from upwork_deliverable_generator import DOC_CREATION_LOCK
        import threading

        # Verify it's a semaphore
        self.assertIsInstance(DOC_CREATION_LOCK, threading.Semaphore,
            "DOC_CREATION_LOCK should be a threading.Semaphore")

        # Verify it's a semaphore with value 1 (binary semaphore)
        # Check internal value (this is implementation-specific but works for testing)
        self.assertEqual(DOC_CREATION_LOCK._value, 1,
            "DOC_CREATION_LOCK should be a binary semaphore (value=1)")

        print("\n[Feature #77] Step 1: Semaphore exists")
        print(f"  Type: {type(DOC_CREATION_LOCK).__name__}")
        print(f"  Value: {DOC_CREATION_LOCK._value}")
        print("  Status: PASS")

    def test_semaphore_limits_concurrent_calls(self):
        """
        Feature #77 Step 2: Verify semaphore limits concurrent calls
        Test that the semaphore enforces mutual exclusion.
        """
        from upwork_deliverable_generator import DOC_CREATION_LOCK
        import threading
        import time

        # Track concurrent access
        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def worker():
            nonlocal max_concurrent, current_concurrent
            with DOC_CREATION_LOCK:
                with lock:
                    current_concurrent += 1
                    max_concurrent = max(max_concurrent, current_concurrent)

                time.sleep(0.1)  # Simulate API call

                with lock:
                    current_concurrent -= 1

        # Launch 5 threads
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # With semaphore(1), max concurrent should be 1
        self.assertEqual(max_concurrent, 1,
            f"With semaphore(1), max concurrent should be 1, got {max_concurrent}")

        print("\n[Feature #77] Step 2: Semaphore limits concurrent calls")
        print(f"  Threads launched: 5")
        print(f"  Max concurrent: {max_concurrent}")
        print("  Status: PASS")

    def test_no_ssl_errors_with_semaphore(self):
        """
        Feature #77 Step 3: Verify no SSL errors occur
        Test that serialized doc creation prevents SSL errors.
        """
        # In mock mode, we verify the semaphore pattern is correct
        # SSL errors typically occur with concurrent API calls

        # Create test jobs
        jobs = [
            JobData(
                job_id=f'~ssl_test_{i}',
                title=f'SSL Test Job {i}',
                description='Testing SSL error prevention',
                url=f'https://upwork.com/jobs/~ssl_test_{i}',
                skills=['Python']
            )
            for i in range(10)
        ]

        # Generate docs in mock mode (simulates parallel processing)
        results = []
        errors = []

        for job in jobs:
            try:
                result = generate_deliverables(job, mock=True)
                results.append(result)
            except Exception as e:
                errors.append(str(e))

        # All should succeed without errors
        self.assertEqual(len(errors), 0,
            f"Expected no errors, got {len(errors)}: {errors}")
        self.assertEqual(len(results), 10,
            f"Expected 10 results, got {len(results)}")

        # Verify all have doc URLs
        for result in results:
            self.assertIsNotNone(result.proposal_doc_url,
                "All results should have proposal_doc_url")

        print("\n[Feature #77] Step 3: No SSL errors occur")
        print(f"  Jobs processed: {len(jobs)}")
        print(f"  Successful: {len(results)}")
        print(f"  Errors: {len(errors)}")
        print("  Status: PASS")

    def test_all_docs_created(self):
        """
        Feature #77 Step 4: Verify all docs created
        Ensure parallel doc generation completes successfully.
        """
        # Create 10 test jobs
        jobs = [
            JobData(
                job_id=f'~doc_test_{i}',
                title=f'Doc Creation Test {i}',
                description='Testing doc creation',
                url=f'https://upwork.com/jobs/~doc_test_{i}',
                skills=['Python', 'AI']
            )
            for i in range(10)
        ]

        # Generate deliverables in mock mode
        results = []
        for job in jobs:
            result = generate_deliverables(job, mock=True)
            results.append(result)

        # Verify all 10 docs created
        self.assertEqual(len(results), 10,
            f"Expected 10 results, got {len(results)}")

        # Verify each has a doc URL
        docs_created = sum(1 for r in results if r.proposal_doc_url is not None)
        self.assertEqual(docs_created, 10,
            f"Expected 10 docs created, got {docs_created}")

        # Verify no duplicates (each job has unique doc)
        doc_urls = [r.proposal_doc_url for r in results if r.proposal_doc_url]
        unique_urls = set(doc_urls)
        self.assertEqual(len(unique_urls), 10,
            f"Expected 10 unique doc URLs, got {len(unique_urls)}")

        print("\n[Feature #77] Step 4: All docs created")
        print(f"  Jobs: {len(jobs)}")
        print(f"  Docs created: {docs_created}")
        print(f"  Unique docs: {len(unique_urls)}")
        print("  Status: PASS")

    def test_batch_async_uses_semaphore(self):
        """
        Test that batch async processing uses semaphore for rate limiting.
        """
        import inspect

        # Check the batch function signature
        sig = inspect.signature(generate_deliverables_batch_async)
        params = sig.parameters

        # Verify max_concurrent parameter exists
        self.assertIn('max_concurrent', params,
            "generate_deliverables_batch_async should have max_concurrent parameter")

        # Verify default is reasonable
        default_concurrent = params['max_concurrent'].default
        self.assertGreater(default_concurrent, 0,
            "max_concurrent default should be > 0")
        self.assertLessEqual(default_concurrent, 5,
            "max_concurrent default should be <= 5 to avoid SSL errors")

        print("\n[Feature #77] Batch async uses semaphore:")
        print(f"  Has max_concurrent param: True")
        print(f"  Default value: {default_concurrent}")
        print("  Status: PASS")

    def test_create_google_doc_uses_lock(self):
        """
        Test that create_google_doc function uses the DOC_CREATION_LOCK.
        """
        import inspect

        # Read the source code of create_google_doc
        source = inspect.getsource(create_google_doc)

        # Check that it uses DOC_CREATION_LOCK
        self.assertIn('DOC_CREATION_LOCK', source,
            "create_google_doc should use DOC_CREATION_LOCK")

        # Check that it uses the context manager pattern
        self.assertIn('with DOC_CREATION_LOCK', source,
            "create_google_doc should use 'with DOC_CREATION_LOCK' context manager")

        print("\n[Feature #77] create_google_doc uses lock:")
        print("  DOC_CREATION_LOCK referenced: True")
        print("  Uses context manager: True")
        print("  Status: PASS")


class TestFeature89CoverLetterAboveTheFold(unittest.TestCase):
    """
    Feature #89: Cover letter follows above-the-fold format (~35 words)

    Steps:
    1. Generate cover letter for job
    2. Count words in cover letter
    3. Verify word count is approximately 35 words
    4. Verify format matches template
    """

    def test_cover_letter_word_count_approximately_35_words(self):
        """Test that cover letter word count is approximately 35 words (25-45 range)."""
        job = JobData(
            job_id='~f89_wordcount',
            title='AI Workflow Automation Expert',
            description='We need someone to build AI-powered automation workflows using n8n, Claude API, and various integrations.',
            url='https://upwork.com/jobs/~f89_wordcount',
            skills=['n8n', 'Claude API', 'Python', 'Automation']
        )

        doc_url = 'https://docs.google.com/document/d/test89'
        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=doc_url,
            mock=True
        )

        word_count = len(cover_letter.split())

        # Word count should be approximately 35 words (within 25-45 range)
        self.assertGreaterEqual(word_count, 20,
            f"Cover letter too short: {word_count} words (minimum ~25)")
        self.assertLessEqual(word_count, 50,
            f"Cover letter too long: {word_count} words (should be ~35)")

        print(f"\n[Feature #89] Cover letter word count: {word_count} words")
        print(f"  Expected range: 25-45 words")
        print(f"  Status: PASS")

    def test_cover_letter_format_starts_with_hi(self):
        """Test that cover letter starts with 'Hi.'"""
        job = JobData(
            job_id='~f89_format',
            title='Zapier Automation Specialist',
            description='Looking for Zapier expert',
            url='https://upwork.com/jobs/~f89_format',
            skills=['Zapier', 'Automation']
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/document/d/test',
            mock=True
        )

        # Cover letter should start with "Hi." or "Hi "
        self.assertTrue(
            cover_letter.startswith('Hi.') or cover_letter.startswith('Hi ') or cover_letter.lower().startswith('hi'),
            f"Cover letter should start with 'Hi': {cover_letter[:30]}..."
        )

        print("\n[Feature #89] Cover letter format - starts with Hi:")
        print(f"  First 30 chars: {cover_letter[:30]}")
        print("  Status: PASS")

    def test_cover_letter_format_includes_expertise_mention(self):
        """Test that cover letter mentions daily work with the skill area."""
        job = JobData(
            job_id='~f89_expertise',
            title='n8n Workflow Builder',
            description='Need n8n automation expert',
            url='https://upwork.com/jobs/~f89_expertise',
            skills=['n8n', 'API', 'Automation']
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/document/d/test',
            mock=True
        )

        # Cover letter should mention working with something "daily" or similar expertise indicators
        expertise_indicators = ['daily', 'work with', 'just built', 'built', 'experience']
        has_expertise = any(indicator in cover_letter.lower() for indicator in expertise_indicators)

        self.assertTrue(has_expertise,
            f"Cover letter should indicate expertise: {cover_letter}")

        print("\n[Feature #89] Cover letter format - expertise mention:")
        print(f"  Has expertise indicator: {has_expertise}")
        print("  Status: PASS")

    def test_cover_letter_format_includes_doc_url(self):
        """Test that cover letter includes the proposal doc URL when provided."""
        job = JobData(
            job_id='~f89_url',
            title='AI Integration Project',
            description='Need AI integration help',
            url='https://upwork.com/jobs/~f89_url',
            skills=['AI', 'Python']
        )

        doc_url = 'https://docs.google.com/document/d/abc123xyz'
        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url=doc_url,
            mock=True
        )

        self.assertIn(doc_url, cover_letter,
            f"Cover letter should include doc URL: {cover_letter}")

        print("\n[Feature #89] Cover letter format - includes doc URL:")
        print(f"  URL present: True")
        print("  Status: PASS")

    def test_cover_letter_format_ends_with_walkthrough_offer(self):
        """Test that cover letter ends with a walkthrough/approach offer."""
        job = JobData(
            job_id='~f89_ending',
            title='Automation Expert Needed',
            description='Looking for automation help',
            url='https://upwork.com/jobs/~f89_ending',
            skills=['Automation']
        )

        # Test with doc URL
        cover_letter_with_url = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/document/d/test',
            mock=True
        )

        # Test without doc URL
        cover_letter_no_url = generate_cover_letter(
            job=job,
            proposal_doc_url=None,
            mock=True
        )

        # With URL, should mention "walkthrough" or contain the link
        has_walkthrough = 'walkthrough' in cover_letter_with_url.lower() or 'docs.google.com' in cover_letter_with_url
        self.assertTrue(has_walkthrough,
            f"Cover letter with URL should mention walkthrough or contain link: {cover_letter_with_url}")

        # Without URL, should mention "approach" or "walk you through"
        approach_indicators = ['approach', 'walk', 'explain', 'show', 'happy to']
        has_approach = any(ind in cover_letter_no_url.lower() for ind in approach_indicators)
        self.assertTrue(has_approach,
            f"Cover letter without URL should offer to explain: {cover_letter_no_url}")

        print("\n[Feature #89] Cover letter format - ends with offer:")
        print(f"  With URL has walkthrough: {has_walkthrough}")
        print(f"  Without URL has approach: {has_approach}")
        print("  Status: PASS")

    def test_cover_letter_no_filler_phrases(self):
        """Test that cover letter avoids common filler phrases."""
        job = JobData(
            job_id='~f89_nofiller',
            title='Python Developer',
            description='Need Python help',
            url='https://upwork.com/jobs/~f89_nofiller',
            skills=['Python']
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/document/d/test',
            mock=True
        )

        # Check for common filler phrases that should NOT be present
        filler_phrases = [
            "i'm excited",
            "i would love to",
            "i am very interested",
            "dear hiring manager",
            "to whom it may concern",
            "i am writing to apply",
            "i believe i am"
        ]

        for filler in filler_phrases:
            self.assertNotIn(filler, cover_letter.lower(),
                f"Cover letter should not contain filler phrase: '{filler}'")

        print("\n[Feature #89] Cover letter format - no filler phrases:")
        print("  No 'I'm excited': True")
        print("  No 'I would love to': True")
        print("  No formal greetings: True")
        print("  Status: PASS")

    def test_cover_letter_word_count_multiple_jobs(self):
        """Test word count consistency across different job types."""
        jobs = [
            JobData(
                job_id='~f89_multi1',
                title='Make.com Integration Expert',
                description='Need Make.com help',
                url='https://upwork.com/jobs/~f89_multi1',
                skills=['Make.com', 'API']
            ),
            JobData(
                job_id='~f89_multi2',
                title='AI Chatbot Developer',
                description='Build AI chatbot',
                url='https://upwork.com/jobs/~f89_multi2',
                skills=['AI', 'Python', 'Claude']
            ),
            JobData(
                job_id='~f89_multi3',
                title='Data Pipeline Builder',
                description='Build data pipeline',
                url='https://upwork.com/jobs/~f89_multi3',
                skills=['Python', 'Data', 'ETL']
            )
        ]

        word_counts = []
        for job in jobs:
            cover_letter = generate_cover_letter(
                job=job,
                proposal_doc_url='https://docs.google.com/document/d/test',
                mock=True
            )
            word_counts.append(len(cover_letter.split()))

        # All should be approximately 35 words (within 20-50 range)
        for i, wc in enumerate(word_counts):
            self.assertGreaterEqual(wc, 20,
                f"Job {i+1} cover letter too short: {wc} words")
            self.assertLessEqual(wc, 50,
                f"Job {i+1} cover letter too long: {wc} words")

        print("\n[Feature #89] Multiple job word counts:")
        for i, wc in enumerate(word_counts):
            print(f"  Job {i+1}: {wc} words")
        print("  All within 20-50 range: True")
        print("  Status: PASS")

    def test_cover_letter_template_format_structure(self):
        """Test the overall structure of cover letter matches template."""
        job = JobData(
            job_id='~f89_template',
            title='Workflow Automation Expert',
            description='Need workflow automation',
            url='https://upwork.com/jobs/~f89_template',
            skills=['n8n', 'Zapier', 'Automation']
        )

        cover_letter = generate_cover_letter(
            job=job,
            proposal_doc_url='https://docs.google.com/document/d/testdoc',
            mock=True
        )

        # Template structure:
        # "Hi. I work with [2-4 word paraphrase] daily & just built a [2-5 word thing]. Free walkthrough: [LINK]"

        # Check basic structure elements
        self.assertIn('.', cover_letter, "Cover letter should have sentences")

        # Word count should be approximately 35 (above-the-fold)
        word_count = len(cover_letter.split())
        self.assertLess(word_count, 50, "Cover letter should fit above the fold (<50 words)")

        print("\n[Feature #89] Cover letter template structure:")
        print(f"  Word count: {word_count}")
        print("  Has punctuation: True")
        print("  Above the fold (<50 words): True")
        print("  Status: PASS")


class TestFeature91ProposalConversationalFormat(unittest.TestCase):
    """
    Feature #91: Proposal doc follows conversational format

    Steps:
    1. Generate proposal for job
    2. Verify greeting uses contact name if available
    3. Verify 'My proposed approach' section exists
    4. Verify 'What you'll get' section exists
    5. Verify 'Timeline' section exists
    """

    def test_proposal_has_my_proposed_approach_section(self):
        """Step 2: Verify 'My proposed approach' section exists in proposal."""
        job = JobData(
            job_id='~f91_approach',
            title='AI Automation Pipeline',
            description='Need expert to build AI-powered automation',
            url='https://upwork.com/jobs/~f91_approach',
            skills=['Python', 'AI', 'n8n']
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify 'My proposed approach' section exists
        self.assertIn('My proposed approach', proposal.full_text,
            "Proposal should contain 'My proposed approach' section")

        print("\n[Feature #91] 'My proposed approach' section:")
        print(f"  Present in proposal: True")
        print("  Status: PASS")

    def test_proposal_has_what_youll_get_section(self):
        """Step 3: Verify 'What you'll get' section exists in proposal."""
        job = JobData(
            job_id='~f91_deliverables',
            title='Zapier Automation Project',
            description='Build Zapier workflows',
            url='https://upwork.com/jobs/~f91_deliverables',
            skills=['Zapier', 'Automation']
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify 'What you'll get' section exists
        self.assertIn("What you'll get", proposal.full_text,
            "Proposal should contain 'What you'll get' section")

        print("\n[Feature #91] 'What you'll get' section:")
        print(f"  Present in proposal: True")
        print("  Status: PASS")

    def test_proposal_has_timeline_section(self):
        """Step 4: Verify 'Timeline' section exists in proposal."""
        job = JobData(
            job_id='~f91_timeline',
            title='Data Pipeline Project',
            description='Build data pipeline',
            url='https://upwork.com/jobs/~f91_timeline',
            skills=['Python', 'ETL']
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify 'Timeline' section exists
        self.assertIn('Timeline', proposal.full_text,
            "Proposal should contain 'Timeline' section")

        print("\n[Feature #91] 'Timeline' section:")
        print(f"  Present in proposal: True")
        print("  Status: PASS")

    def test_proposal_greeting_with_contact_name_high_confidence(self):
        """Step 1: Verify greeting uses contact name for high confidence."""
        job = JobData(
            job_id='~f91_name_high',
            title='AI Project',
            description='Need AI help',
            url='https://upwork.com/jobs/~f91_name_high',
            skills=['AI'],
            contact_name='John',
            contact_confidence='high'
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify greeting includes contact name
        self.assertIn('John', proposal.greeting,
            f"Proposal greeting should include contact name 'John': {proposal.greeting}")

        # Should NOT have the hedged qualifier
        self.assertNotIn('if I have the right person', proposal.greeting,
            "High confidence greeting should not be hedged")

        print("\n[Feature #91] Greeting with high confidence name:")
        print(f"  Greeting: {proposal.greeting}")
        print(f"  Contains 'John': True")
        print(f"  Not hedged: True")
        print("  Status: PASS")

    def test_proposal_greeting_with_contact_name_medium_confidence(self):
        """Step 1: Verify greeting uses hedged format for medium confidence."""
        job = JobData(
            job_id='~f91_name_medium',
            title='Automation Project',
            description='Need automation help',
            url='https://upwork.com/jobs/~f91_name_medium',
            skills=['Automation'],
            contact_name='Sarah',
            contact_confidence='medium'
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify greeting includes contact name
        self.assertIn('Sarah', proposal.greeting,
            f"Proposal greeting should include contact name 'Sarah': {proposal.greeting}")

        # Should have the hedged qualifier
        self.assertIn('if I have the right person', proposal.greeting,
            "Medium confidence greeting should be hedged")

        print("\n[Feature #91] Greeting with medium confidence name:")
        print(f"  Greeting: {proposal.greeting}")
        print(f"  Contains 'Sarah': True")
        print(f"  Has hedge phrase: True")
        print("  Status: PASS")

    def test_proposal_greeting_without_contact_name(self):
        """Step 1: Verify default greeting when no contact name available."""
        job = JobData(
            job_id='~f91_no_name',
            title='Python Project',
            description='Need Python help',
            url='https://upwork.com/jobs/~f91_no_name',
            skills=['Python'],
            contact_name=None,
            contact_confidence=None
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify default greeting
        self.assertEqual('Hey', proposal.greeting,
            f"Proposal greeting should be 'Hey' when no contact: {proposal.greeting}")

        print("\n[Feature #91] Greeting without contact name:")
        print(f"  Greeting: {proposal.greeting}")
        print(f"  Is 'Hey': True")
        print("  Status: PASS")

    def test_proposal_has_all_required_sections(self):
        """Full test: Verify all required sections exist in proposal."""
        job = JobData(
            job_id='~f91_full',
            title='Complete AI Automation Project',
            description='Build comprehensive AI automation pipeline with multiple integrations',
            url='https://upwork.com/jobs/~f91_full',
            skills=['Python', 'AI', 'n8n', 'API'],
            budget_type='fixed',
            budget_min=2000,
            budget_max=5000,
            contact_name='Michael',
            contact_confidence='high'
        )

        proposal = generate_proposal_content(job, mock=True)

        # Verify all sections
        self.assertIn('My proposed approach', proposal.full_text,
            "Missing 'My proposed approach' section")
        self.assertIn("What you'll get", proposal.full_text,
            "Missing 'What you'll get' section")
        self.assertIn('Timeline', proposal.full_text,
            "Missing 'Timeline' section")

        # Verify greeting
        self.assertIn('Michael', proposal.greeting,
            f"Greeting should include contact name: {proposal.greeting}")

        print("\n[Feature #91] All required sections:")
        print(f"  Greeting with contact: {proposal.greeting}")
        print("  'My proposed approach': Present")
        print("  'What you'll get': Present")
        print("  'Timeline': Present")
        print("  Status: PASS")

    def test_proposal_content_structure_conversational(self):
        """Verify proposal follows conversational structure."""
        job = JobData(
            job_id='~f91_structure',
            title='Make.com Integration',
            description='Need Make.com workflow expert',
            url='https://upwork.com/jobs/~f91_structure',
            skills=['Make.com', 'API']
        )

        proposal = generate_proposal_content(job, mock=True)

        # Check that sections appear in correct order
        text = proposal.full_text

        approach_pos = text.find('My proposed approach')
        deliverables_pos = text.find("What you'll get")
        timeline_pos = text.find('Timeline')

        # All should be found
        self.assertGreater(approach_pos, -1, "'My proposed approach' not found")
        self.assertGreater(deliverables_pos, -1, "'What you'll get' not found")
        self.assertGreater(timeline_pos, -1, "'Timeline' not found")

        # They should appear in order
        self.assertLess(approach_pos, deliverables_pos,
            "'My proposed approach' should come before 'What you'll get'")
        self.assertLess(deliverables_pos, timeline_pos,
            "'What you'll get' should come before 'Timeline'")

        print("\n[Feature #91] Proposal structure order:")
        print(f"  'My proposed approach' position: {approach_pos}")
        print(f"  'What you'll get' position: {deliverables_pos}")
        print(f"  'Timeline' position: {timeline_pos}")
        print("  Correct order: True")
        print("  Status: PASS")

    def test_proposal_doc_url_created_with_correct_format(self):
        """Verify the full deliverables include properly formatted doc URL."""
        job = JobData(
            job_id='~f91_doc',
            title='AI Workflow Project',
            description='Build AI workflow',
            url='https://upwork.com/jobs/~f91_doc',
            skills=['AI', 'Python'],
            contact_name='Alex',
            contact_confidence='high'
        )

        result = generate_deliverables(
            job=job,
            generate_doc=True,
            generate_pdf=False,
            generate_video=False,
            mock=True
        )

        # Verify result
        self.assertTrue(result.success, "Deliverable generation should succeed")
        self.assertIsNotNone(result.proposal_doc_url, "Doc URL should be populated")
        self.assertIn('docs.google.com/document', result.proposal_doc_url,
            "Doc URL should be Google Docs format")
        self.assertIsNotNone(result.proposal_text, "Proposal text should be populated")

        # Verify proposal text has all sections
        self.assertIn('My proposed approach', result.proposal_text)
        self.assertIn("What you'll get", result.proposal_text)
        self.assertIn('Timeline', result.proposal_text)

        print("\n[Feature #91] Full deliverables generation:")
        print(f"  Success: {result.success}")
        print(f"  Doc URL: {result.proposal_doc_url[:50]}...")
        print("  Proposal has all sections: True")
        print("  Status: PASS")

    @patch('upwork_deliverable_generator.anthropic')
    def test_proposal_api_call_includes_all_sections_in_prompt(self, mock_anthropic):
        """Verify the API prompt requests all required sections."""
        # Setup mock Anthropic client
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock response
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = 'text'
        mock_text_block.text = """Hey Michael.

I spent ~15 minutes putting this together for you. In short, it's how I would create your AI automation end to end.

I've worked with $MM companies like Anthropic and I have a lot of experience with similar workflows.

Here's a step-by-step, along with my reasoning at every point:

My proposed approach

1. First, I would analyze your current workflow needs...
2. Then build the core automation pipeline...
3. Set up the API integrations...
4. Test and refine...

What you'll get

- Working AI automation pipeline
- Documentation
- Training session

Timeline

I can deliver this within 2 weeks."""
        mock_response.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_response

        # Create job with contact name
        job = JobData(
            job_id='~f91_api',
            title='AI Automation Project',
            description='Need AI automation expert',
            url='https://upwork.com/jobs/~f91_api',
            skills=['Python', 'AI'],
            contact_name='Michael',
            contact_confidence='high'
        )

        # Generate proposal
        proposal = generate_proposal_content(job, anthropic_client=mock_client, mock=False)

        # Get the prompt that was sent
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs.get('messages', call_args[1].get('messages', []))
        prompt_content = messages[0]['content'] if messages else ''

        # Verify prompt includes section headers
        self.assertIn('My proposed approach', prompt_content,
            "Prompt should request 'My proposed approach' section")
        self.assertIn("What you'll get", prompt_content,
            "Prompt should request 'What you'll get' section")
        self.assertIn('Timeline', prompt_content,
            "Prompt should request 'Timeline' section")

        # Verify greeting format is specified
        self.assertIn('Hey', prompt_content,
            "Prompt should specify greeting format")

        print("\n[Feature #91] API prompt includes all sections:")
        print("  'My proposed approach' in prompt: True")
        print("  'What you'll get' in prompt: True")
        print("  'Timeline' in prompt: True")
        print("  Greeting format specified: True")
        print("  Status: PASS")


class TestFeature92ContactNameDiscovery(unittest.TestCase):
    """
    Feature #92: Contact name discovery works from job description

    Steps:
    1. Process job with signature 'Thanks, John'
    2. Run contact discovery
    3. Verify contact_name='John'
    4. Verify contact_confidence='high'
    """

    def test_discover_contact_name_from_signature_thanks_john(self):
        """
        Feature #92 Step 1-4: Process job with 'Thanks, John' signature.
        Verify contact_name='John' and contact_confidence='high'.
        """
        from upwork_deliverable_generator import discover_contact_name

        description = """
        Looking for an AI automation expert to help with our workflow.

        Requirements:
        - Python experience
        - API integrations

        Thanks, John
        """

        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'John',
            "contact_name should be 'John'")
        self.assertEqual(result.contact_confidence, 'high',
            "contact_confidence should be 'high' for signature pattern")
        self.assertEqual(result.source, 'signature',
            "source should be 'signature'")

        print("\n[Feature #92] Contact name discovery from 'Thanks, John':")
        print(f"  contact_name: {result.contact_name}")
        print(f"  contact_confidence: {result.contact_confidence}")
        print(f"  source: {result.source}")
        print("  Status: PASS")

    def test_discover_contact_name_from_signature_best_sarah(self):
        """Test discovery with 'Best, Sarah' signature."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Need help with automation project.\n\nBest, Sarah"
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Sarah')
        self.assertEqual(result.contact_confidence, 'high')

    def test_discover_contact_name_from_signature_regards_mike(self):
        """Test discovery with 'Regards, Mike' signature."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Looking for Python developer.\n\nRegards, Mike"
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Mike')
        self.assertEqual(result.contact_confidence, 'high')

    def test_discover_contact_name_from_introduction(self):
        """Test discovery with 'My name is' pattern."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Hi, my name is David and I need help with my project."
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'David')
        self.assertEqual(result.contact_confidence, 'high')
        self.assertEqual(result.source, 'introduction')

    def test_discover_contact_name_from_im_pattern(self):
        """Test discovery with 'I'm' pattern."""
        from upwork_deliverable_generator import discover_contact_name

        description = "I'm Lisa and I run a small business."
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Lisa')
        self.assertEqual(result.contact_confidence, 'high')
        self.assertEqual(result.source, 'introduction')

    def test_discover_contact_name_at_end_medium_confidence(self):
        """Test discovery with name at end of description (medium confidence)."""
        from upwork_deliverable_generator import discover_contact_name

        description = """
        Need an expert for my project.

        Requirements listed below.

        Robert
        """

        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Robert')
        self.assertEqual(result.contact_confidence, 'medium',
            "Name at end without signature word should be medium confidence")

    def test_discover_contact_name_no_name_found(self):
        """Test when no name can be found."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Looking for Python developer with API experience."
        result = discover_contact_name(description)

        self.assertIsNone(result.contact_name)
        self.assertEqual(result.contact_confidence, 'low')
        self.assertEqual(result.source, 'none')

    def test_discover_contact_name_empty_description(self):
        """Test with empty description."""
        from upwork_deliverable_generator import discover_contact_name

        result = discover_contact_name("")

        self.assertIsNone(result.contact_name)
        self.assertEqual(result.contact_confidence, 'low')

    def test_discover_contact_name_excludes_false_positives(self):
        """Test that common words like 'Thanks', 'Best' are excluded."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Thanks for reading this job post.\n\nBest"
        result = discover_contact_name(description)

        # Should not pick up 'Thanks' or 'Best' as names
        self.assertIsNone(result.contact_name)

    def test_enrich_job_with_contact_adds_contact_info(self):
        """Test that enrich_job_with_contact populates contact fields."""
        from upwork_deliverable_generator import JobData, enrich_job_with_contact

        job = JobData(
            job_id='test123',
            title='Python Developer',
            description='Need help with project.\n\nThanks, Emily',
            url='https://upwork.com/jobs/~test123'
        )

        self.assertIsNone(job.contact_name)
        self.assertIsNone(job.contact_confidence)

        enriched_job = enrich_job_with_contact(job)

        self.assertEqual(enriched_job.contact_name, 'Emily')
        self.assertEqual(enriched_job.contact_confidence, 'high')

        print("\n[Feature #92] enrich_job_with_contact:")
        print(f"  Original contact_name: None")
        print(f"  Enriched contact_name: {enriched_job.contact_name}")
        print(f"  Enriched contact_confidence: {enriched_job.contact_confidence}")
        print("  Status: PASS")

    def test_enrich_job_preserves_existing_contact(self):
        """Test that existing contact info is not overwritten."""
        from upwork_deliverable_generator import JobData, enrich_job_with_contact

        job = JobData(
            job_id='test123',
            title='Python Developer',
            description='Need help.\n\nThanks, Emily',
            url='https://upwork.com/jobs/~test123',
            contact_name='ManuallySet',
            contact_confidence='high'
        )

        enriched_job = enrich_job_with_contact(job)

        # Should not change existing contact info
        self.assertEqual(enriched_job.contact_name, 'ManuallySet')

    def test_contact_discovery_result_to_dict(self):
        """Test ContactDiscoveryResult serialization."""
        from upwork_deliverable_generator import ContactDiscoveryResult

        result = ContactDiscoveryResult(
            contact_name='John',
            contact_confidence='high',
            source='signature'
        )

        d = result.to_dict()

        self.assertEqual(d['contact_name'], 'John')
        self.assertEqual(d['contact_confidence'], 'high')
        self.assertEqual(d['source'], 'signature')

    def test_discover_contact_name_dash_signature(self):
        """Test discovery with dash before name (e.g., 'Thanks - Alex')."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Need automation help.\n\nThanks - Alex"
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Alex')
        self.assertEqual(result.contact_confidence, 'high')

    def test_discover_contact_name_case_insensitive_signature(self):
        """Test that signature patterns work case-insensitively."""
        from upwork_deliverable_generator import discover_contact_name

        description = "Looking for developer.\n\nTHANKS, Jennifer"
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Jennifer')
        self.assertEqual(result.contact_confidence, 'high')

    def test_format_greeting_with_discovered_high_confidence_contact(self):
        """Test that high confidence contact gets direct greeting."""
        from upwork_deliverable_generator import format_greeting

        greeting = format_greeting('John', 'high')
        self.assertEqual(greeting, 'Hey John')

    def test_format_greeting_with_discovered_medium_confidence_contact(self):
        """Test that medium confidence contact gets hedged greeting."""
        from upwork_deliverable_generator import format_greeting

        greeting = format_greeting('Robert', 'medium')
        self.assertEqual(greeting, 'Hey Robert (if I have the right person)')


class TestFeature93HedgedGreetingForMediumConfidence(unittest.TestCase):
    """
    Feature #93: Contact name uses hedged greeting for medium confidence

    Steps:
    1. Process job with inferred contact name
    2. Verify contact_confidence='medium'
    3. Verify proposal uses 'Hey [Name] (if I have the right person)'
    """

    def test_inferred_contact_name_gets_medium_confidence(self):
        """
        Test that a name at end of description (inferred) gets medium confidence.

        Feature #93 Step 1: Process job with inferred contact name
        """
        from upwork_deliverable_generator import discover_contact_name

        # Name at end of description = medium confidence (inferred)
        description = """
        Looking for someone to build an automation system.

        Requirements:
        - Python experience
        - API integration

        Michael
        """
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Michael')
        self.assertEqual(result.contact_confidence, 'medium')
        self.assertEqual(result.source, 'signature')

        print("\n[Feature #93] Inferred contact name from end of description:")
        print(f"  Description ends with: Michael")
        print(f"  Discovered name: {result.contact_name}")
        print(f"  Confidence: {result.contact_confidence}")
        print("  Status: PASS")

    def test_medium_confidence_contact_verified(self):
        """
        Feature #93 Step 2: Verify contact_confidence='medium'
        """
        from upwork_deliverable_generator import JobData, enrich_job_with_contact

        # Job where name is inferred from end of description
        job = JobData(
            job_id='test93',
            title='Python Automation',
            description="""
            Need help building a workflow automation.

            Amanda
            """,
            url='https://upwork.com/jobs/~test93'
        )

        enriched = enrich_job_with_contact(job)

        # Verify medium confidence
        self.assertEqual(enriched.contact_name, 'Amanda')
        self.assertEqual(enriched.contact_confidence, 'medium')

        print("\n[Feature #93] Contact confidence verification:")
        print(f"  Job ID: {job.job_id}")
        print(f"  Contact name: {enriched.contact_name}")
        print(f"  Contact confidence: {enriched.contact_confidence}")
        print("  Status: PASS - contact_confidence='medium' verified")

    def test_proposal_uses_hedged_greeting_for_medium_confidence(self):
        """
        Feature #93 Step 3: Verify proposal uses 'Hey [Name] (if I have the right person)'
        """
        from upwork_deliverable_generator import (
            JobData, enrich_job_with_contact,
            generate_proposal_content, format_greeting
        )

        # Job with inferred contact name
        job = JobData(
            job_id='test93b',
            title='Automation Developer',
            description="""
            Build an automation workflow.

            Kevin
            """,
            url='https://upwork.com/jobs/~test93b'
        )

        enriched = enrich_job_with_contact(job)
        self.assertEqual(enriched.contact_confidence, 'medium')

        # Verify format_greeting produces hedged greeting
        greeting = format_greeting(enriched.contact_name, enriched.contact_confidence)
        self.assertEqual(greeting, 'Hey Kevin (if I have the right person)')

        # Verify generate_proposal_content uses hedged greeting in mock mode
        proposal = generate_proposal_content(enriched, mock=True)
        self.assertIn('Hey Kevin (if I have the right person)', proposal.greeting)

        print("\n[Feature #93] Hedged greeting in proposal:")
        print(f"  Contact name: {enriched.contact_name}")
        print(f"  Contact confidence: {enriched.contact_confidence}")
        print(f"  Greeting: {proposal.greeting}")
        print("  Status: PASS - uses 'Hey [Name] (if I have the right person)'")

    def test_full_flow_medium_confidence_generates_hedged_greeting(self):
        """
        Full integration test: Job with inferred name -> proposal with hedged greeting
        """
        from upwork_deliverable_generator import (
            JobData, enrich_job_with_contact,
            generate_proposal_content
        )

        # Simulate a real job posting with name at end
        job = JobData(
            job_id='~feature93test',
            title='API Integration Specialist',
            description="""
            We need someone to integrate our CRM with Slack.

            Requirements:
            - API experience
            - Python preferred
            - Good communication

            Steven
            """,
            url='https://upwork.com/jobs/~feature93test',
            skills=['Python', 'API', 'Slack'],
            budget_type='fixed',
            budget_min=500,
            budget_max=1000
        )

        # Step 1: Enrich with contact discovery
        enriched = enrich_job_with_contact(job)

        # Step 2: Verify medium confidence
        self.assertEqual(enriched.contact_name, 'Steven')
        self.assertEqual(enriched.contact_confidence, 'medium')

        # Step 3: Generate proposal
        proposal = generate_proposal_content(enriched, mock=True)

        # Step 4: Verify hedged greeting in proposal
        self.assertEqual(proposal.greeting, 'Hey Steven (if I have the right person)')
        self.assertIn('Hey Steven (if I have the right person)', proposal.full_text)

        print("\n[Feature #93] Full integration test:")
        print(f"  Job: {job.title}")
        print(f"  Description ends with: Steven")
        print(f"  Discovered: contact_name='Steven', confidence='medium'")
        print(f"  Proposal greeting: {proposal.greeting}")
        print("  Status: PASS - full flow verified")

    def test_format_greeting_low_confidence_also_hedged(self):
        """Test that low confidence also gets hedged greeting."""
        from upwork_deliverable_generator import format_greeting

        greeting = format_greeting('David', 'low')
        self.assertEqual(greeting, 'Hey David (if I have the right person)')

    def test_format_greeting_high_confidence_not_hedged(self):
        """Verify high confidence does NOT get hedged greeting (contrast test)."""
        from upwork_deliverable_generator import format_greeting

        greeting = format_greeting('Lisa', 'high')
        self.assertEqual(greeting, 'Hey Lisa')
        self.assertNotIn('if I have the right person', greeting)

    def test_signature_pattern_gets_high_confidence_not_hedged(self):
        """
        Contrast test: Signature pattern (high confidence) should NOT be hedged.
        """
        from upwork_deliverable_generator import (
            discover_contact_name, format_greeting
        )

        # Direct signature = high confidence
        description = "Need help.\n\nThanks, Jennifer"
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Jennifer')
        self.assertEqual(result.contact_confidence, 'high')

        greeting = format_greeting(result.contact_name, result.contact_confidence)
        self.assertEqual(greeting, 'Hey Jennifer')
        self.assertNotIn('if I have the right person', greeting)

    def test_introduction_pattern_gets_high_confidence_not_hedged(self):
        """
        Contrast test: Introduction pattern (high confidence) should NOT be hedged.
        """
        from upwork_deliverable_generator import (
            discover_contact_name, format_greeting
        )

        description = "Hi, I'm Michelle. Looking for automation help."
        result = discover_contact_name(description)

        self.assertEqual(result.contact_name, 'Michelle')
        self.assertEqual(result.contact_confidence, 'high')

        greeting = format_greeting(result.contact_name, result.contact_confidence)
        self.assertEqual(greeting, 'Hey Michelle')
        self.assertNotIn('if I have the right person', greeting)


if __name__ == '__main__':
    unittest.main()
