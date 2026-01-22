import React, { useState, useEffect, useRef } from 'react';
import { getJobs, getJobStats, deleteJob, deleteJobsBulk, processJobs, updateJobStatus, getActiveSubmissions, getActiveVideoGenerations, getSubmissionMode, type SubmissionStatus, type ActiveSubmissionsResponse, type SubmissionModeResponse } from '@/api/jobs';
import type { VideoGenerationStatus, ActiveVideoGenerationsResponse } from '@/api/types';
import type { Job, JobStatsResponse, JobStatus } from '@/api/types';
import { STATUS_COLORS, STATUS_LABELS, getScoreColor } from '@/lib/constants';
import { formatBudget, truncateText } from '@/lib/utils';

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
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [activeSubmissions, setActiveSubmissions] = useState<Record<string, SubmissionStatus>>({});
  const [showSubmissions, setShowSubmissions] = useState(true);
  const [activeVideoGens, setActiveVideoGens] = useState<VideoGenerationStatus[]>([]);
  const [showVideoGens, setShowVideoGens] = useState(true);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [submissionMode, setSubmissionMode] = useState<SubmissionModeResponse | null>(null);
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const logEndRef = useRef<HTMLDivElement>(null);
  const videoLogEndRef = useRef<HTMLDivElement>(null);

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
      setJobs(jobsRes.jobs);
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

  // Fetch active video generations
  const fetchVideoGenerations = async () => {
    try {
      const result = await getActiveVideoGenerations();
      setActiveVideoGens(Array.isArray(result.video_generations) ? result.video_generations : []);
      // Auto-scroll to bottom of logs when new entries come in
      if (videoLogEndRef.current) {
        videoLogEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    } catch (err) {
      console.error('Failed to fetch video generations:', err);
      setActiveVideoGens([]);
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

  // Poll for submission and video generation updates
  useEffect(() => {
    fetchSubmissions(); // Initial fetch
    fetchVideoGenerations(); // Initial fetch
    fetchSubmissionMode(); // Initial fetch

    const interval = setInterval(() => {
      fetchSubmissions();
      fetchVideoGenerations();
    }, 2000); // Poll every 2 seconds for real-time updates

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

  const activeVideoGenCount = activeVideoGens.length;
  const hasInProgressVideoGens = activeVideoGens.some(
    v => v.status === 'pending' || v.status === 'in_progress'
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
    'pending_approval', 'approved', 'rejected', 'submitting', 'submitted', 'submission_failed', 'filtered_out'
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

  const handleDeleteSelected = async () => {
    if (selectedJobs.size === 0) return;
    if (!confirm(`Are you sure you want to delete ${selectedJobs.size} job(s)?`)) return;

    setDeleting(true);
    try {
      const jobIds = Array.from(selectedJobs);
      await deleteJobsBulk(jobIds);
      setJobs(jobs.filter(j => !selectedJobs.has(j.job_id || '')));
      setSelectedJobs(new Set());
    } catch (err) {
      console.error('Failed to delete jobs:', err);
      alert('Failed to delete jobs');
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

  // Handle continuing processing for filtered jobs (reset status to extracting to skip scoring)
  const handleContinueProcessing = async (jobId: string) => {
    if (!confirm('Reset this job to continue processing? It will skip scoring and go to extraction.')) return;

    setProcessing(true);
    try {
      // Reset status to 'extracting' to skip scoring but continue pipeline
      await updateJobStatus(jobId, 'new');
      // Then process it
      const result = await processJobs([jobId], 0); // min_score 0 to not filter again
      alert(`Processing started: ${result.message}`);
      // Update local state
      setJobs(jobs.map(j => j.job_id === jobId ? { ...j, status: 'scoring' as JobStatus } : j));
      setAutoRefresh(true);
    } catch (err) {
      console.error('Failed to continue processing:', err);
      alert('Failed to continue processing');
    } finally {
      setProcessing(false);
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
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      Started: {new Date(submission.started_at).toLocaleTimeString()}
                    </span>
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

      {/* Active Video Generations Panel */}
      {activeVideoGenCount > 0 && (
        <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
          <button
            onClick={() => setShowVideoGens(!showVideoGens)}
            className="w-full px-4 py-3 flex items-center justify-between bg-purple-50 dark:bg-purple-900/30 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-white text-sm font-bold ${hasInProgressVideoGens ? 'bg-purple-500 animate-pulse' : 'bg-green-500'}`}>
                {activeVideoGenCount}
              </span>
              <span className="font-medium text-gray-700 dark:text-gray-200">
                Video Generation
                {hasInProgressVideoGens && <span className="ml-2 text-purple-600 text-sm">(generating)</span>}
              </span>
            </div>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`h-5 w-5 text-gray-500 transition-transform ${showVideoGens ? 'rotate-180' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>

          {showVideoGens && (
            <div className="p-4 space-y-4 max-h-96 overflow-y-auto">
              {activeVideoGens.map((videoGen) => (
                <div key={videoGen.job_id} className="border rounded-lg overflow-hidden">
                  {/* Video Gen Header */}
                  <div className="px-4 py-2 bg-gray-50 dark:bg-gray-700 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                        videoGen.status === 'completed' ? 'bg-green-100 text-green-800' :
                        videoGen.status === 'failed' ? 'bg-red-100 text-red-800' :
                        videoGen.status === 'in_progress' ? 'bg-purple-100 text-purple-800' :
                        'bg-blue-100 text-blue-800'
                      }`}>
                        {videoGen.status === 'in_progress' ? 'Generating' : videoGen.status}
                      </span>
                      <span className="text-sm text-gray-600 dark:text-gray-300">
                        Job: {videoGen.job_id.slice(0, 15)}...
                      </span>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Stage: {videoGen.stage}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      Started: {new Date(videoGen.started_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Log Output */}
                  <div className="bg-gray-900 text-gray-100 p-3 font-mono text-xs max-h-40 overflow-y-auto">
                    {videoGen.logs.length === 0 ? (
                      <div className="text-gray-500 italic">Waiting for logs...</div>
                    ) : (
                      videoGen.logs.map((log, idx) => (
                        <div key={idx} className={`py-0.5 ${
                          log.includes('ERROR') || log.includes('Failed') ? 'text-red-400' :
                          log.includes('SUCCESS') || log.includes('successfully') ? 'text-green-400' :
                          log.includes('Starting') || log.includes('Generating') || log.includes('Calling') ? 'text-blue-400' :
                          'text-gray-300'
                        }`}>
                          {log}
                        </div>
                      ))
                    )}
                    <div ref={videoLogEndRef} />
                  </div>

                  {/* Error Display */}
                  {videoGen.error && (
                    <div className="px-4 py-2 bg-red-50 text-red-700 text-sm">
                      <span className="font-medium">Error:</span> {videoGen.error}
                    </div>
                  )}

                  {/* Success with Video URL */}
                  {videoGen.video_url && videoGen.status === 'completed' && (
                    <div className="px-4 py-2 bg-green-50 flex items-center justify-between">
                      <span className="text-green-700 text-sm font-medium">Video generated successfully!</span>
                      <a
                        href={videoGen.video_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                          <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
                        </svg>
                        Watch Video
                      </a>
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
                          href={job.url || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline"
                        >
                          {truncateText(job.title || 'Untitled', 50)}
                        </a>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[job.status] || 'bg-gray-100 text-gray-800'}`}>
                          {STATUS_LABELS[job.status] || job.status || 'Unknown'}
                        </span>
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
                                  {job.video_url && (
                                    <a
                                      href={job.video_url}
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
                                  {job.pdf_url && (
                                    <a
                                      href={job.pdf_url}
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
                            {/* Proposal Text Preview */}
                            {job.proposal_text && (
                              <div>
                                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-indigo-500" viewBox="0 0 20 20" fill="currentColor">
                                    <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                                  </svg>
                                  Proposal Text
                                </h4>
                                <div className="bg-white dark:bg-gray-800 p-3 rounded border dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
                                  {job.proposal_text}
                                </div>
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
