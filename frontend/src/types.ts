/* ------------------------------------------------------------------ */
/*  Types for Multi-Agent Research Assistant Frontend                  */
/*  Aligned with FastAPI backend models                                */
/* ------------------------------------------------------------------ */

export interface ResearchOptions {
  query: string;
  focusAreas: string;
  sources: string[];
  format: string;
  citationStyle: string;
  maxSources: number;
  mode: string;
}

export interface LogEntry {
  timestamp: string;
  agent: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

export enum AgentStatus {
  PENDING = 'Pending',
  IN_PROGRESS = 'In Progress',
  COMPLETED = 'Completed',
  FAILED = 'Failed',
}

export interface AgentState {
  id: string;
  name: string;
  description: string;
  status: AgentStatus;
  icon: string;
}

export interface ResearchHistory {
  id: string;
  query: string;
  timestamp: string;
  report: ResearchReport | null;
  options: ResearchOptions;
  status: string;
}

/* --- Report schema (from backend) --- */

export interface ReportSource {
  title: string;
  url: string;
  relevance: string;
}

export interface ReportSection {
  heading: string;
  content: string;
}

export interface ResearchReport {
  title: string;
  tableOfContents?: string[];
  executiveSummary: string;
  methodology?: string;
  sections: ReportSection[];
  findings?: string[];
  sources?: ReportSource[];
  quality_score?: number;
}

/* --- WebSocket message types --- */

export interface WSAgentUpdate {
  type: 'agent_status_update';
  agent: string;
  status: string;
  progress: number;
  timestamp: string;
  output?: string;
  error?: string;
  data?: Record<string, unknown>;
}

export interface WSPhaseUpdate {
  type: 'phase_update';
  phase: string;
  status: string;
  message?: string;
  timestamp: string;
}

export interface WSResearchComplete {
  type: 'research_complete';
  session_id: string;
  status: string;
  timestamp: string;
  results: {
    report_title: string;
    sources_count: Record<string, number>;
    findings_count: number;
    confidence_level: string;
    quality_score: number;
  };
}

export interface WSResearchError {
  type: 'research_error';
  session_id: string;
  error: string;
  phase?: string;
  timestamp: string;
}

export type WSMessage =
  | WSAgentUpdate
  | WSPhaseUpdate
  | WSResearchComplete
  | WSResearchError
  | { type: 'connection_established'; session_id: string; timestamp: string };
