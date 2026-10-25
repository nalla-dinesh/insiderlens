/** Shared API shapes — mirrored from apps/api/app/schemas/ (single source = backend). */

export interface HealthResponse {
  status: 'ok';
  version: string;
  environment: string;
}

export interface ApiErrorShape {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export function isApiErrorShape(v: unknown): v is ApiErrorShape {
  if (typeof v !== 'object' || v === null) return false;
  const err = (v as ApiErrorShape).error;
  return (
    typeof err === 'object' &&
    err !== null &&
    typeof err.code === 'string' &&
    typeof err.message === 'string'
  );
}

// ------------------------------------------------------------------ alerts (Phase 04)
export type Band = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'IN_REVIEW' | 'RESOLVED' | 'DISMISSED';

export const BANDS: Band[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
export const STATUSES: AlertStatus[] = ['OPEN', 'ACKNOWLEDGED', 'IN_REVIEW', 'RESOLVED', 'DISMISSED'];
export const RULE_IDS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'E1', 'E2', 'E3', 'E4', 'E5', 'F1', 'F2', 'F3'] as const;
export type RuleId = (typeof RULE_IDS)[number];

export interface ReasonItem {
  rule: string;
  pts: number;
  text: string;
}

export interface AlertSummary {
  alert_id: number;
  run_id: number;
  band: Band;
  score: number;
  rule_set: string[];
  entity_ids: number[];
  entity_type: 'ACCOUNT' | 'EMPLOYEE' | 'CUSTOMER' | 'MIXED';
  status: AlertStatus;
  created_at: string;
  top_reasons: string[];
  case_id: number | null; // Phase 06: owning case (null = unlinked)
  max_amount: number | null;
  entity_counts: { accounts?: number; employees?: number };
}

export interface AlertPage {
  items: AlertSummary[];
  total: number;
  limit: number;
  offset: number;
  band_counts: Record<Band, number>;
}

export interface AlertDetail extends AlertSummary {
  reasons: ReasonItem[];
  evidence: EvidencePayload;
}

// ------------------------------------------------------------------ evidence
export interface GraphNodeData {
  id: number;
  label: string;
  branch?: string;
  type?: string;
  status?: string;
  cust_id?: number;
}

export interface GraphEdgeData {
  id: number;
  source: number;
  target: number;
  amount: number;
  ts: string;
  channel: string;
}

export interface EvidenceGraph {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  truncated: boolean;
}

export interface TimelineEvent {
  ts: string;
  kind: 'EMPLOYEE' | 'TXN';
  label: string;
  ref_id: number;
}

export interface ThresholdGate {
  observed: string | number;
  limit: string | number;
  source: string;
}

export interface EvidencePayload {
  graph: EvidenceGraph;
  timeline: TimelineEvent[];
  thresholds: Record<string, ThresholdGate>;
  records: { txn_ids: number[]; log_ids: number[] };
  overflow_rules?: string[];
  overflow_note?: string;
}

export interface TimelineResponse {
  alert_id: number;
  timeline: TimelineEvent[];
  statuses: string[];
}

// ------------------------------------------------------------------ runs / analysis
export interface RunSummary {
  run_id: number;
  started_at: string;
  finished_at: string | null;
  txn_count: number | null;
  alert_count: number | null;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED';
  config: Record<string, unknown>;
}

export interface RunList {
  items: RunSummary[];
  total: number;
}

export interface AnalysisReport {
  run_id: number;
  status: string;
  alerts_by_band: Record<Band, number>;
  duration_ms: number;
  per_rule_hits: Record<string, number>;
  signals_dropped: number;
  errors: string[];
}

// ------------------------------------------------------------------ explorer (Phase 02)
export interface EgoNode {
  id: number;
  label: string;           // e.g. "200071 · CURRENT"
  group: string;           // account type
  risk_hint: string | null;
}

export interface EgoEdge {
  txn_id: number;
  source: number;
  target: number;
  amount: number;
  ts: string;
  channel?: string;
  purpose?: string | null;
}

export interface EgoGraphResponse {
  center: number;
  depth: number;
  nodes: EgoNode[];
  edges: EgoEdge[];
  truncated: boolean;
}

// ------------------------------------------------------------------ cases (Phase 06)
export type CaseStatus = 'OPEN' | 'IN_PROGRESS' | 'ESCALATED' | 'CLOSED_TRUE' | 'CLOSED_FALSE';
export const CASE_STATUSES: CaseStatus[] = ['OPEN', 'IN_PROGRESS', 'ESCALATED', 'CLOSED_TRUE', 'CLOSED_FALSE'];

/** Mirrors app/services/cases.py TRANSITIONS — keep in sync (noted in PHASE_06_NOTES). */
export const CASE_TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  OPEN: ['IN_PROGRESS'],
  IN_PROGRESS: ['ESCALATED', 'CLOSED_TRUE', 'CLOSED_FALSE'],
  ESCALATED: ['CLOSED_TRUE', 'CLOSED_FALSE'],
  CLOSED_TRUE: [],
  CLOSED_FALSE: [],
};

export interface CaseBoardItem {
  case_id: number;
  title: string;
  assignee: string | null;
  status: CaseStatus;
  created_at: string;
  closed_at: string | null;
  alert_count: number;
  band: Band | null;
}

export interface CaseBoard {
  statuses: CaseStatus[];
  groups: Record<CaseStatus, CaseBoardItem[]>;
}

export interface CaseNoteOut {
  note_id: number;
  author: string;
  body: string;
  ts: string;
}

export interface CaseDetail {
  case_id: number;
  title: string;
  assignee: string | null;
  status: CaseStatus;
  created_at: string;
  closed_at: string | null;
  band: Band | null;
  alert_ids: number[];
  alerts: AlertDetail[];
  notes: CaseNoteOut[];
  recommendations: string[];
}

export interface AnalystOut {
  emp_id: number;
  name: string;
  role: string;
  branch: string;
}

// ---------------- Phase 07: evaluation ----------------
export interface ScenarioRow {
  scenario_id: string;
  is_suspicious: boolean;
  hit: boolean;
  tag: 'TP' | 'FP' | 'FN' | 'TN';
  entity_ids: number[];
  matching_alert_ids: number[];
  note: string;
}

export interface MetricCounts { tp: number; fp: number; fn: number; tn: number; }

export interface EvalTargets {
  recall_goal: number; precision_goal: number; fpr_goal: number;
  recall_passed: boolean; precision_passed: boolean; fpr_passed: boolean; passed: boolean;
}

export interface EvaluationReport {
  run_id: number;
  alert_count: number;
  counts: MetricCounts;
  precision: number; recall: number; f1: number; fpr: number;
  targets: EvalTargets;
  alerts_on_tagged_suspicious: number;
  alerts_on_tagged_legit: number;
  alerts_unverified: number;
  scenario_rows: ScenarioRow[];
}

export interface CompareReport {
  run_a: EvaluationReport;
  run_b: EvaluationReport;
  deltas: Record<string, number>;
}
