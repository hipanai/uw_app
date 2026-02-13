import React, { useState, useEffect, useRef } from 'react';
import { getJobs, getJobStats, deleteJob, deleteJobsBulk, processJobs, updateJobStatus, updateJobStatusBulk, getActiveSubmissions, getSubmissionMode, submitJob, approveJob, updateProposal, dismissSubmission, type SubmissionStatus, type SubmissionModeResponse } from '@/api/jobs';
import type { Job, JobStatsResponse, JobStatus } from '@/api/types';
import { STATUS_COLORS, STATUS_LABELS, getScoreColor } from '@/lib/constants';
import { formatBudget, truncateText } from '@/lib/utils';
import { getAuthToken } from '@/api/client';

// Helper to convert local file paths to API URLs (with auth token for file endpoints)
const getVideoUrl = (url: string | null | undefined, jobId: string | undefined): string | null => {
  if (!url) return null;
  // If it's already a full URL (http/https), return as-is
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  // If it's a local file path, convert to API endpoint with auth token
  if (url.includes('.tmp') || url.includes('composed_') || url.endsWith('.mp4')) {
    const token = getAuthToken();
    return `/api/files/video/${jobId}${token ? `?token=${token}` : ''}`;
  }
  return url;
};

const getPdfUrl = (url: string | null | undefined, jobId: string | undefined): string | null => {
  if (!url) return null;
  // If it's already a full URL (http/https), return as-is
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  // If it's a local file path, convert to API endpoint with auth token
  if (url.includes('.tmp') || url.includes('proposal_') || url.endsWith('.pdf')) {
    const token = getAuthToken();
    return `/api/files/pdf/${jobId}${token ? `?token=${token}` : ''}`;
  }
  return url;
};

// Helper to get Upwork job URL - constructs from job_id if url is missing
const getUpworkUrl = (url: string | null | undefined, jobId: string | undefined): string => {
  if (url && url.startsWith('http')) return url;
  if (jobId) {
    // Upwork job URLs follow pattern: https://www.upwork.com/jobs/~02{job_id}
    const cleanId = String(jobId).replace(/^0+/, ''); // Remove leading zeros if any
    return `https://www.upwork.com/jobs/~02${cleanId}`;
  }
  return '#';
};

type SortColumn = 'job_id' | 'title' | 'status' | 'fit_score' | 'budget' | 'source';
type SortDirection = 'asc' | 'desc';

