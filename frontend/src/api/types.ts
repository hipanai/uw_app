// Job status enum matching backend
export type JobStatus =
  | 'new'
  | 'scoring'
  | 'extracting'
  | 'generating'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'submitting'
  | 'submitted'
  | 'submission_failed'
  | 'filtered_out'
  | 'error';

// Job interface matching Google Sheet columns
export interface Job {
  job_id: string;
  source: 'apify' | 'gmail';
  status: JobStatus;
  title: string;
  url: string;
  description: string;
  attachments: string; // JSON array
  budget_type: 'fixed' | 'hourly' | 'unknown';
  budget_min: number | null;
  budget_max: number | null;
  client_country: string | null;
  client_spent: number | null;
  client_hires: number | null;
  payment_verified: boolean;
  fit_score: number | null;
  fit_reasoning: string | null;
  score_reasoning: string | null;
  posted_date: string | null;
  proposal_doc_url: string | null;
  proposal_text: string | null;
  video_url: string | null;
  pdf_url: string | null;
  boost_decision: boolean | null;
  boost_reasoning: string | null;
  pricing_proposed: number | null;
  slack_message_ts: string | null;
  approved_at: string | null;
  submitted_at: string | null;
  error_log: string | null;
  created_at: string;
  updated_at: string;
}

// API response types
export interface JobsResponse {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
}

export interface JobStatsResponse {
  total: number;
  by_status: Record<JobStatus, number>;
  avg_fit_score: number;
  today_processed: number;
}

export interface AuthResponse {
  token: string;
  expires_in: number;
}

export interface ApprovalResponse {
  success: boolean;
  job_id: string;
  status: JobStatus;
  error?: string;
}

export interface PipelineTriggerResponse {
  run_id: string;
  status: 'started' | 'queued' | 'error';
  error?: string;
}

export interface PipelineStatusResponse {
  is_running: boolean;
  last_run_time: string | null;
  last_run_status: string | null;
  current_run_id: string | null;
  jobs_processed_today: number;
  last_reset_date: string;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  services: {
    sheets: boolean;
    slack: boolean;
    openai: boolean;
  };
  timestamp: string;
}

export interface ConfigItem {
  key: string;
  label: string;
  value: string;
  raw_value: string;
  sensitive: boolean;
  editable: boolean;
  description: string;
  is_set: boolean;
}

export interface ConfigResponse {
  config: ConfigItem[];
}

export interface ConfigUpdateResponse {
  success: boolean;
  message: string;
  updated: string[];
}

export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
  message: string;
  source?: string;
}

export interface LogsResponse {
  logs: LogEntry[];
  total: number;
}

// Video Generation Status
export interface VideoGenerationStatus {
  job_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  stage: string;
  started_at: string;
  updated_at?: string;
  logs: string[];
  error: string | null;
  video_url: string | null;
}

export interface ActiveVideoGenerationsResponse {
  video_generations: VideoGenerationStatus[];
  count: number;
}
