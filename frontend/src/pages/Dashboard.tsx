import { useState, useEffect } from 'react';
import { getJobs, getJobStats } from '@/api/jobs';
import type { Job, JobStatsResponse, JobStatus } from '@/api/types';
import { STATUS_COLORS, STATUS_LABELS, getScoreColor } from '@/lib/constants';
import { formatBudget, truncateText } from '@/lib/utils';

export function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<JobStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
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
        setLoading(false);
      }
    };

    fetchData();
  }, [statusFilter, search]);

  const statuses: JobStatus[] = [
    'new', 'scoring', 'extracting', 'generating',
    'pending_approval', 'approved', 'rejected', 'submitted', 'filtered_out'
  ];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500">Total Jobs</p>
            <p className="text-2xl font-bold">{stats.total}</p>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500">Pending Approval</p>
            <p className="text-2xl font-bold text-yellow-600">
              {stats.by_status?.pending_approval ?? 0}
            </p>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500">Submitted Today</p>
            <p className="text-2xl font-bold text-green-600">
              {stats.today_processed}
            </p>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <p className="text-sm text-gray-500">Avg Fit Score</p>
            <p className="text-2xl font-bold">{stats.avg_fit_score?.toFixed(0) ?? 'N/A'}</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
          className="px-3 py-2 border border-gray-300 rounded-md"
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
          className="px-3 py-2 border border-gray-300 rounded-md flex-1 max-w-md"
        />
      </div>

      {/* Jobs Table */}
      {loading ? (
        <div className="text-center py-8">Loading...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Budget</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {jobs.map((job) => (
                <tr key={job.job_id} className="hover:bg-gray-50 cursor-pointer">
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {job.job_id.slice(0, 10)}...
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      {truncateText(job.title, 50)}
                    </a>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[job.status]}`}>
                      {STATUS_LABELS[job.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 text-xs rounded ${getScoreColor(job.fit_score)}`}>
                      {job.fit_score ?? 'N/A'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {formatBudget(job.budget_type, job.budget_min, job.budget_max)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 capitalize">
                    {job.source}
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
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
