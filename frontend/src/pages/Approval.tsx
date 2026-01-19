import { useState, useEffect } from 'react';
import {
  getPendingApprovals,
  approveJob,
  rejectJob,
  updateProposal,
} from '@/api/jobs';
import type { Job } from '@/api/types';
import { STATUS_COLORS, STATUS_LABELS, getScoreColor } from '@/lib/constants';
import { formatBudget, formatDate, formatClientSpent } from '@/lib/utils';

export function Approval() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [editedProposal, setEditedProposal] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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

  useEffect(() => {
    fetchPending();
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

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Approval Queue</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">
        Approval Queue
        <span className="ml-2 text-sm font-normal text-gray-500">
          ({jobs.length} pending)
        </span>
      </h1>

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
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No jobs pending approval. Check back later!
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Job List */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow overflow-hidden">
              <div className="p-3 bg-gray-50 border-b font-medium">
                Pending Jobs
              </div>
              <ul className="divide-y divide-gray-200 max-h-[600px] overflow-y-auto">
                {jobs.map((job) => (
                  <li
                    key={job.job_id}
                    onClick={() => selectJob(job)}
                    className={`p-3 cursor-pointer hover:bg-gray-50 ${
                      selectedJob?.job_id === job.job_id ? 'bg-blue-50' : ''
                    }`}
                  >
                    <p className="font-medium text-sm truncate">{job.title}</p>
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
                <div className="bg-white rounded-lg shadow p-4">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h2 className="text-lg font-semibold">{selectedJob.title}</h2>
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
                      <p className="text-gray-500">Fit Score</p>
                      <p className={`font-semibold px-2 py-0.5 rounded inline-block ${getScoreColor(selectedJob.fit_score)}`}>
                        {selectedJob.fit_score ?? 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500">Budget</p>
                      <p className="font-semibold">
                        {formatBudget(selectedJob.budget_type, selectedJob.budget_min, selectedJob.budget_max)}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500">Client Spent</p>
                      <p className="font-semibold">{formatClientSpent(selectedJob.client_spent)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Posted</p>
                      <p className="font-semibold">{formatDate(selectedJob.posted_date)}</p>
                    </div>
                  </div>

                  <div className="border-t pt-4">
                    <p className="text-gray-500 text-sm mb-2">Job Description</p>
                    <p className="text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">
                      {selectedJob.description || 'No description available'}
                    </p>
                  </div>

                  {selectedJob.score_reasoning && (
                    <div className="border-t pt-4 mt-4">
                      <p className="text-gray-500 text-sm mb-2">Score Reasoning</p>
                      <p className="text-sm whitespace-pre-wrap">
                        {selectedJob.score_reasoning}
                      </p>
                    </div>
                  )}
                </div>

                {/* Proposal Editor */}
                <div className="bg-white rounded-lg shadow p-4">
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="font-semibold">Proposal</h3>
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
                    className="w-full h-64 p-3 border border-gray-300 rounded-md text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="No proposal generated yet"
                  />
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3">
                  <button
                    onClick={handleApprove}
                    disabled={actionLoading !== null}
                    className="flex-1 bg-green-600 text-white py-3 px-4 rounded-md hover:bg-green-700 disabled:opacity-50 font-medium"
                  >
                    {actionLoading === 'approve' ? 'Approving...' : 'Approve & Submit'}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={actionLoading !== null}
                    className="flex-1 bg-red-600 text-white py-3 px-4 rounded-md hover:bg-red-700 disabled:opacity-50 font-medium"
                  >
                    {actionLoading === 'reject' ? 'Rejecting...' : 'Reject'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
