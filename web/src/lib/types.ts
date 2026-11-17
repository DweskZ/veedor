/** Shapes of the Veedor API, mirroring src/veedor/schemas (FastAPI). Keys are exact. */

export type PartyKind = "natural_person" | "company" | "public_entity" | "other" | "unknown";

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Party {
  ruc: string | null;
  name: string | null;
  kind: PartyKind;
}

export interface ScoreBucket {
  lower: number;
  /** Exclusive upper bound; the last bucket includes 100. */
  upper: number;
  count: number;
}

export interface SignalCount {
  code: string;
  label_es: string | null;
  count: number;
}

export interface Stats {
  processes_total: number | null;
  processes_by_method_group: Record<string, number>;
  processes_scored: number | null;
  processes_with_signals: number | null;
  mean_risk_score: number | null;
  score_distribution: ScoreBucket[];
  signal_counts: SignalCount[];
  first_year: number | null;
  last_year: number | null;
  last_data_date: string | null;
  available_tables: Record<string, boolean>;
}

export interface ProcessSummary {
  ocid: string;
  risk_score: number;
  n_signals: number;
  signal_codes: string[];
  anomaly_score: number | null;
  award_total: number | null;
  year: number | null;
  buyer_ruc: string | null;
  buyer_name: string | null;
  method: string | null;
  winner_ruc: string | null;
  winner_name: string | null;
  winner_kind: PartyKind | null;
}

export type SignalKind = "risk" | "context";

export interface FiredSignal {
  code: string;
  /** Absent on older API versions: treated as "risk". */
  kind?: SignalKind;
  label_es: string | null;
  value: number | null;
  threshold: number | null;
  evidence: Record<string, unknown>;
}

export interface ProcessFacts {
  process_code: string | null;
  release_date: string | null;
  year: number | null;
  buyer_ruc: string | null;
  buyer_name: string | null;
  buyer_region: string | null;
  buyer_locality: string | null;
  method: string | null;
  method_group: string | null;
  category: string | null;
  status: string | null;
  description: string | null;
  /** True when the description was omitted because it contained personal data. */
  description_withheld?: boolean;
  budget: number | null;
  tender_start: string | null;
  tender_end: string | null;
  n_tenderers: number | null;
  n_bids: number | null;
  n_awards: number | null;
  award_total: number | null;
  first_award_date: string | null;
  date_signed: string | null;
  main_cpc: string | null;
  main_cpc_description: string | null;
}

export interface Score {
  risk_score: number;
  n_signals: number;
  anomaly_score: number | null;
}

export interface Award {
  award_id: string | null;
  award_date: string | null;
  supplier_ruc: string | null;
  supplier_name: string | null;
  amount: number | null;
}

export interface SupplierProfile {
  ruc: string | null;
  name: string | null;
  kind: PartyKind;
  n_processes: number | null;
  n_wins: number | null;
  total_awarded: number | null;
  first_award_date: string | null;
  last_award_date: string | null;
  n_buyers: number | null;
  top_buyer_ruc: string | null;
  top_buyer_share: number | null;
  single_bidder_wins: number | null;
  mean_risk_score: number | null;
}

export interface ProcessDetail {
  ocid: string;
  facts: ProcessFacts | null;
  score: Score | null;
  signals: FiredSignal[];
  winner: SupplierProfile | null;
  tenderers: Party[];
  awards: Award[];
  notice_es: string;
}

export interface SriFacts {
  ruc: string | null;
  legal_name: string | null;
  status: string | null;
  taxpayer_type: string | null;
  activity_start_date: string | null;
  suspension_date: string | null;
  restart_date: string | null;
  ciiu_code: string | null;
  activity: string | null;
  province: string | null;
}

export interface SuperciasFacts {
  ruc: string | null;
  expediente: string | null;
  legal_name: string | null;
  company_type: string | null;
  province: string | null;
}

