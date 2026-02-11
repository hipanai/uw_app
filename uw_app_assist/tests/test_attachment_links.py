"""Tests for embed_attachment_links()."""

from uw_app_assist.submitter.attachment_links import embed_attachment_links


PROPOSAL = "I'd love to help with your project."


def test_both_urls_appended():
    result = embed_attachment_links(
        PROPOSAL,
        video_url="https://cdn.heygen.com/video123.mp4",
        pdf_url="https://drive.google.com/file/d/abc/view",
    )
    assert PROPOSAL in result
    assert "Video introduction: https://cdn.heygen.com/video123.mp4" in result
    assert "Portfolio/resume: https://drive.google.com/file/d/abc/view" in result
    assert "---" in result


def test_only_video():
    result = embed_attachment_links(
        PROPOSAL,
        video_url="https://cdn.heygen.com/video123.mp4",
    )
    assert "Video introduction:" in result
    assert "Portfolio/resume:" not in result


def test_only_pdf():
    result = embed_attachment_links(
        PROPOSAL,
        pdf_url="https://drive.google.com/file/d/abc/view",
    )
    assert "Portfolio/resume:" in result
    assert "Video introduction:" not in result


def test_no_urls_returns_original():
    result = embed_attachment_links(PROPOSAL)
    assert result == PROPOSAL


def test_none_values_returns_original():
    result = embed_attachment_links(PROPOSAL, video_url=None, pdf_url=None)
    assert result == PROPOSAL


def test_empty_strings_returns_original():
    result = embed_attachment_links(PROPOSAL, video_url="", pdf_url="")
    assert result == PROPOSAL


def test_local_paths_ignored():
    result = embed_attachment_links(
        PROPOSAL,
        video_url="C:/tmp/video.mp4",
        pdf_url="/home/user/resume.pdf",
    )
    assert result == PROPOSAL


def test_local_path_mixed_with_url():
    result = embed_attachment_links(
        PROPOSAL,
        video_url="/local/path/video.mp4",
        pdf_url="https://drive.google.com/file/d/abc/view",
    )
    assert "Video introduction:" not in result
    assert "Portfolio/resume:" in result
