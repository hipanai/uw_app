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
  LogsResponse,
  JobStatus,
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

export const triggerPipeline = async (
  source: 'apify' | 'gmail',
  limit?: number
): Promise<PipelineTriggerResponse> => {
  const response = await apiClient.post<PipelineTriggerResponse>('/admin/pipeline/trigger', {
    source,
    limit,
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
