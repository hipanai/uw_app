import { useState, useEffect, useRef } from 'react';
import {
  getPendingApprovals,
  approveJob,
  rejectJob,
  updateProposal,
  getSubmissionMode,
  getActiveVideoGenerations,
  getJobs,
  submitJob,
  updateJobStatus,
  type SubmissionModeResponse,
} from '@/api/jobs';
import { getAuthToken } from '@/api/client';
import type { Job, VideoGenerationStatus } from '@/api/types';
import { STATUS_COLORS, STATUS_LABELS, getScoreColor } from '@/lib/constants';
import { formatBudget, formatDate, formatClientSpent } from '@/lib/utils';

// Helper to convert local file paths to API URLs
const getVideoUrl = (url: string | null | undefined, jobId: string | undefined): string | null => {
  if (!url) return null;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.includes('.tmp') || url.includes('composed_') || url.endsWith('.mp4')) {
    const token = getAuthToken();
    return `/api/files/video/${jobId}${token ? `?token=${token}` : ''}`;
  }
  return url;
};

const getPdfUrl = (url: string | null | undefined, jobId: string | undefined): string | null => {
  if (!url) return null;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.includes('.tmp') || url.includes('proposal_') || url.endsWith('.pdf')) {
    const token = getAuthToken();
    return `/api/files/pdf/${jobId}${token ? `?token=${token}` : ''}`;
  }
  return url;
};

