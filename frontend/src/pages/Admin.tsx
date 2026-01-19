import { useState, useEffect } from 'react';
import {
  getHealth,
  getConfig,
  updateConfig,
  getPipelineStatus,
  triggerPipeline,
  getLogs,
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
  const [triggerSource, setTriggerSource] = useState<'apify' | 'gmail'>('apify');
  const [triggerLimit, setTriggerLimit] = useState<number>(10);
  const [triggerKeywords, setTriggerKeywords] = useState<string>('');
  const [triggerLocation, setTriggerLocation] = useState<string>('');
  const [runFullPipeline, setRunFullPipeline] = useState<boolean>(false);
  const [minScore, setMinScore] = useState<number>(70);
  const [logLevel, setLogLevel] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'status' | 'config' | 'logs'>('status');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [healthRes, statusRes, configRes, logsRes] = await Promise.all([
        getHealth(),
        getPipelineStatus(),
        getConfig(),
        getLogs(logLevel || undefined, 100),
      ]);
      setHealth(healthRes);
      setPipelineStatus(statusRes);
      setConfigItems(configRes.config);
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
      const result = await triggerPipeline(
        triggerSource,
        triggerLimit,
        triggerKeywords || undefined,
        triggerLocation || undefined,
        runFullPipeline,
        minScore
      );
      let msg = runFullPipeline
        ? `Full Pipeline triggered! Run ID: ${result.run_id} (score >= ${minScore})`
        : `Scrape triggered! Run ID: ${result.run_id}`;
      if (triggerKeywords) msg += ` | Keywords: ${triggerKeywords}`;
      if (triggerLocation) msg += ` | Location: ${triggerLocation}`;
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

  if (loading) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Admin Panel</h1>
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Admin Panel</h1>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-md">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-100 text-green-700 rounded-md">{success}</div>
      )}

      {/* Tabs */}
      <div className="flex border-b mb-6">
        {(['status', 'config', 'logs'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-medium capitalize ${
              activeTab === tab
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Status Tab */}
      {activeTab === 'status' && (
        <div className="space-y-6">
          {/* Health Status */}
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4">System Health</h2>
            {health && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Overall Status</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm font-medium ${getHealthColor(health.status)}`}>
                    {health.status}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Google Sheets</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.sheets ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.sheets ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Slack</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.slack ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.slack ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500">OpenAI</p>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${health.services.openai ? 'text-green-600' : 'text-red-600'}`}>
                    {health.services.openai ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Pipeline Status */}
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4">Pipeline Status</h2>
            {pipelineStatus && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-500">Running</p>
                  <p className={`font-semibold ${pipelineStatus.is_running ? 'text-blue-600' : 'text-gray-600'}`}>
                    {pipelineStatus.is_running ? 'Yes' : 'No'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Last Run</p>
                  <p className="font-semibold text-sm">
                    {formatDate(pipelineStatus.last_run_time)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Last Status</p>
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
                  <p className="text-sm text-gray-500">Jobs Processed</p>
                  <p className="font-semibold">{pipelineStatus.jobs_processed_today}</p>
                </div>
              </div>
            )}
          </div>

          {/* Trigger Pipeline */}
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="text-lg font-semibold mb-4">Trigger Pipeline</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-sm text-gray-500 mb-1">Source</label>
                <select
                  value={triggerSource}
                  onChange={(e) => setTriggerSource(e.target.value as 'apify' | 'gmail')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                >
                  <option value="apify">Apify (Scrape New Jobs)</option>
                  <option value="gmail">Gmail (Process Alerts)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Limit</label>
                <input
                  type="number"
                  value={triggerLimit}
                  onChange={(e) => setTriggerLimit(parseInt(e.target.value) || 10)}
                  min={1}
                  max={100}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">
                  Keywords <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={triggerKeywords}
                  onChange={(e) => setTriggerKeywords(e.target.value)}
                  placeholder="e.g., python, react, automation"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">
                  Location <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={triggerLocation}
                  onChange={(e) => setTriggerLocation(e.target.value)}
                  placeholder="e.g., United States, Remote"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  disabled={triggerSource === 'gmail'}
                />
              </div>
            </div>

            {/* Full Pipeline Options */}
            <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-3 mb-3">
                <input
                  type="checkbox"
                  id="runFullPipeline"
                  checked={runFullPipeline}
                  onChange={(e) => setRunFullPipeline(e.target.checked)}
                  className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                />
                <label htmlFor="runFullPipeline" className="font-medium text-gray-700">
                  Run Full Pipeline
                </label>
              </div>
              <p className="text-sm text-gray-500 mb-3">
                When enabled, runs the complete workflow: Scrape → Score → Extract → Generate Proposal → Boost Decision → Send to Approval.
                When disabled, only scrapes and imports jobs to the sheet.
              </p>
              {runFullPipeline && (
                <div className="flex items-center gap-4">
                  <label className="text-sm text-gray-600">Min Fit Score:</label>
                  <input
                    type="number"
                    value={minScore}
                    onChange={(e) => setMinScore(parseInt(e.target.value) || 70)}
                    min={0}
                    max={100}
                    className="w-20 px-2 py-1 border border-gray-300 rounded-md text-sm"
                  />
                  <span className="text-sm text-gray-500">
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
                <p className="text-sm text-gray-500">
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
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-lg font-semibold">Configuration</h2>
              <p className="text-sm text-gray-500">
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
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Execution Logs</h2>
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
