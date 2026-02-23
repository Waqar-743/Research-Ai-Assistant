import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Search,
  ChevronDown,
  ChevronUp,
  User,
  Database,
  Cpu,
  ShieldCheck,
  FileText,
  Loader2,
  History,
  ExternalLink,
  Download,
  Plus,
  CheckCircle2,
  Terminal,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import Markdown from 'react-markdown';
import {
  ResearchOptions,
  LogEntry,
  AgentStatus,
  AgentState,
  ResearchHistory,
  ResearchReport,
  WSMessage,
} from './types';
import { researchService } from './services/researchService';

/* ------------------------------------------------------------------ */
/*  Reusable UI Components                                             */
/* ------------------------------------------------------------------ */

const GlassCard = ({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) => (
  <div
    className={`bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl shadow-xl ${className}`}
  >
    {children}
  </div>
);

const AgentIcon = ({
  name,
  status,
  isActive,
}: {
  name: string;
  status: AgentStatus;
  isActive: boolean;
}) => {
  const icons: Record<string, React.ElementType> = {
    'User Proxy': User,
    Researcher: Database,
    Analyst: Cpu,
    'Fact Checker': ShieldCheck,
    'Report Generator': FileText,
  };
  const Icon = icons[name] || Search;

  const getColors = () => {
    switch (status) {
      case AgentStatus.COMPLETED:
        return 'text-emerald-400 border-emerald-400/50 bg-emerald-400/10';
      case AgentStatus.IN_PROGRESS:
        return 'text-amber-400 border-amber-400/50 bg-amber-400/10';
      case AgentStatus.FAILED:
        return 'text-rose-400 border-rose-400/50 bg-rose-400/10';
      default:
        return 'text-slate-400 border-slate-400/30 bg-slate-400/5';
    }
  };

  return (
    <div className="relative">
      {/* Outer pulsing ring for active agent */}
      {isActive && (
        <>
          <motion.div
            className="absolute -inset-3 rounded-2xl border-2 border-amber-400/40"
            animate={{ scale: [1, 1.18, 1], opacity: [0.6, 0, 0.6] }}
            transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
          />
          <motion.div
            className="absolute -inset-1.5 rounded-xl border border-amber-400/30"
            animate={{ scale: [1, 1.08, 1], opacity: [0.8, 0.2, 0.8] }}
            transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
          />
          {/* Glow backdrop */}
          <motion.div
            className="absolute -inset-4 rounded-2xl bg-amber-400/10 blur-xl -z-10"
            animate={{ opacity: [0.3, 0.7, 0.3] }}
            transition={{ repeat: Infinity, duration: 2, ease: 'easeInOut' }}
          />
        </>
      )}

      {/* Completed checkmark flash */}
      {status === AgentStatus.COMPLETED && (
        <motion.div
          className="absolute -inset-2 rounded-xl bg-emerald-400/20 blur-lg -z-10"
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: [0, 0.8, 0.3], scale: [0.5, 1.2, 1] }}
          transition={{ duration: 0.6 }}
        />
      )}

      <motion.div
        animate={
          isActive
            ? { scale: [1, 1.08, 1], rotate: [0, 3, -3, 0] }
            : status === AgentStatus.COMPLETED
              ? { scale: 1 }
              : {}
        }
        transition={
          isActive
            ? { repeat: Infinity, duration: 2.5, ease: 'easeInOut' }
            : { duration: 0.4 }
        }
        className={`p-4 rounded-xl border-2 transition-all duration-500 relative ${getColors()}`}
      >
        <Icon size={32} />
      </motion.div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Agent name mapping (backend → frontend display name)               */
/* ------------------------------------------------------------------ */

const AGENT_NAME_MAP: Record<string, string> = {
  user_proxy: 'User Proxy',
  researcher: 'Researcher',
  analyst: 'Analyst',
  fact_checker: 'Fact Checker',
  report_generator: 'Report Generator',
};

const AGENT_STATUS_MAP: Record<string, AgentStatus> = {
  pending: AgentStatus.PENDING,
  in_progress: AgentStatus.IN_PROGRESS,
  completed: AgentStatus.COMPLETED,
  failed: AgentStatus.FAILED,
};

/* ------------------------------------------------------------------ */
/*  Main Application                                                   */
/* ------------------------------------------------------------------ */

export default function App() {
  const [view, setView] = useState<
    'landing' | 'progress' | 'report' | 'history'
  >('landing');
  const [history, setHistory] = useState<ResearchHistory[]>([]);
  const [options, setOptions] = useState<ResearchOptions>({
    query: '',
    focusAreas: 'social, environmental, ethical',
    sources: ['Academic', 'News', 'Official', 'Wikipedia'],
    format: 'Markdown',
    citationStyle: 'APA',
    maxSources: 300,
    mode: 'Automatic',
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agents, setAgents] = useState<AgentState[]>([
    { id: '1', name: 'User Proxy', description: 'Query analysis', status: AgentStatus.PENDING, icon: 'user' },
    { id: '2', name: 'Researcher', description: 'Data collection', status: AgentStatus.PENDING, icon: 'database' },
    { id: '3', name: 'Analyst', description: 'Synthesis & patterns', status: AgentStatus.PENDING, icon: 'cpu' },
    { id: '4', name: 'Fact Checker', description: 'Verification', status: AgentStatus.PENDING, icon: 'shield' },
    { id: '5', name: 'Report Generator', description: 'Report creation', status: AgentStatus.PENDING, icon: 'file' },
  ]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ---- auto-scroll logs ---- */
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  /* ---- backend health check on mount ---- */
  useEffect(() => {
    researchService.checkHealth().then(setBackendOnline);
  }, []);

  /* ---- load history from backend on mount ---- */
  useEffect(() => {
    researchService
      .getHistory()
      .then(({ sessions }) => setHistory(sessions))
      .catch(() => {});
  }, []);

  /* ---- cleanup ws & poll on unmount ---- */
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  /* ---- helper: add log ---- */
  const addLog = useCallback(
    (agent: string, message: string, type: LogEntry['type'] = 'info') => {
      const timestamp = new Date().toLocaleTimeString('en-GB', {
        hour12: false,
      });
      setLogs((prev) => [...prev, { timestamp, agent, message, type }]);
    },
    [],
  );

  /* ---- WebSocket message handler ---- */
  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case 'connection_established':
          addLog('System', 'Connected to research pipeline', 'success');
          break;

        case 'agent_status_update': {
          const displayName =
            AGENT_NAME_MAP[msg.agent] ?? msg.agent;
          const mappedStatus =
            AGENT_STATUS_MAP[msg.status] ?? AgentStatus.PENDING;

          setAgents((prev) =>
            prev.map((a) =>
              a.name === displayName
                ? { ...a, status: mappedStatus }
                : a,
            ),
          );
          setProgress(msg.progress);

          if (msg.output) {
            addLog(displayName, msg.output, 'info');
          }
          if (msg.error) {
            addLog(displayName, msg.error, 'error');
          }
          break;
        }

        case 'phase_update':
          addLog(
            'Pipeline',
            msg.message ?? `Phase: ${msg.phase} → ${msg.status}`,
            'info',
          );
          break;

        case 'research_complete':
          addLog('System', 'Research complete — loading report…', 'success');
          setProgress(100);
          // Fetch full results
          if (sessionId) {
            researchService
              .getResearchResults(sessionId)
              .then((res) => {
                const r = (res as Record<string, unknown>).report as ResearchReport | undefined;
                if (r) {
                  setReport(r);
                  setView('report');
                  // refresh history
                  researchService
                    .getHistory()
                    .then(({ sessions }) => setHistory(sessions))
                    .catch(() => {});
                }
              })
              .catch((e) => addLog('System', `Error loading results: ${e}`, 'error'));
          }
          break;

        case 'research_error':
          addLog('System', `Error: ${msg.error}`, 'error');
          setError(msg.error);
          break;
      }
    },
    [addLog, sessionId],
  );

  /* ---- Start research ---- */
  const startResearch = async () => {
    if (!options.query.trim()) return;

    setView('progress');
    setProgress(0);
    setLogs([]);
    setError(null);
    setReport(null);
    setAgents((prev) =>
      prev.map((a) => ({ ...a, status: AgentStatus.PENDING })),
    );

    try {
      addLog('System', 'Submitting research request…', 'info');

      const result = await researchService.startResearch(options);
      const sid = result.session_id;
      setSessionId(sid);

      addLog('System', `Session started: ${sid}`, 'success');

      // Connect WebSocket for real-time updates
      wsRef.current?.close();
      wsRef.current = researchService.connectWebSocket(
        sid,
        handleWSMessage,
        () => addLog('System', 'WebSocket disconnected', 'warning'),
      );

      // Fall-back polling every 5 s (in case WS updates are sparse)
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const status = await researchService.getResearchStatus(sid);
          setProgress(status.progress);

          if (status.status === 'completed' || status.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
          }

          if (
            status.status === 'completed' &&
            view !== 'report'
          ) {
            const res = await researchService.getResearchResults(sid);
            const r = (res as Record<string, unknown>).report as ResearchReport | undefined;
            if (r) {
              setReport(r);
              setView('report');
              researchService
                .getHistory()
                .then(({ sessions }) => setHistory(sessions))
                .catch(() => {});
            }
          }
        } catch {
          /* polling errors are non-fatal */
        }
      }, 5000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      addLog('System', `Failed to start research: ${msg}`, 'error');
      setError(msg);
    }
  };

  /* ---- Export helpers ---- */
  const exportMarkdown = () => {
    if (!report) return;
    const md = [
      `# ${report.title}\n`,
      `## Executive Summary\n${report.executiveSummary}\n`,
      report.methodology ? `## Methodology\n${report.methodology}\n` : '',
      ...(report.sections ?? []).map(
        (s) => `## ${s.heading}\n${s.content}\n`,
      ),
      report.sources?.length
        ? `## Sources\n${report.sources.map((s) => `- [${s.title}](${s.url}) — ${s.relevance}`).join('\n')}`
        : '',
    ].join('\n');

    const blob = new Blob([md], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${report.title?.replace(/\s+/g, '_') ?? 'report'}.md`;
    a.click();
  };

  const exportHTML = () => {
    if (!report) return;
    const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>${report.title}</title>
<style>body{font-family:Inter,sans-serif;max-width:800px;margin:0 auto;padding:2rem;color:#1e293b}h1{color:#4f46e5}h2{margin-top:2rem}a{color:#4f46e5}</style>
</head><body>
<h1>${report.title}</h1>
<h2>Executive Summary</h2><p>${report.executiveSummary}</p>
${report.methodology ? `<h2>Methodology</h2><p>${report.methodology}</p>` : ''}
${(report.sections ?? []).map((s) => `<h2>${s.heading}</h2><div>${s.content}</div>`).join('')}
${report.sources?.length ? `<h2>Sources</h2><ul>${report.sources.map((s) => `<li><a href="${s.url}">${s.title}</a> — ${s.relevance}</li>`).join('')}</ul>` : ''}
</body></html>`;

    const blob = new Blob([html], { type: 'text/html' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${report.title?.replace(/\s+/g, '_') ?? 'report'}.html`;
    a.click();
  };

  /* ---------------------------------------------------------------- */
  /*  RENDER                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#1a0b2e] via-[#4a1d4d] to-[#d97706] text-white font-sans selection:bg-amber-500/30">
      {/* ---- Header ---- */}
      <header className="px-8 py-4 flex items-center justify-between border-b border-white/10 bg-black/20 backdrop-blur-sm sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/20">
            <Cpu className="text-white" size={24} />
          </div>
          <span className="text-xl font-bold tracking-tight">
            Research Assistant
          </span>
          {backendOnline !== null && (
            <span
              className={`ml-2 inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-widest ${
                backendOnline
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-rose-500/20 text-rose-400'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  backendOnline ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              {backendOnline ? 'Online' : 'Offline'}
            </span>
          )}
        </div>

        <nav className="flex items-center gap-8">
          <button
            onClick={() => setView('landing')}
            className={`text-sm font-medium transition-colors ${
              view === 'landing'
                ? 'text-white'
                : 'text-white/60 hover:text-white'
            }`}
          >
            Research
          </button>
          <button
            onClick={() => {
              setView('history');
              researchService
                .getHistory()
                .then(({ sessions }) => setHistory(sessions))
                .catch(() => {});
            }}
            className={`text-sm font-medium transition-colors flex items-center gap-2 ${
              view === 'history'
                ? 'text-white'
                : 'text-white/60 hover:text-white'
            }`}
          >
            <History size={16} />
            History
          </button>
        </nav>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-12">
        <AnimatePresence mode="wait">
          {/* ============================================================ */}
          {/*  LANDING VIEW                                                 */}
          {/* ============================================================ */}
          {view === 'landing' && (
            <motion.div
              key="landing"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex flex-col items-center text-center"
            >
              <h1 className="text-6xl font-black mb-6 bg-gradient-to-r from-orange-400 via-rose-400 to-purple-400 bg-clip-text text-transparent tracking-tight">
                Multi-Agent Research Assistant
              </h1>
              <p className="text-xl text-white/70 max-w-2xl mb-12 leading-relaxed">
                5 specialized AI agents collaborate to research, analyze,
                verify, and generate comprehensive reports on any topic.
              </p>

              {/* Backend offline banner */}
              {backendOnline === false && (
                <div className="mb-6 flex items-center gap-3 px-5 py-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
                  <AlertCircle size={18} />
                  <span>
                    Backend is unreachable. Make sure the server is running on
                    port 8000.
                  </span>
                  <button
                    onClick={() =>
                      researchService.checkHealth().then(setBackendOnline)
                    }
                    className="ml-2 underline hover:text-white"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
              )}

              <GlassCard className="w-full max-w-5xl p-8">
                <div className="relative mb-6">
                  <textarea
                    value={options.query}
                    onChange={(e) =>
                      setOptions({ ...options, query: e.target.value })
                    }
                    placeholder="What are the major challenges of AI in 2026?"
                    className="w-full bg-black/20 border border-white/10 rounded-xl p-4 pb-16 text-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all min-h-[160px] resize-none placeholder:text-white/20"
                  />
                  <motion.button
                    whileHover={{
                      scale: 1.05,
                      filter: 'brightness(1.1)',
                    }}
                    whileTap={{ scale: 0.95 }}
                    onClick={startResearch}
                    disabled={!options.query.trim() || backendOnline === false}
                    style={{
                      backgroundColor: '#432371',
                      color: '#faae7b',
                    }}
                    className="absolute bottom-4 right-4 px-5 py-2 rounded-lg font-bold text-sm transition-all shadow-lg flex items-center gap-2 group border border-[#faae7b]/20 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span>Start Research</span>
                    <Search
                      size={16}
                      className="group-hover:rotate-12 transition-transform"
                    />
                  </motion.button>
                </div>

                {/* Advanced options */}
                <div className="text-left">
                  <button
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-2 text-sm font-semibold text-white/60 hover:text-white transition-colors mb-6"
                  >
                    {showAdvanced ? (
                      <ChevronUp size={16} />
                    ) : (
                      <ChevronDown size={16} />
                    )}
                    Advanced Options
                  </button>

                  <AnimatePresence>
                    {showAdvanced && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="grid grid-cols-1 md:grid-cols-2 gap-8 overflow-hidden"
                      >
                        <div className="space-y-4">
                          <div>
                            <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                              Focus Areas
                            </label>
                            <input
                              type="text"
                              value={options.focusAreas}
                              onChange={(e) =>
                                setOptions({
                                  ...options,
                                  focusAreas: e.target.value,
                                })
                              }
                              className="w-full bg-black/20 border border-white/10 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-white/30"
                            />
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                                Report Format
                              </label>
                              <select
                                value={options.format}
                                onChange={(e) =>
                                  setOptions({
                                    ...options,
                                    format: e.target.value,
                                  })
                                }
                                className="w-full bg-black/40 border border-white/10 rounded-full px-4 py-2 text-sm appearance-none focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                              >
                                <option value="Markdown">Markdown</option>
                                <option value="PDF">PDF</option>
                                <option value="HTML">HTML</option>
                              </select>
                            </div>
                            <div>
                              <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                                Citation Style
                              </label>
                              <select
                                value={options.citationStyle}
                                onChange={(e) =>
                                  setOptions({
                                    ...options,
                                    citationStyle: e.target.value,
                                  })
                                }
                                className="w-full bg-black/40 border border-white/10 rounded-full px-4 py-2 text-sm appearance-none focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                              >
                                <option value="APA">APA</option>
                                <option value="MLA">MLA</option>
                                <option value="Chicago">Chicago</option>
                                <option value="Harvard">Harvard</option>
                              </select>
                            </div>
                          </div>
                        </div>

                        <div className="space-y-4">
                          <div>
                            <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                              Source Preferences
                            </label>
                            <div className="bg-black/20 border border-white/10 rounded-xl p-3 text-sm text-white/60 space-y-1">
                              {options.sources.map((s) => (
                                <div
                                  key={s}
                                  className="flex items-center gap-2"
                                >
                                  <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full" />
                                  {s}
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                                Max Sources
                              </label>
                              <input
                                type="number"
                                value={options.maxSources}
                                onChange={(e) =>
                                  setOptions({
                                    ...options,
                                    maxSources: parseInt(e.target.value) || 50,
                                  })
                                }
                                className="w-full bg-black/20 border border-white/10 rounded-full px-4 py-2 text-sm focus:outline-none"
                              />
                            </div>
                            <div>
                              <label className="text-[10px] uppercase tracking-widest font-bold text-white/40 mb-2 block">
                                Mode
                              </label>
                              <select
                                value={options.mode}
                                onChange={(e) =>
                                  setOptions({
                                    ...options,
                                    mode: e.target.value,
                                  })
                                }
                                className="w-full bg-black/40 border border-white/10 rounded-full px-4 py-2 text-sm appearance-none focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                              >
                                <option value="Automatic">Automatic</option>
                                <option value="Manual">Manual</option>
                                <option value="Deep Research">
                                  Deep Research
                                </option>
                              </select>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </GlassCard>
            </motion.div>
          )}

          {/* ============================================================ */}
          {/*  PROGRESS VIEW                                                */}
          {/* ============================================================ */}
          {view === 'progress' && (
            <motion.div
              key="progress"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-8"
            >
              {/* Error banner */}
              {error && (
                <div className="flex items-center gap-3 px-5 py-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
                  <AlertCircle size={18} />
                  <span>{error}</span>
                  <button
                    onClick={() => {
                      setError(null);
                      startResearch();
                    }}
                    className="ml-auto flex items-center gap-1 underline hover:text-white"
                  >
                    <RefreshCw size={14} /> Retry
                  </button>
                </div>
              )}

              {/* Agent pipeline */}
              <GlassCard className="p-8">
                <div className="flex items-center justify-between mb-8">
                  <h3 className="text-xl font-bold">Agent Pipeline</h3>
                  <span className="text-xs text-white/40 font-mono">
                    {agents.filter((a) => a.status === AgentStatus.COMPLETED).length}/{agents.length} agents complete
                  </span>
                </div>

                <div className="flex items-start justify-between relative px-2">
                  {/* Background track line */}
                  <div className="absolute top-[34px] left-[40px] right-[40px] h-[3px] bg-white/5 rounded-full" />
                  {/* Completed fill line */}
                  <motion.div
                    className="absolute top-[34px] left-[40px] h-[3px] rounded-full bg-gradient-to-r from-emerald-500 via-emerald-400 to-emerald-300"
                    style={{ originX: 0 }}
                    initial={{ width: 0 }}
                    animate={{
                      width: (() => {
                        const completed = agents.filter((a) => a.status === AgentStatus.COMPLETED).length;
                        const inProgress = agents.findIndex((a) => a.status === AgentStatus.IN_PROGRESS);
                        const step = inProgress >= 0 ? inProgress : completed;
                        const maxW = 100 - (80 / agents.length); // account for icon width
                        return `${(step / (agents.length - 1)) * maxW}%`;
                      })(),
                    }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />

                  {agents.map((agent, idx) => {
                    const isCompleted = agent.status === AgentStatus.COMPLETED;
                    const isRunning = agent.status === AgentStatus.IN_PROGRESS;
                    const isFailed = agent.status === AgentStatus.FAILED;

                    return (
                      <motion.div
                        key={agent.id}
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.1, duration: 0.5, ease: 'backOut' }}
                        className="flex flex-col items-center gap-3 relative z-10 w-1/5"
                      >
                        <AgentIcon
                          name={agent.name}
                          status={agent.status}
                          isActive={isRunning}
                        />

                        <div className="text-center mt-1">
                          <p className="font-bold text-sm leading-tight">{agent.name}</p>
                          <p className="text-[10px] text-white/40 uppercase tracking-wider mt-0.5">
                            {agent.description}
                          </p>

                          <motion.div
                            className="mt-2 flex items-center justify-center gap-1.5"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.2 }}
                          >
                            {isRunning && (
                              <motion.div
                                animate={{ rotate: 360 }}
                                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                              >
                                <Loader2 size={12} className="text-amber-400" />
                              </motion.div>
                            )}
                            {isCompleted && (
                              <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ type: 'spring', stiffness: 400, damping: 12 }}
                              >
                                <CheckCircle2 size={12} className="text-emerald-400" />
                              </motion.div>
                            )}
                            {isFailed && (
                              <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: [0, 1.3, 1] }}
                                transition={{ duration: 0.4 }}
                              >
                                <AlertCircle size={12} className="text-rose-400" />
                              </motion.div>
                            )}
                            <span
                              className={`text-[10px] font-bold ${
                                isCompleted
                                  ? 'text-emerald-400'
                                  : isRunning
                                    ? 'text-amber-400'
                                    : isFailed
                                      ? 'text-rose-400'
                                      : 'text-white/20'
                              }`}
                            >
                              {agent.status}
                            </span>
                          </motion.div>
                        </div>

                        {/* Animated data-flow dots between agents */}
                        {idx < agents.length - 1 && isCompleted && (
                          <div className="absolute top-[34px] left-[calc(50%+28px)] w-[calc(100%-56px)] h-[3px] pointer-events-none overflow-hidden">
                            {[0, 1, 2].map((dot) => (
                              <motion.div
                                key={dot}
                                className="absolute top-[-2px] w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]"
                                initial={{ left: '-8px', opacity: 0 }}
                                animate={{ left: ['0%', '100%'], opacity: [0, 1, 1, 0] }}
                                transition={{
                                  repeat: Infinity,
                                  duration: 1.2,
                                  delay: dot * 0.4,
                                  ease: 'linear',
                                }}
                              />
                            ))}
                          </div>
                        )}
                        {idx < agents.length - 1 && isRunning && (
                          <div className="absolute top-[34px] left-[calc(50%+28px)] w-[calc(100%-56px)] h-[3px] pointer-events-none overflow-hidden">
                            <motion.div
                              className="absolute top-[-1px] w-6 h-[5px] rounded-full bg-gradient-to-r from-transparent via-amber-400 to-transparent"
                              animate={{ left: ['-24px', '100%'] }}
                              transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
                            />
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </div>

                {/* Progress bar */}
                <div className="mt-12 space-y-3">
                  <div className="flex justify-between text-sm font-bold">
                    <span className="text-white/60">
                      <motion.span
                        key={progress}
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-block"
                      >
                        {progress}%
                      </motion.span>{' '}
                      Overall Progress
                    </span>
                    <span className="text-amber-400">
                      {agents.find(
                        (a) => a.status === AgentStatus.IN_PROGRESS,
                      )?.name ?? 'Initializing…'}{' '}
                      is active
                    </span>
                  </div>
                  <div className="h-3 bg-black/30 rounded-full overflow-hidden border border-white/5 relative">
                    <motion.div
                      className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-amber-500 relative"
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    >
                      {/* Shimmer overlay */}
                      <motion.div
                        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent"
                        animate={{ x: ['-100%', '200%'] }}
                        transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
                      />
                    </motion.div>
                  </div>
                </div>
              </GlassCard>

              {/* Live log */}
              <GlassCard className="p-0 overflow-hidden border-indigo-500/20">
                <div className="px-6 py-4 bg-black/40 border-b border-white/10 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal size={18} className="text-indigo-400" />
                    <h3 className="font-bold">Live Activity</h3>
                  </div>
                  <button
                    onClick={() => setLogs([])}
                    className="text-[10px] uppercase tracking-widest font-bold px-3 py-1 bg-white/5 hover:bg-white/10 rounded-md transition-colors"
                  >
                    Clear
                  </button>
                </div>
                <div className="h-[300px] overflow-y-auto p-6 font-mono text-sm space-y-2 scrollbar-thin scrollbar-thumb-white/10">
                  {logs.map((log, i) => (
                    <div
                      key={i}
                      className="flex gap-4 animate-in fade-in slide-in-from-left-2 duration-300"
                    >
                      <span className="text-white/30 shrink-0">
                        {log.timestamp}
                      </span>
                      <span
                        className={`font-bold shrink-0 w-36 ${
                          log.agent === 'Researcher'
                            ? 'text-emerald-400'
                            : log.agent === 'Analyst'
                              ? 'text-amber-400'
                              : log.agent === 'Fact Checker'
                                ? 'text-indigo-400'
                                : log.agent === 'Report Generator'
                                  ? 'text-purple-400'
                                  : log.agent === 'System'
                                    ? 'text-cyan-400'
                                    : 'text-white/60'
                        }`}
                      >
                        [{log.agent}]
                      </span>
                      <span
                        className={
                          log.type === 'error'
                            ? 'text-rose-400'
                            : log.type === 'success'
                              ? 'text-emerald-400'
                              : log.type === 'warning'
                                ? 'text-amber-300'
                                : 'text-white/80'
                        }
                      >
                        {log.message}
                      </span>
                    </div>
                  ))}
                  <div ref={logEndRef} />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {/* ============================================================ */}
          {/*  HISTORY VIEW                                                 */}
          {/* ============================================================ */}
          {view === 'history' && (
            <motion.div
              key="history"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-8"
            >
              <div className="flex items-center justify-between mb-8">
                <h2 className="text-3xl font-black tracking-tight">
                  Research History
                </h2>
                <button
                  onClick={() => setView('landing')}
                  className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-bold transition-all border border-white/10"
                >
                  <Plus size={16} />
                  New Research
                </button>
              </div>

              {history.length === 0 ? (
                <GlassCard className="p-12 text-center">
                  <History
                    size={48}
                    className="mx-auto mb-4 text-white/20"
                  />
                  <p className="text-xl text-white/40">
                    No research history found.
                  </p>
                  <button
                    onClick={() => setView('landing')}
                    className="mt-6 text-indigo-400 font-bold hover:underline"
                  >
                    Start your first research task
                  </button>
                </GlassCard>
              ) : (
                <div className="grid gap-4">
                  {history.map((item) => (
                    <motion.div
                      key={item.id}
                      whileHover={{ scale: 1.01 }}
                      className="cursor-pointer"
                      onClick={async () => {
                        try {
                          const res =
                            await researchService.getResearchResults(
                              item.id,
                            );
                          const r = (res as Record<string, unknown>)
                            .report as ResearchReport | undefined;
                          if (r) {
                            setReport(r);
                            setOptions(item.options);
                            setView('report');
                          }
                        } catch {
                          /* session may not have results yet */
                        }
                      }}
                    >
                      <GlassCard className="p-6 flex items-center justify-between group hover:border-indigo-500/50 transition-all">
                        <div className="space-y-1">
                          <h3 className="text-lg font-bold group-hover:text-indigo-400 transition-colors">
                            {item.query}
                          </h3>
                          <div className="flex items-center gap-4 text-xs text-white/40 font-medium">
                            <span>
                              {new Date(item.timestamp).toLocaleString()}
                            </span>
                            <span className="px-2 py-0.5 bg-white/5 rounded uppercase tracking-wider">
                              {item.options.format}
                            </span>
                            <span className="px-2 py-0.5 bg-white/5 rounded uppercase tracking-wider">
                              {item.options.citationStyle}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right hidden sm:block">
                            <p className="text-[10px] uppercase tracking-widest font-bold text-white/20">
                              Status
                            </p>
                            <p
                              className={`text-xs font-bold ${
                                item.status === 'completed'
                                  ? 'text-emerald-400'
                                  : item.status === 'failed'
                                    ? 'text-rose-400'
                                    : 'text-amber-400'
                              }`}
                            >
                              {item.status}
                            </p>
                          </div>
                          <div className="p-2 bg-white/5 rounded-lg group-hover:bg-indigo-500/20 transition-all">
                            <ChevronDown
                              className="-rotate-90 text-white/40 group-hover:text-indigo-400"
                              size={20}
                            />
                          </div>
                        </div>
                      </GlassCard>
                    </motion.div>
                  ))}
                </div>
              )}
            </motion.div>
          )}

          {/* ============================================================ */}
          {/*  REPORT VIEW                                                  */}
          {/* ============================================================ */}
          {view === 'report' && report && (
            <motion.div
              key="report"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-8"
            >
              <div className="text-center space-y-4 mb-12">
                <h1 className="text-4xl font-black tracking-tight text-white leading-tight">
                  {report.title}
                </h1>
                <div className="flex items-center justify-center gap-3 flex-wrap">
                  <button
                    onClick={exportMarkdown}
                    className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-bold transition-all border border-white/10"
                  >
                    <Download size={16} />
                    Export Markdown
                  </button>
                  <button
                    onClick={exportHTML}
                    className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-bold transition-all border border-white/10"
                  >
                    <Download size={16} />
                    Export HTML
                  </button>
                  <button
                    onClick={() => setView('landing')}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-bold transition-all shadow-lg shadow-indigo-500/20"
                  >
                    <Plus size={16} />
                    New Research
                  </button>
                </div>
              </div>

              {/* Report content */}
              <div className="bg-white rounded-2xl shadow-2xl text-slate-900 overflow-hidden">
                <div className="bg-slate-50 border-b border-slate-200 px-8 py-4 flex gap-8">
                  {['Report', 'Findings', 'Sources'].map(
                    (tab) => (
                      <button
                        key={tab}
                        className={`text-sm font-bold pb-2 border-b-2 transition-all ${
                          tab === 'Report'
                            ? 'border-indigo-600 text-indigo-600'
                            : 'border-transparent text-slate-400 hover:text-slate-600'
                        }`}
                      >
                        {tab}
                      </button>
                    ),
                  )}
                </div>

                <div className="p-8 md:p-12 max-w-4xl mx-auto prose prose-slate prose-headings:font-black prose-h2:text-3xl prose-h3:text-xl prose-p:text-slate-600 prose-li:text-slate-600">
                  {/* Table of Contents */}
                  {report.tableOfContents &&
                    report.tableOfContents.length > 0 && (
                      <section className="mb-12">
                        <h2 className="text-2xl font-black mb-6">
                          Table of Contents
                        </h2>
                        <ul className="space-y-2 list-none p-0">
                          {report.tableOfContents.map(
                            (item, i) => (
                              <li
                                key={i}
                                className="flex items-center gap-3 text-indigo-600 font-medium"
                              >
                                <div className="w-1 h-1 bg-indigo-600 rounded-full" />
                                {item}
                              </li>
                            ),
                          )}
                        </ul>
                      </section>
                    )}

                  {/* Executive Summary */}
                  <section className="mb-12">
                    <h2 className="text-3xl font-black mb-4">
                      Executive Summary
                    </h2>
                    <div className="text-lg leading-relaxed text-slate-700">
                      <Markdown>{report.executiveSummary}</Markdown>
                    </div>
                  </section>

                  {/* Methodology */}
                  {report.methodology && (
                    <section className="mb-12">
                      <h2 className="text-3xl font-black mb-4">
                        Research Methodology
                      </h2>
                      <div className="bg-slate-50 p-6 rounded-xl border border-slate-100 italic text-slate-600">
                        <Markdown>{report.methodology}</Markdown>
                      </div>
                    </section>
                  )}

                  {/* Sections */}
                  {report.sections?.map((section, i) => (
                    <section key={i} className="mb-12">
                      <h2 className="text-3xl font-black mb-4">
                        {section.heading}
                      </h2>
                      <div className="space-y-4">
                        <Markdown>{section.content}</Markdown>
                      </div>
                    </section>
                  ))}

                  {/* Findings */}
                  {report.findings && report.findings.length > 0 && (
                    <section className="mb-12 pt-12 border-t border-slate-200">
                      <h2 className="text-2xl font-black mb-6">
                        Key Findings
                      </h2>
                      <ul className="space-y-3">
                        {report.findings.map((f, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-3"
                          >
                            <CheckCircle2
                              size={18}
                              className="text-emerald-500 mt-0.5 shrink-0"
                            />
                            <span>{f}</span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  {/* Sources */}
                  {report.sources && report.sources.length > 0 && (
                    <section className="pt-12 border-t border-slate-200">
                      <h2 className="text-2xl font-black mb-6">
                        Sources & References
                      </h2>
                      <div className="grid gap-4">
                        {report.sources.map((source, i) => (
                          <div
                            key={i}
                            className="p-4 bg-slate-50 rounded-lg border border-slate-100 flex items-start justify-between group"
                          >
                            <div>
                              <h4 className="font-bold text-slate-900 mb-1">
                                {source.title}
                              </h4>
                              <p className="text-xs text-slate-500">
                                {source.relevance}
                              </p>
                            </div>
                            {source.url && (
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity"
                              >
                                <ExternalLink size={18} />
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* ---- Footer ---- */}
      <footer className="py-12 text-center text-white/30 text-xs tracking-widest uppercase font-bold">
        &copy; {new Date().getFullYear()} Multi-Agent Research Assistant
      </footer>
    </div>
  );
}
