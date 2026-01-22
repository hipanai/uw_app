import apiClient from './client';
import type {
  Job,
  JobsResponse,
  JobStatsResponse,
  ApprovalResponse,
  AuthResponse,
  PipelineTriggerResponse,
  PipelineStatusResponse,
  HealthResponse,
  ConfigResponse,
  ConfigUpdateResponse,
  LogsResponse,
  JobStatus,
  VideoGenerationStatus,
  ActiveVideoGenerationsResponse,
} from './types';

// Auth API
export const login = async (password: string): Promise<AuthResponse> => {
  const response = await apiClient.post<AuthResponse>('/auth/login', { password });
  return response.data;
};

export const verifyToken = async (): Promise<{ valid: boolean }> => {
  const response = await apiClient.get<{ valid: boolean }>('/auth/verify');
  return response.data;
};

// Jobs API
export interface GetJobsParams {
  status?: JobStatus;
  search?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export const getJobs = async (params: GetJobsParams = {}): Promise<JobsResponse> => {
  const response = await apiClient.get<JobsResponse>('/jobs', { params });
  return response.data;
};

export const getJob = async (jobId: string): Promise<Job> => {
  const response = await apiClient.get<Job>(`/jobs/${encodeURIComponent(jobId)}`);
  return response.data;
};

export const getJobStats = async (): Promise<JobStatsResponse> => {
  const response = await apiClient.get<JobStatsResponse>('/jobs/stats');
  return response.data;
};

// Approvals API
export const getPendingApprovals = async (): Promise<Job[]> => {
  const response = await apiClient.get<Job[]>('/approvals/pending');
  return response.data;
};

export const approveJob = async (jobId: string): Promise<ApprovalResponse> => {
  const response = await apiClient.post<ApprovalResponse>(
    `/approvals/${encodeURIComponent(jobId)}/approve`
  );
  return response.data;
};

export const rejectJob = async (jobId: string): Promise<ApprovalResponse> => {
  const response = await apiClient.post<ApprovalResponse>(
    `/approvals/${encodeURIComponent(jobId)}/reject`
  );
  return response.data;
};

export const updateProposal = async (
  jobId: string,
  proposalText: string
): Promise<ApprovalResponse> => {
  const response = await apiClient.put<ApprovalResponse>(
    `/approvals/${encodeURIComponent(jobId)}/proposal`,
    { proposal_text: proposalText }
  );
  return response.data;
};

export const submitJob = async (jobId: string): Promise<ApprovalResponse> => {
  const response = await apiClient.post<ApprovalResponse>(
    `/approvals/${encodeURIComponent(jobId)}/submit`
  );
  return response.data;
};

// Admin API
export const getConfig = async (): Promise<ConfigResponse> => {
  const response = await apiClient.get<ConfigResponse>('/admin/config');
  return response.data;
};

export const updateConfig = async (
  config: Record<string, string>
): Promise<ConfigUpdateResponse> => {
  const response = await apiClient.put<ConfigUpdateResponse>('/admin/config', { config });
  return response.data;
};

export const triggerPipeline = async (
  source: 'apify' | 'gmail' | 'urls',
  limit?: number,
  keywords?: string,
  location?: string,
  runFullPipeline?: boolean,
  minScore?: number,
  fromDate?: string,
  toDate?: string,
  minHourly?: number,
  maxHourly?: number,
  minFixed?: number,
  maxFixed?: number,
  jobUrls?: string[]
): Promise<PipelineTriggerResponse> => {
  const response = await apiClient.post<PipelineTriggerResponse>('/admin/pipeline/trigger', {
    source,
    limit,
    keywords: keywords || undefined,
    location: location || undefined,
    run_full_pipeline: runFullPipeline ?? false,
    min_score: minScore ?? 70,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
    min_hourly: minHourly || undefined,
    max_hourly: maxHourly || undefined,
    min_fixed: minFixed || undefined,
    max_fixed: maxFixed || undefined,
    job_urls: jobUrls || undefined,
  });
  return response.data;
};

export const processJobs = async (
  jobIds: string[],
  minScore?: number
): Promise<{ success: boolean; run_id: string; job_count: number; message: string }> => {
  const response = await apiClient.post('/admin/pipeline/process', {
    job_ids: jobIds,
    min_score: minScore ?? 70,
  });
  return response.data;
};

export const updateJobStatus = async (
  jobId: string,
  status: string
): Promise<{ success: boolean; job_id: string; status: string }> => {
  const response = await apiClient.patch(`/jobs/${encodeURIComponent(jobId)}/status`, {
    status,
  });
  return response.data;
};

export const getPipelineStatus = async (): Promise<PipelineStatusResponse> => {
  const response = await apiClient.get<PipelineStatusResponse>('/admin/pipeline/status');
  return response.data;
};

export const getLogs = async (
  level?: string,
  limit?: number
): Promise<LogsResponse> => {
  const response = await apiClient.get<LogsResponse>('/admin/logs', {
    params: { level, limit },
  });
  return response.data;
};

export const getHealth = async (): Promise<HealthResponse> => {
  const response = await apiClient.get<HealthResponse>('/admin/health');
  return response.data;
};

// Delete API
export interface DeleteJobResponse {
  success: boolean;
  message: string;
  job_id: string;
}

export interface BulkDeleteResponse {
  success: boolean;
  message: string;
  deleted_count: number;
  requested_count: number;
}

export const deleteJob = async (jobId: string): Promise<DeleteJobResponse> => {
  const response = await apiClient.delete<DeleteJobResponse>(`/jobs/${encodeURIComponent(jobId)}`);
  return response.data;
};

export const deleteJobsBulk = async (jobIds: string[]): Promise<BulkDeleteResponse> => {
  const response = await apiClient.delete<BulkDeleteResponse>('/jobs/bulk', {
    data: { job_ids: jobIds }
  });
  return response.data;
};

// Submission Status API
export interface SubmissionStatus {
  job_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  stage: string;
  started_at: string;
  updated_at?: string;
  logs: string[];
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface ActiveSubmissionsResponse {
  submissions: Record<string, SubmissionStatus>;
  count: number;
}

export const getSubmissionStatus = async (jobId: string): Promise<SubmissionStatus> => {
  const response = await apiClient.get<SubmissionStatus>(`/submissions/status/${encodeURIComponent(jobId)}`);
  return response.data;
};

export const getActiveSubmissions = async (): Promise<ActiveSubmissionsResponse> => {
  const response = await apiClient.get<ActiveSubmissionsResponse>('/submissions/active');
  return response.data;
};

// Submission Mode API
export interface SubmissionModeResponse {
  mode: 'manual' | 'semi_auto' | 'automatic';
  description: string;
  available_modes: { value: string; label: string }[];
}

export const getSubmissionMode = async (): Promise<SubmissionModeResponse> => {
  const response = await apiClient.get<SubmissionModeResponse>('/submission-mode');
  return response.data;
};

export const setSubmissionMode = async (mode: string): Promise<{ success: boolean; mode: string }> => {
  const response = await apiClient.put('/submission-mode', { mode });
  return response.data;
};

export const autoProcessPendingJobs = async (): Promise<{ success: boolean; processed: number; message: string }> => {
  const response = await apiClient.post('/auto-process');
  return response.data;
};

// Video Generation Status API
export const getVideoGenerationStatus = async (jobId: string): Promise<VideoGenerationStatus> => {
  const response = await apiClient.get<VideoGenerationStatus>(`/video-generation/status/${encodeURIComponent(jobId)}`);
  return response.data;
};

export const getActiveVideoGenerations = async (): Promise<ActiveVideoGenerationsResponse> => {
  const response = await apiClient.get<ActiveVideoGenerationsResponse>('/video-generation/active');
  return response.data;
};
