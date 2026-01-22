import { useState, useEffect } from 'react';
import {
  getHealth,
  getConfig,
  updateConfig,
  getPipelineStatus,
  triggerPipeline,
  getLogs,
  getSubmissionMode,
  setSubmissionMode,
  autoProcessPendingJobs,
  type SubmissionModeResponse,
} from '@/api/jobs';
import type { HealthResponse, PipelineStatusResponse, LogEntry, ConfigItem } from '@/api/types';
import { LOG_LEVEL_COLORS } from '@/lib/constants';
import { formatDate } from '@/lib/utils';

export function Admin() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusResponse | null>(null);
  const [configItems, setConfigItems] = useState<ConfigItem[]>([]);
  const [editedConfig, setEditedConfig] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [triggerSource, setTriggerSource] = useState<'apify' | 'gmail' | 'urls'>('apify');
  const [jobUrls, setJobUrls] = useState<string>('');
  const [triggerLimit, setTriggerLimit] = useState<number>(10);
  const [triggerKeywords, setTriggerKeywords] = useState<string>('');
  const [triggerLocation, setTriggerLocation] = useState<string>('');
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [minHourly, setMinHourly] = useState<string>('');
  const [maxHourly, setMaxHourly] = useState<string>('');
  const [minFixed, setMinFixed] = useState<string>('');
  const [maxFixed, setMaxFixed] = useState<string>('');
  const [runFullPipeline, setRunFullPipeline] = useState<boolean>(false);
  const [minScore, setMinScore] = useState<number>(70);
  const [logLevel, setLogLevel] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'status' | 'config' | 'logs'>('status');
  const [submissionMode, setSubmissionModeState] = useState<SubmissionModeResponse | null>(null);
  const [modeChanging, setModeChanging] = useState(false);
  const [autoProcessing, setAutoProcessing] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [healthRes, statusRes, configRes, logsRes, modeRes] = await Promise.all([
        getHealth(),
        getPipelineStatus(),
        getConfig(),
        getLogs(logLevel || undefined, 100),
        getSubmissionMode(),
      ]);
      setHealth(healthRes);
      setPipelineStatus(statusRes);
      setConfigItems(configRes.config);
      setSubmissionModeState(modeRes);
      // Initialize edited config with current values
      const initialEdited: Record<string, string> = {};
      configRes.config.forEach((item: ConfigItem) => {
        initialEdited[item.key] = item.sensitive ? item.value : item.raw_value;
      });
      setEditedConfig(initialEdited);
      setLogs(logsRes.logs);
    } catch (err) {
      console.error('Failed to fetch admin data:', err);
      setError('Failed to load admin data');
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (key: string, value: string) => {
    setEditedConfig(prev => ({ ...prev, [key]: value }));
  };

  const handleSaveConfig = async () => {
    setConfigSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await updateConfig(editedConfig);
      setSuccess(result.message);
      // Refresh config to get updated masked values
      const configRes = await getConfig();
      setConfigItems(configRes.config);
      const newEdited: Record<string, string> = {};
      configRes.config.forEach((item: ConfigItem) => {
        newEdited[item.key] = item.sensitive ? item.value : item.raw_value;
      });
      setEditedConfig(newEdited);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setConfigSaving(false);
    }
  };

  const hasConfigChanges = () => {
    return configItems.some((item) => {
      const originalValue = item.sensitive ? item.value : item.raw_value;
      return editedConfig[item.key] !== originalValue;
    });
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    // Refresh logs when filter changes
    getLogs(logLevel || undefined, 100)
      .then((res) => setLogs(res.logs))
      .catch(console.error);
  }, [logLevel]);

  const handleTrigger = async () => {
    setTriggerLoading(true);
    setError(null);
    setSuccess(null);
    try {
      // Parse URLs if source is 'urls'
      const urlList = triggerSource === 'urls'
        ? jobUrls.split('\n').map(u => u.trim()).filter(u => u.length > 0)
        : undefined;

      if (triggerSource === 'urls' && (!urlList || urlList.length === 0)) {
        setError('Please enter at least one Upwork job URL');
        setTriggerLoading(false);
        return;
      }

      const result = await triggerPipeline(
        triggerSource,
        triggerLimit,
        triggerKeywords || undefined,
        triggerLocation || undefined,
        runFullPipeline,
        minScore,
        fromDate || undefined,
        toDate || undefined,
        minHourly ? parseInt(minHourly) : undefined,
        maxHourly ? parseInt(maxHourly) : undefined,
        minFixed ? parseInt(minFixed) : undefined,
        maxFixed ? parseInt(maxFixed) : undefined,
        urlList
      );
      let msg = runFullPipeline
        ? `Full Pipeline triggered! Run ID: ${result.run_id} (score >= ${minScore})`
        : triggerSource === 'urls'
        ? `URL import triggered! Run ID: ${result.run_id} (${urlList?.length} URLs)`
        : `Scrape triggered! Run ID: ${result.run_id}`;
      if (triggerKeywords) msg += ` | Keywords: ${triggerKeywords}`;
      if (triggerLocation) msg += ` | Location: ${triggerLocation}`;
      if (fromDate) msg += ` | From: ${fromDate}`;
      if (toDate) msg += ` | To: ${toDate}`;
      if (minHourly || maxHourly) msg += ` | Hourly: $${minHourly || '0'}-$${maxHourly || '∞'}`;
      if (minFixed || maxFixed) msg += ` | Fixed: $${minFixed || '0'}-$${maxFixed || '∞'}`;
      setSuccess(msg);
      // Refresh status
      const status = await getPipelineStatus();
      setPipelineStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger pipeline');
    } finally {
      setTriggerLoading(false);
    }
  };

  const handleModeChange = async (newMode: string) => {
    setModeChanging(true);
    setError(null);
    setSuccess(null);
    try {
      await setSubmissionMode(newMode);
      const modeRes = await getSubmissionMode();
      setSubmissionModeState(modeRes);
      setSuccess(`Submission mode changed to: ${newMode}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change mode');
    } finally {
      setModeChanging(false);
    }
  };

  const handleAutoProcess = async () => {
    setAutoProcessing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await autoProcessPendingJobs();
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to auto-process jobs');
    } finally {
      setAutoProcessing(false);
    }
  };

  const getHealthColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-100 text-green-800';
      case 'degraded':
        return 'bg-yellow-100 text-yellow-800';
      case 'unhealthy':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getModeColor = (mode: string) => {
    switch (mode) {
      case 'manual':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'semi_auto':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'automatic':
        return 'bg-green-100 text-green-800 border-green-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6 dark:text-white">Admin Panel</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6 dark:text-white">Admin Panel</h1>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-100 text-green-700 rounded-md">{success}</div>
      )}

      {/* Tabs */}
      <div className="flex border-b dark:border-gray-700 mb-6">
        {(['status', 'config', 'logs'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-medium capitalize ${
              activeTab === tab
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Status Tab */}
      {activeTab === 'status' && (
        <div className="space-y-6">
          {/* Submission Mode Selector */}
          <div className={`rounded-lg shadow p-4 border-2 ${getModeColor(submissionMode?.mode || 'manual')}`}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold dark:text-white">Submission Mode</h2>
                <p className="text-sm text-gray-600">{submissionMode?.description}</p>
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={submissionMode?.mode || 'manual'}
                  onChange={(e) => handleModeChange(e.target.value)}
                  disabled={modeChanging}
                  className={`px-4 py-2 border-2 rounded-lg font-medium ${getModeColor(submissionMode?.mode || 'manual')}`}
                >
                  {submissionMode?.available_modes.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.value === 'manual' ? 'Manual' : m.value === 'semi_auto' ? 'Semi-Auto' : 'Automatic'}
                    </option>
                  ))}
                </select>
                {modeChanging && <span className="text-sm text-gray-500 dark:text-gray-400">Saving...</span>}
              </div>
            </div>

            {/* Mode descriptions */}
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className={`p-3 rounded-lg ${submissionMode?.mode === 'manual' ? 'bg-white ring-2 ring-blue-400' : 'bg-gray-50'}`}>
                <div className="font-medium text-blue-700">Manual</div>
                <p className="text-gray-600 text-xs mt-1">
                  Approve each job manually, then click Submit after video generation
                </p>
              </div>
              <div className={`p-3 rounded-lg ${submissionMode?.mode === 'semi_auto' ? 'bg-white ring-2 ring-yellow-400' : 'bg-gray-50'}`}>
                <div className="font-medium text-yellow-700">Semi-Auto</div>
                <p className="text-gray-600 text-xs mt-1">
                  Auto-approve and generate videos, but require manual Submit to Upwork
                </p>
              </div>
              <div className={`p-3 rounded-lg ${submissionMode?.mode === 'automatic' ? 'bg-white ring-2 ring-green-400' : 'bg-gray-50'}`}>
                <div className="font-medium text-green-700">Automatic</div>
                <p className="text-gray-600 text-xs mt-1">
                  Full automation: approve, generate videos, and submit to Upwork
                </p>
              </div>
            </div>

            {/* Auto-process button for semi_auto and automatic modes */}
            {(submissionMode?.mode === 'semi_auto' || submissionMode?.mode === 'automatic') && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <button
                  onClick={handleAutoProcess}
                  disabled={autoProcessing}
                  className={`px-4 py-2 rounded-lg text-white font-medium ${
                    submissionMode?.mode === 'automatic'
                      ? 'bg-green-600 hover:bg-green-700'
                      : 'bg-yellow-600 hover:bg-yellow-700'
                  } disabled:opacity-50`}
                >
                  {autoProcessing ? 'Processing...' : 'Process All Pending Jobs Now'}
                </button>
                <p className="text-xs text-gray-500 mt-2">
                  {submissionMode?.mode === 'automatic'
                    ? 'This will auto-approve, generate videos, and submit all pending jobs to Upwork.'
                    : 'This will auto-approve and generate videos for all pending jobs. You\'ll still need to manually submit.'}
                </p>
              </div>
            )}
          </div>

          {/* Health Status */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">System Health</h2>
            {health && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Overall Status</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm font-medium ${getHealthColor(health.status)}`}>
                    {health.status}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Google Sheets</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.sheets ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.sheets ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Slack</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.slack ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.slack ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">OpenAI</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.openai ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.openai ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Pipeline Status */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">Pipeline Status</h2>
            {pipelineStatus && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Running</p>
                  <p className={`font-semibold ${pipelineStatus.is_running ? 'text-blue-600' : 'text-gray-600'}`}>
                    {pipelineStatus.is_running ? 'Yes' : 'No'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Last Run</p>
                  <p className="font-semibold text-sm">
                    {formatDate(pipelineStatus.last_run_time)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Last Status</p>
                  <p className={`font-semibold ${
                    pipelineStatus.last_run_status === 'success'
                      ? 'text-green-600'
                      : pipelineStatus.last_run_status === 'error'
                      ? 'text-red-600'
                      : 'text-gray-600'
                  }`}>
                    {pipelineStatus.last_run_status || 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Jobs Processed</p>
                  <p className="font-semibold">{pipelineStatus.jobs_processed_today}</p>
                </div>
              </div>
            )}
          </div>

          {/* Trigger Pipeline */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">Trigger Pipeline</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">Source</label>
                <select
                  value={triggerSource}
                  onChange={(e) => setTriggerSource(e.target.value as 'apify' | 'gmail' | 'urls')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                >
                  <option value="apify">Apify (Scrape New Jobs)</option>
                  <option value="gmail">Gmail (Process Alerts)</option>
                  <option value="urls">URLs (Direct Job Links)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">Limit</label>
                <input
                  type="number"
                  value={triggerLimit}
                  onChange={(e) => setTriggerLimit(parseInt(e.target.value) || 10)}
                  min={1}
                  max={100}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Keywords <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={triggerKeywords}
                  onChange={(e) => setTriggerKeywords(e.target.value)}
                  placeholder="e.g., python, react, automation"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Location <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={triggerLocation}
                  onChange={(e) => setTriggerLocation(e.target.value)}
                  placeholder="e.g., United States, Remote"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  From Date <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  To Date <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
            </div>

            {/* Budget Filters */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Min Hourly ($)
                </label>
                <input
                  type="number"
                  value={minHourly}
                  onChange={(e) => setMinHourly(e.target.value)}
                  placeholder="5"
                  min={0}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Max Hourly ($)
                </label>
                <input
                  type="number"
                  value={maxHourly}
                  onChange={(e) => setMaxHourly(e.target.value)}
                  placeholder="1500"
                  min={0}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Min Fixed ($)
                </label>
                <input
                  type="number"
                  value={minFixed}
                  onChange={(e) => setMinFixed(e.target.value)}
                  placeholder="50"
                  min={0}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Max Fixed ($)
                </label>
                <input
                  type="number"
                  value={maxFixed}
                  onChange={(e) => setMaxFixed(e.target.value)}
                  placeholder="100000"
                  min={0}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
            </div>

            {/* URL Input - only show when source is 'urls' */}
            {triggerSource === 'urls' && (
              <div className="mt-4">
                <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">
                  Job URLs <span className="text-gray-400">(one per line)</span>
                </label>
                <textarea
                  value={jobUrls}
                  onChange={(e) => setJobUrls(e.target.value)}
                  placeholder="https://www.upwork.com/jobs/~01234567890123456789&#10;https://www.upwork.com/jobs/~09876543210987654321"
                  rows={5}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Paste Upwork job URLs, one per line. They will be fetched and added to the pipeline.
                </p>
              </div>
            )}

            {/* Full Pipeline Options */}
            <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
              <div className="flex items-center gap-3 mb-3">
                <input
                  type="checkbox"
                  id="runFullPipeline"
                  checked={runFullPipeline}
                  onChange={(e) => setRunFullPipeline(e.target.checked)}
                  className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                />
                <label htmlFor="runFullPipeline" className="font-medium text-gray-700 dark:text-gray-200">
                  Run Full Pipeline
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-3">
                When enabled, runs the complete workflow: Scrape → Score → Extract → Generate Proposal → Boost Decision → Send to Approval.
                When disabled, only scrapes and imports jobs to the sheet.
              </p>
              {runFullPipeline && (
                <div className="flex items-center gap-4">
                  <label className="text-sm text-gray-600 dark:text-gray-300">Min Fit Score:</label>
                  <input
                    type="number"
                    value={minScore}
                    onChange={(e) => setMinScore(parseInt(e.target.value) || 70)}
                    min={0}
                    max={100}
                    className="w-20 px-2 py-1 border border-gray-300 rounded-md text-sm"
                  />
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Jobs below this score will be filtered out
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-4 mt-4">
              <button
                onClick={handleTrigger}
                disabled={triggerLoading || pipelineStatus?.is_running}
                className={`px-4 py-2 rounded-md text-white ${
                  runFullPipeline
                    ? 'bg-green-600 hover:bg-green-700'
                    : 'bg-blue-600 hover:bg-blue-700'
                } disabled:opacity-50`}
              >
                {triggerLoading
                  ? 'Triggering...'
                  : runFullPipeline
                  ? 'Run Full Pipeline'
                  : 'Scrape Only'}
              </button>
              {triggerSource === 'gmail' && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Keywords and location filters only apply to Apify source
                </p>
              )}
            </div>
            {pipelineStatus?.is_running && (
              <p className="mt-2 text-sm text-yellow-600">
                Pipeline is currently running. Please wait for it to complete.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Config Tab */}
      {activeTab === 'config' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-lg font-semibold dark:text-white">Configuration</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Edit environment variables. Sensitive values are masked.
              </p>
            </div>
            <button
              onClick={handleSaveConfig}
              disabled={configSaving || !hasConfigChanges()}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {configSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
          {configItems.length > 0 && (
            <div className="space-y-4">
              {configItems.map((item) => (
                <div key={item.key} className="border-b border-gray-100 pb-4">
                  <div className="flex justify-between items-start mb-1">
                    <label className="font-medium text-sm text-gray-700">
                      {item.label}
                      {item.sensitive && (
                        <span className="ml-2 text-xs text-yellow-600 bg-yellow-50 px-1 rounded">
                          Sensitive
                        </span>
                      )}
                      {!item.editable && (
                        <span className="ml-2 text-xs text-gray-500 bg-gray-100 px-1 rounded">
                          Read-only
                        </span>
                      )}
                    </label>
                    <span className={`text-xs ${item.is_set ? 'text-green-600' : 'text-red-500'}`}>
                      {item.is_set ? 'Set' : 'Not Set'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-2">{item.description}</p>
                  <input
                    type={item.sensitive ? 'password' : 'text'}
                    value={editedConfig[item.key] || ''}
                    onChange={(e) => handleConfigChange(item.key, e.target.value)}
                    disabled={!item.editable}
                    placeholder={item.sensitive ? '••••••••' : '(not set)'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm disabled:bg-gray-50 disabled:text-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-gray-400 mt-1 font-mono">{item.key}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold dark:text-white">Execution Logs</h2>
            <div className="flex gap-2">
              <select
                value={logLevel}
                onChange={(e) => setLogLevel(e.target.value)}
                className="px-3 py-1 border border-gray-300 rounded-md text-sm"
              >
                <option value="">All Levels</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
                <option value="DEBUG">DEBUG</option>
              </select>
              <button
                onClick={fetchData}
                className="px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded-md text-sm"
              >
                Refresh
              </button>
            </div>
          </div>
          <div className="max-h-[500px] overflow-y-auto font-mono text-sm">
            {logs.length === 0 ? (
              <p className="text-gray-500 text-center py-4">No logs available</p>
            ) : (
              <div className="space-y-1">
                {logs.map((log, idx) => (
                  <div key={idx} className="py-1 border-b border-gray-100">
                    <span className="text-gray-400 mr-2">
                      {formatDate(log.timestamp)}
                    </span>
                    <span className={`mr-2 font-medium ${LOG_LEVEL_COLORS[log.level] || 'text-gray-600'}`}>
                      [{log.level}]
                    </span>
                    <span>{log.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
