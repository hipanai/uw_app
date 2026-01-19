// Job status enum matching backend
export type JobStatus =
  | 'new'
  | 'scoring'
  | 'extracting'
  | 'generating'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'submitted'
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
  running: boolean;
  last_run: string | null;
  last_result: {
    jobs_processed: number;
    jobs_approved: number;
    errors: number;
  } | null;
}

export interface HealthResponse {
  sheets_connected: boolean;
  slack_configured: boolean;
  anthropic_configured: boolean;
  heygen_configured: boolean;
}

export interface ConfigResponse {
  PREFILTER_MIN_SCORE: number;
  UPWORK_PIPELINE_SHEET_ID: string;
  UPWORK_PROCESSED_IDS_SHEET_ID: string;
  ANTHROPIC_API_KEY: string;
  HEYGEN_API_KEY: string;
  SLACK_BOT_TOKEN: string;
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