export function Approval() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [approvedJobs, setApprovedJobs] = useState<Job[]>([]);
  const [videoGenerations, setVideoGenerations] = useState<Record<string, VideoGenerationStatus>>({});
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [editedProposal, setEditedProposal] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submissionMode, setSubmissionMode] = useState<SubmissionModeResponse | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  // State for approved jobs expansion
  const [expandedApprovedJob, setExpandedApprovedJob] = useState<string | null>(null);
  const [approvedJobProposal, setApprovedJobProposal] = useState('');
  const [savingApprovedProposal, setSavingApprovedProposal] = useState(false);
  const [submittedJobs, setSubmittedJobs] = useState<Job[]>([]);
  const [markingSubmitted, setMarkingSubmitted] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const fetchPending = async () => {
    setLoading(true);
    try {
      const pending = await getPendingApprovals();
      setJobs(pending);
      if (pending.length > 0 && !selectedJob) {
        setSelectedJob(pending[0]);
        setEditedProposal(pending[0].proposal_text || '');
      }
    } catch (err) {
      console.error('Failed to fetch pending approvals:', err);
      setError('Failed to load pending approvals');
    } finally {
      setLoading(false);
    }
  };

  const fetchApprovedJobs = async () => {
    try {
      // Fetch approved jobs that have video generation in progress or completed
      const response = await getJobs({ status: 'approved', per_page: 20 });
      setApprovedJobs(response.jobs);
    } catch (err) {
      console.error('Failed to fetch approved jobs:', err);
    }
  };

  const fetchSubmittedJobs = async () => {
    try {
      const response = await getJobs({ status: 'submitted', per_page: 20 });
      setSubmittedJobs(response.jobs);
    } catch (err) {
      console.error('Failed to fetch submitted jobs:', err);
    }
  };

  const fetchVideoGenerations = async () => {
    try {
      const response = await getActiveVideoGenerations();
      // Convert array to record keyed by job_id
      const genMap: Record<string, VideoGenerationStatus> = {};
      for (const gen of response.video_generations) {
        genMap[gen.job_id] = gen;
      }
      setVideoGenerations(genMap);
    } catch (err) {
      console.error('Failed to fetch video generations:', err);
    }
  };

  useEffect(() => {
    fetchPending();
    fetchApprovedJobs();
    fetchSubmittedJobs();
    fetchVideoGenerations();
    getSubmissionMode().then(setSubmissionMode).catch(console.error);

    // Poll for video generation updates
    const interval = setInterval(() => {
      fetchVideoGenerations();
      fetchApprovedJobs();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const selectJob = (job: Job) => {
    setSelectedJob(job);
    setEditedProposal(job.proposal_text || '');
    setError(null);
    setSuccess(null);
  };

  const handleApprove = async () => {
    if (!selectedJob) return;
    setActionLoading('approve');
    setError(null);
    try {
      // Save any edits first
      if (editedProposal !== selectedJob.proposal_text) {
        await updateProposal(selectedJob.job_id, editedProposal);
      }
      await approveJob(selectedJob.job_id);
      setSuccess('Job approved successfully!');
      // Remove from list and select next
      const remaining = jobs.filter((j) => j.job_id !== selectedJob.job_id);
      setJobs(remaining);
      if (remaining.length > 0) {
        selectJob(remaining[0]);
      } else {
        setSelectedJob(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async () => {
    if (!selectedJob) return;
    setActionLoading('reject');
    setError(null);
    try {
      await rejectJob(selectedJob.job_id);
      setSuccess('Job rejected');
      // Remove from list and select next
      const remaining = jobs.filter((j) => j.job_id !== selectedJob.job_id);
      setJobs(remaining);
      if (remaining.length > 0) {
        selectJob(remaining[0]);
      } else {
        setSelectedJob(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSaveProposal = async () => {
    if (!selectedJob) return;
    setActionLoading('save');
    setError(null);
    try {
      await updateProposal(selectedJob.job_id, editedProposal);
      setSuccess('Proposal saved');
      // Update local state
      setJobs((prev) =>
        prev.map((j) =>
          j.job_id === selectedJob.job_id
            ? { ...j, proposal_text: editedProposal }
            : j
        )
      );
      setSelectedJob((prev) =>
        prev ? { ...prev, proposal_text: editedProposal } : prev
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save proposal');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSubmitJob = async (jobId: string) => {
    if (!confirm('Submit this proposal to Upwork?')) return;
    setSubmitting(jobId);
    try {
      await submitJob(jobId);
      setSuccess('Job submitted successfully!');
      fetchApprovedJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit job');
    } finally {
      setSubmitting(null);
    }
  };

  const toggleApprovedJobExpand = (job: Job) => {
    if (expandedApprovedJob === job.job_id) {
      setExpandedApprovedJob(null);
    } else {
      setExpandedApprovedJob(job.job_id);
      setApprovedJobProposal(job.proposal_text || '');
    }
  };

  const handleSaveApprovedProposal = async (jobId: string) => {
    setSavingApprovedProposal(true);
    try {
      await updateProposal(jobId, approvedJobProposal);
      setSuccess('Cover letter saved');
      // Update local state
      setApprovedJobs((prev) =>
        prev.map((j) =>
          j.job_id === jobId ? { ...j, proposal_text: approvedJobProposal } : j
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save cover letter');
    } finally {
      setSavingApprovedProposal(false);
    }
  };

  const insertVideoLink = (videoUrl: string) => {
    if (!videoUrl) return;
    // Only insert permanent URLs (Google Drive) - never temporary HeyGen or local paths
    if (!videoUrl.includes('drive.google.com')) return;

    // Find the end of the first paragraph (first double newline or after ~200 chars)
    const firstParagraphEnd = approvedJobProposal.indexOf('\n\n');
    const insertPosition = firstParagraphEnd > 0 && firstParagraphEnd < 500
      ? firstParagraphEnd
      : Math.min(approvedJobProposal.indexOf('.') + 1, 200);

    const videoLinkText = `\n\n🎥 I've created a short personalized video for you: ${videoUrl}\n`;

    if (insertPosition > 0 && insertPosition < approvedJobProposal.length) {
      const newProposal =
        approvedJobProposal.slice(0, insertPosition) +
        videoLinkText +
        approvedJobProposal.slice(insertPosition);
      setApprovedJobProposal(newProposal);
    } else {
      // Fallback: insert at the beginning after first line
      const firstLineEnd = approvedJobProposal.indexOf('\n');
      if (firstLineEnd > 0) {
        setApprovedJobProposal(
          approvedJobProposal.slice(0, firstLineEnd) +
          videoLinkText +
          approvedJobProposal.slice(firstLineEnd)
        );
      } else {
        setApprovedJobProposal(videoLinkText + '\n' + approvedJobProposal);
      }
    }
    setSuccess('Video link inserted into cover letter');
  };

  const handleMarkAsSubmitted = async (jobId: string) => {
    if (!confirm('Mark this job as submitted?')) return;
    setMarkingSubmitted(jobId);
    try {
      await updateJobStatus(jobId, 'submitted');
      setSuccess('Job marked as submitted');
      // Move from approved to submitted
      const job = approvedJobs.find(j => j.job_id === jobId);
      if (job) {
        setApprovedJobs(prev => prev.filter(j => j.job_id !== jobId));
        setSubmittedJobs(prev => [{ ...job, status: 'submitted' }, ...prev]);
      }
      if (expandedApprovedJob === jobId) {
        setExpandedApprovedJob(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status');
    } finally {
      setMarkingSubmitted(null);
    }
  };

  const getVideoStatus = (jobId: string) => {
    return videoGenerations[jobId];
  };

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Approval Queue</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  const getModeIndicator = () => {
    if (!submissionMode) return null;
    const modeColors: Record<string, string> = {
      manual: 'bg-blue-100 text-blue-800 border-blue-300',
      semi_auto: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      automatic: 'bg-green-100 text-green-800 border-green-300',
    };
    const modeLabels: Record<string, string> = {
      manual: 'Manual Mode',
      semi_auto: 'Semi-Auto Mode',
      automatic: 'Automatic Mode',
    };
    return (
      <span className={`ml-3 px-3 py-1 rounded-full border text-sm font-medium ${modeColors[submissionMode.mode]}`}>
        {modeLabels[submissionMode.mode]}
      </span>
    );
  };

  const getApproveButtonText = () => {
    if (actionLoading === 'approve') return 'Processing...';
    switch (submissionMode?.mode) {
      case 'automatic':
        return 'Approve → Generate Video → Submit';
      case 'semi_auto':
        return 'Approve & Generate Video';
      default:
        return 'Approve & Generate Video';
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center mb-6">
        <h1 className="text-2xl font-bold dark:text-white">
          Approval Queue
          <span className="ml-2 text-sm font-normal text-gray-500">
            ({jobs.length} pending)
          </span>
        </h1>
        {getModeIndicator()}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-100 text-green-700 rounded-md">
          {success}
        </div>
      )}

      {jobs.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 text-center text-gray-500 dark:text-gray-400">
          No jobs pending approval. Check back later!
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Job List */}
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
              <div className="p-3 bg-gray-50 dark:bg-gray-700 border-b dark:border-gray-600 font-medium dark:text-white">
                Pending Jobs
              </div>
              <ul className="divide-y divide-gray-200 dark:divide-gray-700 max-h-[600px] overflow-y-auto">
                {jobs.map((job) => (
                  <li
                    key={job.job_id}
                    onClick={() => selectJob(job)}
                    className={`p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${
                      selectedJob?.job_id === job.job_id ? 'bg-blue-50 dark:bg-blue-900/30' : ''
                    }`}
                  >
                    <p className="font-medium text-sm truncate dark:text-white">{job.title}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`px-2 py-0.5 text-xs rounded ${getScoreColor(job.fit_score)}`}
                      >
                        Score: {job.fit_score ?? 'N/A'}
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatBudget(job.budget_type, job.budget_min, job.budget_max)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Job Details & Proposal Editor */}
          <div className="lg:col-span-2 space-y-4">
            {selectedJob && (
              <>
                {/* Job Details */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h2 className="text-lg font-semibold dark:text-white">{selectedJob.title}</h2>
                      <a
                        href={selectedJob.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline text-sm"
                      >
                        View on Upwork
                      </a>
                    </div>
                    <span className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[selectedJob.status]}`}>
                      {STATUS_LABELS[selectedJob.status]}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">Fit Score</p>
                      <p className={`font-semibold px-2 py-0.5 rounded inline-block ${getScoreColor(selectedJob.fit_score)}`}>
                        {selectedJob.fit_score ?? 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">Budget</p>
                      <p className="font-semibold dark:text-white">
                        {formatBudget(selectedJob.budget_type, selectedJob.budget_min, selectedJob.budget_max)}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">Client Spent</p>
                      <p className="font-semibold dark:text-white">{formatClientSpent(selectedJob.client_spent)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400">Posted</p>
                      <p className="font-semibold dark:text-white">{formatDate(selectedJob.posted_date)}</p>
                    </div>
                  </div>

                  <div className="border-t dark:border-gray-700 pt-4">
                    <p className="text-gray-500 text-sm mb-2">Job Description</p>
                    <p className="text-sm whitespace-pre-wrap max-h-40 overflow-y-auto dark:text-gray-300">
                      {selectedJob.description || 'No description available'}
                    </p>
                  </div>

                  {selectedJob.score_reasoning && (
                    <div className="border-t dark:border-gray-700 pt-4 mt-4">
                      <p className="text-gray-500 text-sm mb-2">Score Reasoning</p>
                      <p className="text-sm whitespace-pre-wrap dark:text-gray-300">
                        {selectedJob.score_reasoning}
                      </p>
                    </div>
                  )}
                </div>

                {/* Cover Letter Editor */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="font-semibold dark:text-white">Cover Letter</h3>
                    <button
                      onClick={handleSaveProposal}
                      disabled={actionLoading === 'save' || editedProposal === selectedJob.proposal_text}
                      className="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 rounded disabled:opacity-50"
                    >
                      {actionLoading === 'save' ? 'Saving...' : 'Save Changes'}
                    </button>
                  </div>
                  <textarea
                    value={editedProposal}
                    onChange={(e) => setEditedProposal(e.target.value)}
                    className="w-full h-64 p-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="No cover letter generated yet"
                  />
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3">
                  <button
                    onClick={handleApprove}
                    disabled={actionLoading !== null}
                    className={`flex-1 text-white py-3 px-4 rounded-md disabled:opacity-50 font-medium ${
                      submissionMode?.mode === 'automatic'
                        ? 'bg-green-600 hover:bg-green-700'
                        : 'bg-blue-600 hover:bg-blue-700'
                    }`}
                  >
                    {getApproveButtonText()}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={actionLoading !== null}
                    className="flex-1 bg-red-600 text-white py-3 px-4 rounded-md hover:bg-red-700 disabled:opacity-50 font-medium"
                  >
                    {actionLoading === 'reject' ? 'Rejecting...' : 'Reject'}
                  </button>
                </div>

                {/* Mode-specific info */}
                {submissionMode?.mode !== 'automatic' && (
                  <p className="text-sm text-gray-500 mt-2">
                    After approval, video will be generated. You can then submit from the Dashboard.
                  </p>
                )}
                {submissionMode?.mode === 'automatic' && (
                  <p className="text-sm text-green-600 mt-2">
                    Full automatic mode: Job will be approved, video generated, and submitted to Upwork automatically.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Approved Jobs with Video Generation Status */}
      {approvedJobs.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xl font-bold mb-4 dark:text-white">
            Approved Jobs - Video Generation
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({approvedJobs.length} jobs)
            </span>
          </h2>
          <div className="space-y-4">
            {approvedJobs.map((job) => {
              const videoStatus = getVideoStatus(job.job_id);
              const isVideoReady = videoStatus?.status === 'completed';
              const isVideoFailed = videoStatus?.status === 'failed';
              const isGenerating = videoStatus?.status === 'in_progress' || videoStatus?.status === 'pending';
              const isExpanded = expandedApprovedJob === job.job_id;

              return (
                <div key={job.job_id} className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
                  {/* Header - always visible */}
                  <div
                    onClick={() => toggleApprovedJobExpand(job)}
                    className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium dark:text-white truncate">
                          {job.title}
                        </div>
                        <div className="text-xs text-gray-500">
                          {formatBudget(job.budget_type, job.budget_min, job.budget_max)}
                        </div>
                      </div>
                      {/* Video Status Badge */}
                      <div className="flex items-center gap-2">
                        {!videoStatus && (
                          <span className="px-2 py-1 text-xs rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                            Queued
                          </span>
                        )}
                        {isGenerating && (
                          <span className="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 animate-pulse">
                            {videoStatus?.stage || 'Generating...'}
                          </span>
                        )}
                        {isVideoReady && (
                          <span className="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                            Ready
                          </span>
                        )}
                        {isVideoFailed && (
                          <span className="px-2 py-1 text-xs rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                            Failed
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Action buttons */}
                    <div className="flex items-center gap-2 ml-4">
                      {submissionMode?.mode !== 'automatic' && isVideoReady && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleSubmitJob(job.job_id); }}
                          disabled={submitting === job.job_id}
                          className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                        >
                          {submitting === job.job_id ? 'Submitting...' : 'Submit'}
                        </button>
                      )}
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className={`h-5 w-5 text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>

                  {/* Expanded content */}
                  {isExpanded && (
                    <div className="border-t dark:border-gray-700">
                      {/* Video Generation Logs */}
                      {(isGenerating || isVideoFailed) && videoStatus?.logs && videoStatus.logs.length > 0 && (
                        <div className="bg-gray-900 text-gray-100 p-3 font-mono text-xs max-h-40 overflow-y-auto">
                          {videoStatus.logs.map((log, idx) => (
                            <div key={idx} className={`py-0.5 ${
                              log.includes('ERROR') || log.includes('Failed') ? 'text-red-400' :
                              log.includes('SUCCESS') || log.includes('successfully') ? 'text-green-400' :
                              log.includes('Starting') || log.includes('Generating') || log.includes('Calling') ? 'text-blue-400' :
                              'text-gray-300'
                            }`}>
                              {log}
                            </div>
                          ))}
                          <div ref={logEndRef} />
                        </div>
                      )}

                      {/* Error Display */}
                      {isVideoFailed && videoStatus?.error && (
                        <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm">
                          <span className="font-medium">Error:</span> {videoStatus.error}
                        </div>
                      )}

                      {/* Video/PDF Links when ready */}
                      {isVideoReady && (
                        <div className="px-4 py-3 bg-green-50 dark:bg-green-900/20 flex items-center justify-between">
                          <span className="text-green-700 dark:text-green-400 text-sm font-medium">Video generated successfully!</span>
                          <div className="flex items-center gap-2">
                            {videoStatus?.video_url && (
                              <a
                                href={getVideoUrl(videoStatus.video_url, job.job_id)!}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                  <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
                                </svg>
                                Watch Video
                              </a>
                            )}
                            {job.pdf_url && (
                              <a
                                href={getPdfUrl(job.pdf_url, job.job_id)!}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                  <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                                </svg>
                                View PDF
                              </a>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Cover Letter Editor */}
                      <div className="p-4">
                        <div className="flex justify-between items-center mb-2">
                          <h4 className="font-medium text-sm dark:text-white">Cover Letter</h4>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => videoStatus?.video_url && insertVideoLink(videoStatus.video_url)}
                              disabled={!isVideoReady || !videoStatus?.video_url || !videoStatus.video_url.includes('drive.google.com')}
                              className="px-3 py-1 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                              title={!isVideoReady ? 'Video not ready yet' : !videoStatus?.video_url?.includes('drive.google.com') ? 'Waiting for permanent Drive URL...' : 'Insert video link into cover letter'}
                            >
                              Insert Video Link
                            </button>
                            <button
                              onClick={() => handleSaveApprovedProposal(job.job_id)}
                              disabled={savingApprovedProposal || approvedJobProposal === job.proposal_text}
                              className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded disabled:opacity-50 dark:text-white"
                            >
                              {savingApprovedProposal ? 'Saving...' : 'Save Changes'}
                            </button>
                          </div>
                        </div>
                        <textarea
                          value={approvedJobProposal}
                          onChange={(e) => setApprovedJobProposal(e.target.value)}
                          className="w-full h-48 p-3 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="No cover letter generated yet"
                        />
                      </div>

                      {/* Bottom action bar */}
                      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 flex items-center justify-between">
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline text-sm"
                        >
                          View on Upwork
                        </a>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleMarkAsSubmitted(job.job_id)}
                            disabled={markingSubmitted === job.job_id}
                            className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50 font-medium"
                          >
                            {markingSubmitted === job.job_id ? 'Updating...' : 'Mark as Submitted'}
                          </button>
                          {submissionMode?.mode !== 'automatic' && (
                            <button
                              onClick={() => handleSubmitJob(job.job_id)}
                              disabled={submitting === job.job_id || !isVideoReady}
                              className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                              title={!isVideoReady ? 'Video not ready yet' : 'Submit to Upwork'}
                            >
                              {submitting === job.job_id ? 'Submitting...' : 'Submit to Upwork'}
                            </button>
                          )}
                          {submissionMode?.mode === 'automatic' && isVideoReady && (
                            <span className="text-sm text-green-600">Auto-submitting...</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Submission Completed Section */}
      {submittedJobs.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xl font-bold mb-4 dark:text-white">
            Submission Completed
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({submittedJobs.length} jobs)
            </span>
          </h2>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Job
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Budget
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Links
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {submittedJobs.map((job) => (
                  <tr key={job.job_id}>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium dark:text-white truncate max-w-md">
                        {job.title}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      {formatBudget(job.budget_type, job.budget_min, job.budget_max)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                        Submitted
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline text-sm"
                        >
                          View on Upwork
                        </a>
                        {job.video_url && (
                          <a
                            href={getVideoUrl(job.video_url, job.job_id)!}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-red-600 hover:underline text-sm"
                          >
                            Video
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