export interface FinancialYear {
  year: number;
  revenue: number | null;
  assets: number | null;
  equity: number | null;
  employees: number | null;
}

export interface RegistryFacts {
  sri: SriFacts | null;
  ghost_company_listed: boolean | null;
  supercias: SuperciasFacts | null;
  financials: FinancialYear[];
}

export interface SupplierDetail {
  profile: SupplierProfile;
  registry: RegistryFacts;
  recent_processes: ProcessSummary[];
}

export interface BuyerSupplier {
  ruc: string | null;
  name: string | null;
  kind: PartyKind;
  n_awards: number;
  total_awarded: number | null;
  share_of_awarded: number | null;
  mean_risk_score: number | null;
}

export interface BuyerDetail {
  ruc: string;
  name: string | null;
  n_processes: number;
  n_flagged: number;
  total_awarded: number | null;
  mean_risk_score: number | null;
  first_year: number | null;
  last_year: number | null;
  top_suppliers: BuyerSupplier[];
  signal_mix: SignalCount[];
}

export interface DossierSection {
  title: string;
  body: string;
}

export interface DossierSource {
  dataset: string;
  licence: string | null;
  retrieved_at: string | null;
  record_id: string | null;
}

export interface GroundingReport {
  passed: boolean;
  n_checked: number;
  supported: unknown[];
  unsupported: unknown[];
  forbidden: unknown[];
}

export interface Dossier {
  ocid: string;
  generated_at: string | null;
  mode: "template" | "template_minimal" | "llm" | null;
  summary_es: string | null;
  sections: DossierSection[];
  sources: DossierSource[];
  grounding_report: GroundingReport | null;
  fallback_reason?: string | null;
  llm_attempts?: number;
}

export interface SignalDef {
  code: string;
  kind?: SignalKind;
  label_es: string;
  description_es: string;
  scope: string;
  fields: string[];
  threshold_rule_es: string;
  statistical: boolean;
  needs_registry: boolean;
}

export type ReviewStatus = "pending" | "confirmed_signal" | "dismissed";

export interface Review {
  id: number;
  ocid: string;
  status: ReviewStatus;
  note: string | null;
  reviewer: string | null;
  created_at: string;
}

export interface ApiMeta {
  reviews_enabled: boolean | null;
  /** The question box is shown only when this is exactly true (absent or unknown counts as off). */
  ask_enabled: boolean | null;
  /** Source quotes are shown only when this is exactly true (absent or unknown counts as off). */
  quotes_enabled: boolean | null;
  /** How questions are answered: "retrieval" (search inside Veedor, no model) or "model" (external language model). Anything else is unknown. */
  ask_mode: "retrieval" | "model" | null;
}

export interface ProcessQuery {
  year?: string;
  method?: string;
  signal?: string;
  min_score?: string;
  min_amount?: string;
  max_amount?: string;
  q?: string;
  buyer_ruc?: string;
  region?: string;
  page?: string;
  page_size?: string;
  sort?: string;
}

/** One row of `GET /processes/{ocid}/similar`. `similarity` is cosine similarity in [-1, 1]. */
export interface SimilarProcess {
  ocid: string;
  similarity: number;
  year: number | null;
  buyer_ruc: string | null;
  buyer_name: string | null;
  method: string | null;
  award_total: number | null;
  main_cpc: string | null;
}

export interface SimilarProcesses {
  ocid: string;
  k: number;
  same_buyer: boolean;
  items: SimilarProcess[];
  notice_es: string;
}

/**
 * Stored multi-agent investigation (`GET /processes/{ocid}/investigation`). The API schema leaves the nested
 * records open, so every field is optional here and `normalizeInvestigation` coerces what it receives.
 */
export interface InvestigationSpecialist {
  specialist: string;
  dispatch_reason: string | null;
  decided_by: string | null;
  action_plan_by: string | null;
  n_tool_calls: number | null;
  outcomes: Record<string, number>;
  facts_added: string[];
}

