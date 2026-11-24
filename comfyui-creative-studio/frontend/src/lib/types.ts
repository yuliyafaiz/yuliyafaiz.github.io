// Types mirroring backend/app/schemas.py serializers.

export interface Campaign {
  id: number;
  project_id: number;
  name: string;
  description: string;
  status: string;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  client: string;
  status: "active" | "archived";
  template_key: string | null;
  meta: Record<string, unknown>;
  cover_reference_id: number | null;
  cover_url: string | null;
  campaigns: Campaign[];
  created_at: string;
  updated_at: string;
  counts: Partial<Record<"references" | "profiles" | "workflows" | "jobs" | "outputs" | "selected", number>>;
}

export interface ProjectDetail extends Project {
  references: Reference[];
  profiles: Profile[];
  collections: { id: number; name: string; count: number }[];
  workflows: Workflow[];
}

export interface ProjectTemplate {
  key: string;
  label: string;
  description: string;
  campaigns: string[];
  collections: string[];
}

export interface Reference {
  id: number;
  title: string;
  original_name: string;
  mime: string;
  width: number;
  height: number;
  has_alpha: boolean;
  sha256: string;
  palette: string[];
  category: string;
  tags: string[];
  description: string;
  favorite: boolean;
  created_at: string;
  file_url: string;
  thumb_url: string;
  project_ids: number[];
}

export interface Collection {
  id: number;
  name: string;
  description: string;
  project_id: number | null;
  reference_ids: number[];
  count: number;
  cover_urls: string[];
}

export interface ProfileImage {
  id: number;
  role: string;
  position: number;
  reference: Reference;
}

export interface Profile {
  id: number;
  kind: "character" | "product";
  name: string;
  description: string;
  category: string;
  attributes: Record<string, string>;
  preserve_details: string[];
  generation_settings: Record<string, unknown>;
  notes: string;
  images: ProfileImage[];
  workflow_ids: number[];
  project_ids: number[];
  prompt_fragment?: { positive: string; negative: string };
  created_at: string;
  updated_at: string;
}

export type ParamType = "text" | "int" | "float" | "seed" | "choice" | "image" | "bool";

export interface WorkflowParam {
  key: string;
  node_id: string;
  input: string;
  class_type?: string;
  label: string;
  type: ParamType;
  group: string;
  default: unknown;
  choices?: unknown[];
  min?: number;
  max?: number;
  step?: number;
  role?: "positive" | "negative" | null;
}

export interface ModelRef {
  node_id: string;
  class_type: string;
  input: string;
  name: string;
  kind: string;
}

export interface Workflow {
  id: number;
  name: string;
  description: string;
  category: string;
  project_id: number | null;
  is_template: boolean;
  source_format: "api" | "ui";
  executable: boolean;
  api_source: "imported" | "converted" | null;
  conversion_warnings: string[];
  parameters: WorkflowParam[];
  node_types: string[];
  models: ModelRef[];
  node_count: number;
  created_at: string;
  updated_at: string;
  original_json?: unknown;
  api_json?: Record<string, { class_type: string; inputs: Record<string, unknown>; _meta?: { title?: string } }> | null;
  methods?: string[];
}

export interface StructureIssue {
  node_id: string;
  class_type: string;
  kind: string;
  message: string;
  severity: "error" | "warning";
}

export interface DependencyReport {
  checked: boolean;
  missing_nodes: string[];
  missing_models: { node_id: string; class_type: string; input: string; value: string }[];
  invalid_values: { node_id: string; class_type: string; input: string; value: unknown }[];
  structure_issues: StructureIssue[];
  node_types: string[];
  models: ModelRef[];
  methods: string[];
  ready: boolean;
}