export function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [search, setSearch] = useState('');
  const [selectedJobs, setSelectedJobs] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [activeSubmissions, setActiveSubmissions] = useState<Record<string, SubmissionStatus>>({});
  const [showSubmissions, setShowSubmissions] = useState(true);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [submissionMode, setSubmissionMode] = useState<SubmissionModeResponse | null>(null);
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [editingProposalJobId, setEditingProposalJobId] = useState<string | null>(null);
  const [editedProposalText, setEditedProposalText] = useState('');
  const [savingProposal, setSavingProposal] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Statuses that belong on the Approval page, not Dashboard
  const APPROVAL_PAGE_STATUSES = ['pending_approval', 'approved', 'submitted'];

  const fetchData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const [jobsRes, statsRes] = await Promise.all([
        getJobs({
          status: statusFilter || undefined,
          search: search || undefined,
          per_page: 50
        }),
        getJobStats(),
      ]);
      // Filter out jobs that belong on the Approval page (unless specifically filtered)
      const filteredJobs = statusFilter
        ? jobsRes.jobs  // If user explicitly filters by status, show all matching
        : jobsRes.jobs.filter(j => !APPROVAL_PAGE_STATUSES.includes(j.status || ''));
      setJobs(filteredJobs);
      setStats(statsRes);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  // Initial fetch and filter changes
  useEffect(() => {
    fetchData();
  }, [statusFilter, search]);

  // Auto-refresh polling when enabled
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchData(false); // Don't show loading spinner on auto-refresh
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, [autoRefresh, statusFilter, search]);

  // Fetch active submissions
  const fetchSubmissions = async () => {
    try {
      const result = await getActiveSubmissions();
      setActiveSubmissions(result.submissions);
      // Auto-scroll to bottom of logs when new entries come in
      if (logEndRef.current) {
        logEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    } catch (err) {
      console.error('Failed to fetch submissions:', err);
    }
  };

  // Fetch submission mode
  const fetchSubmissionMode = async () => {
    try {
      const mode = await getSubmissionMode();
      setSubmissionMode(mode);
    } catch (err) {
      console.error('Failed to fetch submission mode:', err);
    }
  };

  // Poll for submission updates
  useEffect(() => {
    fetchSubmissions(); // Initial fetch
    fetchSubmissionMode(); // Initial fetch

    const interval = setInterval(() => {
      fetchSubmissions();
    }, 5000); // Poll every 5 seconds

    // Refresh mode less frequently
    const modeInterval = setInterval(() => {
      fetchSubmissionMode();
    }, 10000);

    return () => {
      clearInterval(interval);
      clearInterval(modeInterval);
    };
  }, []);

  const activeSubmissionCount = Object.keys(activeSubmissions).length;
  const hasInProgressSubmissions = Object.values(activeSubmissions).some(
    s => s.status === 'pending' || s.status === 'in_progress'
  );

  const getModeIndicator = () => {
    if (!submissionMode) return null;
    const modeColors = {
      manual: 'bg-blue-100 text-blue-800 border-blue-300',
      semi_auto: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      automatic: 'bg-green-100 text-green-800 border-green-300',
    };
    const modeLabels = {
      manual: 'Manual Mode',
      semi_auto: 'Semi-Auto Mode',
      automatic: 'Automatic Mode',
    };
    return (
      <div className={`px-3 py-1 rounded-full border text-sm font-medium ${modeColors[submissionMode.mode]}`}>
        {modeLabels[submissionMode.mode]}
      </div>
    );
  };

  const statuses: JobStatus[] = [
    'new', 'scoring', 'extracting', 'generating',
    'pending_approval', 'approved', 'rejected', 'shortlisted', 'submitting', 'submitted', 'submission_failed', 'filtered_out'
  ];

  const handleSelectJob = (jobId: string) => {
    const newSelected = new Set(selectedJobs);
    if (newSelected.has(jobId)) {
      newSelected.delete(jobId);
    } else {
      newSelected.add(jobId);
    }
    setSelectedJobs(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedJobs.size === jobs.length) {
      setSelectedJobs(new Set());
    } else {
      setSelectedJobs(new Set(jobs.map(j => j.job_id).filter(Boolean) as string[]));
    }
  };

  const handleDeleteSingle = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this job?')) return;

    setDeleting(true);
    try {
      await deleteJob(jobId);
      setJobs(jobs.filter(j => j.job_id !== jobId));
      setSelectedJobs(prev => {
        const newSet = new Set(prev);
        newSet.delete(jobId);
        return newSet;
      });
    } catch (err) {
      console.error('Failed to delete job:', err);
      alert('Failed to delete job');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteSelected = async (force: boolean = false) => {
    if (selectedJobs.size === 0) return;
    if (!force && !confirm(`Are you sure you want to delete ${selectedJobs.size} job(s)?`)) return;

    setDeleting(true);
    try {
      const jobIds = Array.from(selectedJobs);
      await deleteJobsBulk(jobIds, force);
      setJobs(jobs.filter(j => !selectedJobs.has(j.job_id || '')));
      setSelectedJobs(new Set());
    } catch (err: unknown) {
      console.error('Failed to delete jobs:', err);
      // Check if this is a protected jobs error
      const axiosError = err as { response?: { status?: number; data?: { detail?: { message?: string; protected_jobs?: Array<{ title: string; status: string }> } } } };
      if (axiosError.response?.status === 400 && axiosError.response?.data?.detail?.protected_jobs) {
        const detail = axiosError.response.data.detail;
        const protectedJobs = detail.protected_jobs || [];
        const jobList = protectedJobs.map((j: { title: string; status: string }) => `• ${j.title} (${j.status})`).join('\n');
        const confirmForce = confirm(
          `Cannot delete ${protectedJobs.length} job(s) with protected status:\n\n${jobList}\n\nThese jobs are approved/submitted/pending approval.\n\nClick OK to delete them anyway, or Cancel to keep them.`
        );
        if (confirmForce) {
          // Retry with force=true
          await handleDeleteSelected(true);
          return;
        }
      } else {
        alert('Failed to delete jobs');
      }
    } finally {
      setDeleting(false);
    }
  };

  const handleProcessSingle = async (jobId: string) => {
    if (!confirm('Process this job through the pipeline? (Score → Extract → Generate → Boost → Approval)')) return;

    setProcessing(true);
    try {
      const result = await processJobs([jobId]);
      alert(`Pipeline started: ${result.message}`);
      // Update job status locally to show it's being processed
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: 'scoring' as JobStatus } : j));
      // Enable auto-refresh to track progress
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to process job:', err);
      alert('Failed to start pipeline. It may already be running.');
    } finally {
      setProcessing(false);
    }
  };

  const handleProcessSelected = async () => {
    if (selectedJobs.size === 0) return;

    // Filter to only unscored jobs
    const unscoredSelected = jobs
      .filter(j => selectedJobs.has(j.job_id || '') && j.fit_score == null)
      .map(j => j.job_id)
      .filter(Boolean) as string[];

    if (unscoredSelected.length === 0) {
      alert('No unscored jobs selected. Only jobs without a score can be processed.');
      return;
    }

    if (!confirm(`Process ${unscoredSelected.length} job(s) through the pipeline?`)) return;

    setProcessing(true);
    try {
      const result = await processJobs(unscoredSelected);
      alert(`Pipeline started: ${result.message}`);
      // Update job statuses locally
      setJobs(jobs.map(j =>
        unscoredSelected.includes(j.job_id || '') ? { ...j, status: 'scoring' as JobStatus } : j
      ));
      setSelectedJobs(new Set());
      // Enable auto-refresh to track progress
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to process jobs:', err);
      alert('Failed to start pipeline. It may already be running.');
    } finally {
      setProcessing(false);
    }
  };

  // Check if any selected jobs are unscored (processable)
  const hasUnscoredSelected = jobs.some(j => selectedJobs.has(j.job_id || '') && j.fit_score == null);

  // Handle continuing processing for filtered jobs (reset status and set score to 90)
  const handleContinueProcessing = async (jobId: string) => {
    if (!confirm('Continue processing this job? The fit score will be set to 90 and processing will resume.')) return;

    setProcessing(true);
    try {
      // Reset status to 'new' and set fit_score to 90 (user override)
      await updateJobStatus(jobId, 'new', 90);
      // Then process it
      const result = await processJobs([jobId], 0); // min_score 0 to not filter again
      alert(`Processing started: ${result.message}`);
      // Update local state with new score
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: 'scoring' as JobStatus, fit_score: 90 } : j));
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to continue processing:', err);
      alert('Failed to continue processing');
    } finally {
      setProcessing(false);
    }
  };

  // Handle retrying stuck jobs (scoring, extracting, generating)
  const handleRetryProcessing = async (jobId: string, currentStatus: string) => {
    const statusLabels: Record<string, string> = {
      scoring: 'scoring',
      extracting: 'extraction',
      generating: 'generation',
    };
    const label = statusLabels[currentStatus] || currentStatus;

    if (!confirm(`Retry processing for this job? It appears stuck in ${label}. This will reset it and restart processing.`)) return;

    setProcessing(true);
    try {
      // Reset to 'new' to restart the pipeline
      await updateJobStatus(jobId, 'new');
      // Process with min_score 0 to ensure it goes through
      const result = await processJobs([jobId], 0);
      alert(`Processing restarted: ${result.message}`);
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: 'scoring' as JobStatus } : j));
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to retry processing:', err);
      alert('Failed to retry processing. The pipeline may already be running.');
    } finally {
      setProcessing(false);
    }
  };

  // Handle regenerating video for approved jobs missing video
  const handleRegenerateVideo = async (jobId: string) => {
    if (!confirm('Regenerate video for this job? This will re-trigger video generation.')) return;

    setProcessing(true);
    try {
      // Re-approve to trigger video generation again
      await approveJob(jobId);
      alert('Video generation started! Check the Video Generation panel for progress.');
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to regenerate video:', err);
      alert('Failed to start video generation.');
    } finally {
      setProcessing(false);
    }
  };

  // Statuses the user can manually set
  const manualStatuses: JobStatus[] = [
    'new', 'pending_approval', 'approved', 'rejected', 'shortlisted', 'filtered_out',
  ];

  // Handle single job status change
  const handleStatusChange = async (jobId: string, newStatus: JobStatus) => {
    setUpdatingStatus(true);
    try {
      await updateJobStatus(jobId, newStatus);
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: newStatus } : j));
    } catch (err) {
      console.error('Failed to update status:', err);
      alert('Failed to update job status');
    } finally {
      setUpdatingStatus(false);
    }
  };

  // Handle bulk status change
  const handleBulkStatusChange = async (newStatus: JobStatus) => {
    if (selectedJobs.size === 0) return;

    setUpdatingStatus(true);
    try {
      const jobIds = Array.from(selectedJobs);
      await updateJobStatusBulk(jobIds, newStatus);
      setJobs(jobs.map(j => selectedJobs.has(j.job_id || '') ? { ...j, status: newStatus } : j));
      setSelectedJobs(new Set());
    } catch (err) {
      console.error('Failed to bulk update status:', err);
      alert('Failed to update job statuses');
    } finally {
      setUpdatingStatus(false);
    }
  };

  // Handle job submission to Upwork
  const handleSubmitJob = async (jobId: string) => {
    if (!confirm('Submit this proposal to Upwork?')) return;

    setSubmitting(jobId);
    try {
      await submitJob(jobId);
      alert('Submission started! Check the Active Submissions panel for progress.');
      // Update local state to show it's being submitted
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: 'submitting' as JobStatus } : j));
      // Enable auto-refresh to track progress
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to submit job:', err);
      alert('Failed to start submission. Check if the job is approved and has all required data.');
    } finally {
      setSubmitting(null);
    }
  };

  // Handle editing proposal text
  const handleEditProposal = (jobId: string, currentText: string) => {
    setEditingProposalJobId(jobId);
    setEditedProposalText(currentText || '');
  };

  const handleCancelEditProposal = () => {
    setEditingProposalJobId(null);
    setEditedProposalText('');
  };

  const handleSaveProposal = async (jobId: string) => {
    setSavingProposal(true);
    try {
      await updateProposal(jobId, editedProposalText);
      // Update local state
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, proposal_text: editedProposalText } : j));
      setEditingProposalJobId(null);
      setEditedProposalText('');
    } catch (err) {
      console.error('Failed to save proposal:', err);
      alert('Failed to save proposal. Please try again.');
    } finally {
      setSavingProposal(false);
    }
  };

  // Toggle expanded row
  const toggleExpandJob = (jobId: string) => {
    setExpandedJobId(expandedJobId === jobId ? null : jobId);
  };

  // Handle column sort
  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Toggle direction if same column
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New column, default to descending (highest first for scores)
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  // Sort jobs
  const sortedJobs = React.useMemo(() => {
    if (!sortColumn) return jobs;

    return [...jobs].sort((a, b) => {
      let aVal: string | number | null = null;
      let bVal: string | number | null = null;

      switch (sortColumn) {
        case 'job_id':
          aVal = a.job_id || '';
          bVal = b.job_id || '';
          break;
        case 'title':
          aVal = (a.title || '').toLowerCase();
          bVal = (b.title || '').toLowerCase();
          break;
        case 'status':
          aVal = a.status || '';
          bVal = b.status || '';
          break;
        case 'fit_score':
          aVal = a.fit_score ?? -1;
          bVal = b.fit_score ?? -1;
          break;
        case 'budget':
          // Sort by budget_max for comparison, or budget_min if no max
          aVal = a.budget_max ?? a.budget_min ?? 0;
          bVal = b.budget_max ?? b.budget_min ?? 0;
          break;
        case 'source':
          aVal = (a.source || '').toLowerCase();
          bVal = (b.source || '').toLowerCase();
          break;
      }

      if (aVal === null || bVal === null) return 0;
      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [jobs, sortColumn, sortDirection]);

  // Sort indicator component
  const SortIndicator = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) {
      return (
        <svg className="w-3 h-3 ml-1 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
        </svg>
      );
    }
    return sortDirection === 'asc' ? (
      <svg className="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
      </svg>
    ) : (
      <svg className="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    );
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold dark:text-white">Dashboard</h1>
        {getModeIndicator()}
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500 dark:text-gray-400">Total Jobs</p>
            <p className="text-2xl font-bold dark:text-white">{stats.total}</p>
          </div>
          <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500 dark:text-gray-400">Pending Approval</p>
            <p className="text-2xl font-bold text-yellow-600">
              {stats.by_status?.pending_approval ?? 0}
            </p>
          </div>
          <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500 dark:text-gray-400">Submitted Today</p>
            <p className="text-2xl font-bold text-green-600">
              {stats.today_processed}
            </p>
          </div>
          <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500 dark:text-gray-400">Avg Fit Score</p>
            <p className="text-2xl font-bold dark:text-white">{stats.avg_fit_score?.toFixed(0) ?? 'N/A'}</p>
          </div>
        </div>
      )}

      {/* Active Submissions Panel */}
      {activeSubmissionCount > 0 && (
        <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <button
            onClick={() => setShowSubmissions(!showSubmissions)}
            className="w-full px-4 py-3 flex items-center justify-between bg-orange-50 dark:bg-orange-900/30 hover:bg-orange-100 dark:hover:bg-orange-900/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-white text-sm font-bold ${hasInProgressSubmissions ? 'bg-orange-500 animate-pulse' : 'bg-green-500'}`}>
                {activeSubmissionCount}
              </span>
              <span className="font-medium text-gray-700 dark:text-gray-200">
                Active Submissions
                {hasInProgressSubmissions && <span className="ml-2 text-orange-600 text-sm">(in progress)</span>}
              </span>
            </div>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`h-5 w-5 text-gray-500 transition-transform ${showSubmissions ? 'rotate-180' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>

          {showSubmissions && (
            <div className="p-4 space-y-4 max-h-96 overflow-y-auto">
              {Object.values(activeSubmissions).map((submission) => (
                <div key={submission.job_id} className="border rounded-lg overflow-hidden">
                  {/* Submission Header */}
                  <div className="px-4 py-2 bg-gray-50 dark:bg-gray-700 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                        submission.status === 'completed' ? 'bg-green-100 text-green-800' :
                        submission.status === 'failed' ? 'bg-red-100 text-red-800' :
                        submission.status === 'in_progress' ? 'bg-orange-100 text-orange-800' :
                        'bg-blue-100 text-blue-800'
                      }`}>
                        {submission.status === 'in_progress' ? 'Submitting' : submission.status}
                      </span>
                      <span className="text-sm text-gray-600 dark:text-gray-300">
                        Job: {submission.job_id.slice(0, 15)}...
                      </span>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Stage: {submission.stage}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        Started: {new Date(submission.started_at).toLocaleTimeString()}
                      </span>
                      {(submission.status === 'failed' || submission.status === 'completed' || submission.status === 'error') && (
                        <button
                          onClick={async () => {
                            try {
                              await dismissSubmission(submission.job_id);
                              setActiveSubmissions(prev => {
                                const updated = { ...prev };
                                delete updated[submission.job_id];
                                return updated;
                              });
                            } catch (err) {
                              console.error('Failed to dismiss:', err);
                            }
                          }}
                          className="text-xs px-2 py-1 bg-gray-200 dark:bg-gray-600 hover:bg-gray-300 dark:hover:bg-gray-500 rounded"
                          title="Dismiss"
                        >
                          Dismiss
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Log Output */}
                  <div className="bg-gray-900 text-gray-100 p-3 font-mono text-xs max-h-40 overflow-y-auto">
                    {submission.logs.length === 0 ? (
                      <div className="text-gray-500 italic">Waiting for logs...</div>
                    ) : (
                      submission.logs.map((log, idx) => (
                        <div key={idx} className={`py-0.5 ${
                          log.includes('ERROR') || log.includes('Failed') ? 'text-red-400' :
                          log.includes('SUCCESS') || log.includes('completed') ? 'text-green-400' :
                          log.includes('Starting') || log.includes('Navigating') ? 'text-blue-400' :
                          'text-gray-300'
                        }`}>
                          {log}
                        </div>
                      ))
                    )}
                    <div ref={logEndRef} />
                  </div>

                  {/* Error Display */}
                  {submission.error && (
                    <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">
                      <span className="font-medium">Error:</span> {submission.error}
                    </div>
                  )}

                  {/* Result Display */}
                  {submission.result && submission.status === 'completed' && (
                    <div className="px-4 py-2 bg-green-50 text-green-700 text-sm">
                      <span className="font-medium">Result:</span> Proposal submitted successfully
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 mb-4 items-center">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-md"
        >
          <option value="">All Statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search jobs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md flex-1 max-w-md"
        />
        {/* Auto-refresh toggle */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
          />
          <span className={`text-sm ${autoRefresh ? 'text-green-600 font-medium' : 'text-gray-600'}`}>
            Auto-refresh {autoRefresh && '(5s)'}
          </span>
        </label>
        {selectedJobs.size > 0 && (
          <>
            <select
              onChange={(e) => {
                if (e.target.value) {
                  handleBulkStatusChange(e.target.value as JobStatus);
                  e.target.value = '';
                }
              }}
              disabled={updatingStatus}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-md text-sm"
              defaultValue=""
            >
              <option value="" disabled>Set Status ({selectedJobs.size})</option>
              {manualStatuses.map((s) => (
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              ))}
            </select>
            {hasUnscoredSelected && (
              <button
                onClick={handleProcessSelected}
                disabled={processing || deleting}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {processing ? 'Starting...' : 'Process Selected'}
              </button>
            )}
            <button
              onClick={handleDeleteSelected}
              disabled={deleting || processing}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deleting ? 'Deleting...' : `Delete Selected (${selectedJobs.size})`}
            </button>
          </>
        )}
      </div>

      {/* Jobs Table */}
      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={jobs.length > 0 && selectedJobs.size === jobs.length}
                    onChange={handleSelectAll}
                    className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                  />
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('job_id')}
                >
                  <div className="flex items-center">
                    ID
                    <SortIndicator column="job_id" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('title')}
                >
                  <div className="flex items-center">
                    Title
                    <SortIndicator column="title" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('status')}
                >
                  <div className="flex items-center">
                    Status
                    <SortIndicator column="status" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('fit_score')}
                >
                  <div className="flex items-center">
                    Score
                    <SortIndicator column="fit_score" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('budget')}
                >
                  <div className="flex items-center">
                    Budget
                    <SortIndicator column="budget" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none"
                  onClick={() => handleSort('source')}
                >
                  <div className="flex items-center">
                    Source
                    <SortIndicator column="source" />
                  </div>
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {sortedJobs.map((job, idx) => {
                const isExpanded = expandedJobId === job.job_id;
                const hasScoreInfo = job.fit_reasoning || job.score_reasoning;
                const hasAssets = job.video_url || job.pdf_url || job.proposal_doc_url || job.proposal_text;
                const isExpandable = hasScoreInfo || hasAssets;
                const isFiltered = job.status === 'filtered_out';

                return (
                  <React.Fragment key={job.job_id || idx}>
                    <tr className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${isExpanded ? 'bg-blue-50 dark:bg-blue-900/30' : ''}`}>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedJobs.has(job.job_id || '')}
                          onChange={() => job.job_id && handleSelectJob(job.job_id)}
                          className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                        {job.job_id ? `${String(job.job_id).slice(0, 10)}...` : 'N/A'}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <a
                          href={getUpworkUrl(job.url, job.job_id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {truncateText(job.title || 'Untitled', 50)}
                        </a>
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={job.status}
                          onChange={(e) => {
                            e.stopPropagation();
                            if (job.job_id) handleStatusChange(job.job_id, e.target.value as JobStatus);
                          }}
                          disabled={updatingStatus}
                          className={`px-2 py-1 text-xs rounded-full border-0 cursor-pointer ${STATUS_COLORS[job.status] || 'bg-gray-100 text-gray-800'}`}
                        >
                          {/* Current status always shown */}
                          {!manualStatuses.includes(job.status) && (
                            <option value={job.status}>{STATUS_LABELS[job.status] || job.status}</option>
                          )}
                          {manualStatuses.map((s) => (
                            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        {/* Score with expand button */}
                        <button
                          onClick={() => job.job_id && toggleExpandJob(job.job_id)}
                          className={`flex items-center gap-1 px-2 py-1 text-xs rounded ${getScoreColor(job.fit_score)} ${isExpandable ? 'cursor-pointer hover:ring-2 ring-blue-300' : ''}`}
                          title={isExpandable ? 'Click to see details' : undefined}
                          disabled={!isExpandable}
                        >
                          {job.fit_score ?? 'N/A'}
                          {isExpandable && (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              className={`h-3 w-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                              viewBox="0 0 20 20"
                              fill="currentColor"
                            >
                              <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                            </svg>
                          )}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {formatBudget(job.budget_type, job.budget_min, job.budget_max)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 capitalize">
                        {job.source || 'unknown'}
                      </td>
                      <td className="px-4 py-3 flex gap-2">
                        {/* Submit button - show for approved jobs with video */}
                        {job.status === 'approved' && job.video_url && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              job.job_id && handleSubmitJob(job.job_id);
                            }}
                            disabled={submitting === job.job_id || processing || deleting}
                            className="text-green-600 hover:text-green-800 disabled:opacity-50"
                            title="Submit to Upwork"
                          >
                            {submitting === job.job_id ? (
                              <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                            ) : (
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
                              </svg>
                            )}
                          </button>
                        )}
                        {/* Retry button - show for stuck jobs in intermediate states */}
                        {(job.status === 'scoring' || job.status === 'extracting' || job.status === 'generating') && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              job.job_id && handleRetryProcessing(job.job_id, job.status);
                            }}
                            disabled={processing || deleting}
                            className="text-yellow-600 hover:text-yellow-800 disabled:opacity-50"
                            title={`Retry processing (stuck in ${job.status})`}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                            </svg>
                          </button>
                        )}
                        {/* Regenerate video button - show for approved jobs without video */}
                        {job.status === 'approved' && !job.video_url && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              job.job_id && handleRegenerateVideo(job.job_id);
                            }}
                            disabled={processing || deleting}
                            className="text-purple-600 hover:text-purple-800 disabled:opacity-50"
                            title="Regenerate video (video generation may have failed)"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
                            </svg>
                          </button>
                        )}
                        {/* Continue Processing button - show for filtered_out jobs */}
                        {isFiltered && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              job.job_id && handleContinueProcessing(job.job_id);
                            }}
                            disabled={processing || deleting}
                            className="text-orange-600 hover:text-orange-800 disabled:opacity-50"
                            title="Continue processing (skip scoring)"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                            </svg>
                          </button>
                        )}
                        {/* Process button - only show for unscored jobs */}
                        {job.fit_score == null && !isFiltered && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              job.job_id && handleProcessSingle(job.job_id);
                            }}
                            disabled={processing || deleting}
                            className="text-green-600 hover:text-green-800 disabled:opacity-50"
                            title="Process through pipeline"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                            </svg>
                          </button>
                        )}
                        {/* Delete button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            job.job_id && handleDeleteSingle(job.job_id);
                          }}
                          disabled={deleting || processing}
                          className="text-red-600 hover:text-red-800 disabled:opacity-50"
                          title="Delete job"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                    {/* Expanded Row - Details & Assets */}
                    {isExpanded && isExpandable && (
                      <tr className="bg-gray-50 dark:bg-gray-700">
                        <td colSpan={8} className="px-4 py-4">
                          <div className="space-y-4">
                            {/* Generated Assets */}
                            {hasAssets && (
                              <div>
                                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center gap-2">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-purple-500" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" />
                                  </svg>
                                  Generated Assets
                                </h4>
                                <div className="flex flex-wrap gap-3">
                                  {getVideoUrl(job.video_url, job.job_id) && (
                                    <a
                                      href={getVideoUrl(job.video_url, job.job_id)!}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm"
                                    >
                                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                        <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
                                      </svg>
                                      Watch Video
                                    </a>
                                  )}
                                  {getPdfUrl(job.pdf_url, job.job_id) && (
                                    <a
                                      href={getPdfUrl(job.pdf_url, job.job_id)!}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
                                    >
                                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                        <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                                      </svg>
                                      View PDF
                                    </a>
                                  )}
                                  {job.proposal_doc_url && (
                                    <a
                                      href={job.proposal_doc_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 text-sm"
                                    >
                                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                        <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                                      </svg>
                                      View Proposal Doc
                                    </a>
                                  )}
                                </div>
                              </div>
                            )}
                            {/* Cover Letter Preview/Edit */}
                            {(job.proposal_text || editingProposalJobId === job.job_id) && (
                              <div>
                                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2 justify-between">
                                  <span className="flex items-center gap-2">
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-indigo-500" viewBox="0 0 20 20" fill="currentColor">
                                      <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                                    </svg>
                                    Cover Letter
                                  </span>
                                  {editingProposalJobId !== job.job_id && job.status === 'approved' && (
                                    <button
                                      onClick={() => handleEditProposal(job.job_id!, job.proposal_text || '')}
                                      className="text-xs px-2 py-1 bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 rounded hover:bg-indigo-200 dark:hover:bg-indigo-800 flex items-center gap-1"
                                    >
                                      <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                        <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                                      </svg>
                                      Edit
                                    </button>
                                  )}
                                </h4>
                                {editingProposalJobId === job.job_id ? (
                                  <div className="space-y-2">
                                    <textarea
                                      value={editedProposalText}
                                      onChange={(e) => setEditedProposalText(e.target.value)}
                                      className="w-full h-60 p-3 rounded border dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 resize-y"
                                      placeholder="Enter cover letter..."
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => handleSaveProposal(job.job_id!)}
                                        disabled={savingProposal}
                                        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm flex items-center gap-1"
                                      >
                                        {savingProposal ? (
                                          <>
                                            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            Saving...
                                          </>
                                        ) : (
                                          <>
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                            </svg>
                                            Save
                                          </>
                                        )}
                                      </button>
                                      <button
                                        onClick={handleCancelEditProposal}
                                        disabled={savingProposal}
                                        className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 disabled:opacity-50 text-sm"
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="bg-white dark:bg-gray-800 p-3 rounded border dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
                                    {job.proposal_text}
                                  </div>
                                )}
                              </div>
                            )}
                            {/* Score Reasoning */}
                            {job.score_reasoning && (
                              <div>
                                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
                                  </svg>
                                  Score Breakdown
                                </h4>
                                <div className="bg-white dark:bg-gray-800 p-3 rounded border dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap font-mono">
                                  {job.score_reasoning}
                                </div>
                              </div>
                            )}
                            {/* Fit Reasoning */}
                            {job.fit_reasoning && (
                              <div>
                                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-green-500" viewBox="0 0 20 20" fill="currentColor">
                                    <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                  </svg>
                                  Fit Analysis
                                </h4>
                                <div className="bg-white dark:bg-gray-800 p-3 rounded border dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap">
                                  {job.fit_reasoning}
                                </div>
                              </div>
                            )}
                            {/* Action buttons in expanded view */}
                            {/* Submit button for approved jobs with video */}
                            {job.status === 'approved' && job.video_url && (
                              <div className="flex gap-2 pt-2 border-t dark:border-gray-600 mt-4">
                                <button
                                  onClick={() => job.job_id && handleSubmitJob(job.job_id)}
                                  disabled={submitting === job.job_id || processing || deleting}
                                  className="px-6 py-3 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium flex items-center gap-2"
                                >
                                  {submitting === job.job_id ? (
                                    <>
                                      <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                      </svg>
                                      Starting Submission...
                                    </>
                                  ) : (
                                    <>
                                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
                                      </svg>
                                      Submit to Upwork
                                    </>
                                  )}
                                </button>
                              </div>
                            )}
                            {isFiltered && (
                              <div className="flex gap-2 pt-2">
                                <button
                                  onClick={() => job.job_id && handleContinueProcessing(job.job_id)}
                                  disabled={processing || deleting}
                                  className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center gap-2"
                                >
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                                    <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                                  </svg>
                                  Continue Processing (Skip Score Filter)
                                </button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    No jobs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