export interface InvestigationLookup {
  specialist: string;
  tool: string;
  target: string | null;
  started_at: string | null;
  duration_ms: number | null;
  outcome: string;
  attempts: number | null;
  reason: string | null;
}

export interface InvestigationModelUsage {
  model: string | null;
  calls: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  invalid_choices: number | null;
}

export interface Investigation {
  ocid: string;
  started_at: string | null;
  finished_at: string | null;
  specialists: InvestigationSpecialist[];
  lookups: InvestigationLookup[];
  facts_added: string[];
  model_usage: InvestigationModelUsage | null;
}

/** One row of `GET /stats/by-region`: province of the BUYING entity. */
export interface RegionRow {
  region: string;
  region_label: string;
  competitive_processes: number;
  with_signal: number;
  pct_with_signal: number | null;
  single_bidder: number;
  pct_single_bidder: number | null;
  mean_score: number | null;
  processes_total: number;
  awarded_total: number | null;
  small_sample?: boolean;
}

export interface RegionStats {
  items: RegionRow[];
  national: Partial<RegionRow> | null;
  basis: string | null;
  notes: string[];
  data_built_at: string | null;
}

/** Share of the awarded amount by method group. */
export interface MethodMix {
  competitive: number | null;
  direct: number | null;
  catalogue: number | null;
  other: number | null;
}

/** One row of `GET /stats/by-year`, normalised. Shares are fractions in [0, 1]. */
export interface YearRow {
  year: number;
  processes_total: number | null;
  competitive_processes: number | null;
  pct_single_bidder: number | null;
  pct_with_signal: number | null;
  single_bidder_base: number | null;
  awarded_total: number | null;
  mix: MethodMix;
  partial_year: boolean;
}

export interface YearStats {
  items: YearRow[];
  notes: string[];
  data_built_at: string | null;
}

/** Entity suggestion from `GET /buyers/search`. */
export interface BuyerHit {
  ruc: string;
  name: string;
  region_label: string | null;
  processes_total: number | null;
}

/** A position among comparable processes: this process's value and its percentile. */
export interface Position {
  value: number | null;
  percentile: number | null;
}

/** `GET /processes/{ocid}/context`, normalised. Every part may be absent. */
export interface ProcessContext {
  method: string | null;
  year: number | null;
  comparable: number | null;
  tenderers: { counts: number[]; position: Position } | null;
  ratio: { median: number; q1: number | null; q3: number | null; position: Position } | null;
  window: { median: number; q1: number | null; q3: number | null; position: Position } | null;
}

/** The threshold that applies to one process (`GET /processes/{ocid}/threshold`), normalised. */
export interface ProcessThreshold {
  ocid: string;
  year: number | null;
  budget: number | null;
  applicable: boolean;
  /** Why no threshold applies (plain Spanish, from the API). */
  reason: string | null;
  threshold: {
    code: string;
    category: string | null;
    usd: number;
    procedure_below: string | null;
    procedure_above: string | null;
    source_url: string | null;
    verification: string | null;
  } | null;
  /** Percentage points of the threshold by which the budget sits below it (positive = below). */
  distance_pct: number | null;
  just_below: boolean;
  /** Width of the "just below" band, in % of the threshold. */
  band_pct: number | null;
  notes: string[];
}

/** One year and category row of `GET /stats/thresholds`. */
export interface ThresholdRow {
  year: number;
  category: string;
  code: string;
  procedure_below: string | null;
  procedure_above: string | null;
  usd: number;
  source_url: string | null;
  n_band_below: number | null;
  n_band_above: number | null;
  bunching_status: string | null;
  caveats: string[];
}

export interface ThresholdStats {
  items: ThresholdRow[];
  band_pct: number | null;
  /** year -> reason the year is not analysed. */
  excluded_years: Record<string, string>;
  notes: string[];
  data_built_at: string | null;
}