export interface ConsistencyConfig {
  id: number;
  name: string;
  description: string;
  workflow_id: number;
  workflow_name: string | null;
  profile_id: number | null;
  profile_name: string | null;
  project_id: number | null;
  methods: string[];
  image_bindings: Record<string, number>;
  values: Record<string, unknown>;
  use_profile_prompt: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConsistencyPlan {
  workflow_id: number;
  methods: { key: string; info: string }[];
  image_parameters: WorkflowParam[];
  conditioning_parameters: WorkflowParam[];
  suggested_bindings: Record<string, number>;
  profile_loader_nodes: string[];
}

export type JobStatus = "pending" | "submitted" | "running" | "completed" | "failed" | "interrupted" | "cancelled" | "lost";

export interface OutputSummary {
  id: number;
  job_id: number;
  project_id: number | null;
  width: number;
  height: number;
  node_id: string;
  comfy_filename: string;
  favorite: boolean;
  selected: boolean;
  rating: number;
  note: string;
  created_at: string;
  file_url: string;
  thumb_url: string;
  summary?: Record<string, unknown>;
  meta?: OutputMeta;
}

export interface GenerationMeta {
  prompt: string | null;
  negative_prompt: string | null;
  seed: number | null;
  sampler: string | null;
  scheduler: string | null;
  steps: number | null;
  cfg: number | null;
  denoise: number | null;
  dimensions: { width: number; height: number } | null;
  models: (ModelRef & { sha256: string | null })[];
  methods: string[];
  variant?: { label: string; text: string; index: number; seed: number };
  runtime_values_from?: string;
  node_types: string[];
}

export interface OutputMeta {
  schema: string;
  job: { id: number; batch_id: string; variation_index: number; project_id: number | null; campaign_id: number | null };
  workflow: { id: number; name: string; category: string } | null;
  generation: GenerationMeta;
  parameter_values: Record<string, unknown>;
  reference_images: { parameter: string; reference_id: number; title: string; sha256: string; category: string }[];
  comfy: { prompt_id: string; server_url: string; execution_seconds: number | null };
  node_metadata: Record<string, unknown> | null;
  submitted_at: string | null;
  completed_at: string;
  output: { filename: string; sha256: string; width: number; height: number };
}

export interface Job {
  id: number;
  project_id: number | null;
  campaign_id: number | null;
  workflow_id: number | null;
  consistency_config_id: number | null;
  batch_id: string;
  variation_index: number;
  name: string;
  status: JobStatus;
  comfy_prompt_id: string | null;
  server_url: string;
  parameter_values: Record<string, unknown>;
  image_bindings: Record<string, number>;
  progress: { value?: number; max?: number; node?: string; queue?: string; queue_position?: number; connection?: string };
  error: { type: string; message: string; node_id?: string; node_type?: string; node_errors?: Record<string, unknown> } | null;
  execution_seconds: number | null;
  created_at: string;
  submitted_at: string | null;
  finished_at: string | null;
  outputs: OutputSummary[];
  submitted_prompt?: unknown;
}

export interface ComfyStatus {
  url: string;
  reachable: boolean;
  websocket_connected: boolean;
  version?: string;
  python?: string;
  pytorch?: string;
  os?: string;
  ram_total?: number;
  ram_free?: number;
  devices?: { name: string; type: string; vram_total?: number; vram_free?: number }[];
  queue_running?: number;
  queue_pending?: number;
  error?: string;
}

export interface Activity {
  id: number;
  project_id: number | null;
  kind: string;
  message: string;
  created_at: string;
}

export interface Dashboard {
  stats: Record<string, number>;
  recent_projects: Project[];
  active_jobs: Job[];
  recent_outputs: OutputSummary[];
  favorite_references: Reference[];
  workflow_shortcuts: Workflow[];
  activity: Activity[];
}

export interface CustomNodeInfo {
  name: string;
  display_name: string;
  category: string;
  description: string;
  inputs: { name: string; type: string; tooltip?: string | null; options?: string[] }[];
  optional_inputs: { name: string; type: string; tooltip?: string | null }[];
  outputs: { name: string; type: string }[];
  output_node: boolean;
  installed: boolean | null;
}

export interface CompareResult {
  kind: "reference" | "output";
  id: number;
  title?: string;
  structural_similarity: number;
  color_histogram_correlation: number;
  perceptual_hash_distance: number;
  perceptual_hash_similarity: number;
}
