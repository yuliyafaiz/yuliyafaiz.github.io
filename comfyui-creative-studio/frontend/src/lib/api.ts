import type {
  Collection,
  ComfyStatus,
  CompareResult,
  ConsistencyConfig,
  ConsistencyPlan,
  CustomNodeInfo,
  Dashboard,
  DependencyReport,
  Job,
  OutputSummary,
  Profile,
  Project,
  ProjectDetail,
  ProjectTemplate,
  Reference,
  Workflow,
  Activity,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? JSON.stringify(x)).join("; ");
  }
  return fallback;
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, "Cannot reach the Creative Studio backend. Is it running?");
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : await res.blob();
  if (!res.ok) throw new ApiError(res.status, detailMessage(data, `${method} ${url} failed (${res.status})`), data);
  return data as T;
}

const get = <T,>(u: string) => request<T>("GET", u);
const post = <T,>(u: string, b?: unknown) => request<T>("POST", u, b);
const patch = <T,>(u: string, b: unknown) => request<T>("PATCH", u, b);
const put = <T,>(u: string, b: unknown) => request<T>("PUT", u, b);
const del = (u: string) => request<void>("DELETE", u);

const qs = (params: Record<string, unknown>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  dashboard: () => get<Dashboard>("/api/dashboard"),
  // projects
  templates: () => get<ProjectTemplate[]>("/api/project-templates"),
  projects: (status = "active") => get<Project[]>(`/api/projects${qs({ status })}`),
  project: (id: number) => get<ProjectDetail>(`/api/projects/${id}`),
  createProject: (b: { name: string; description?: string; client?: string; template_key?: string }) =>
    post<Project>("/api/projects", b),
  updateProject: (id: number, b: Partial<Project>) => patch<Project>(`/api/projects/${id}`, b),
  archiveProject: (id: number) => post<Project>(`/api/projects/${id}/archive`),
  restoreProject: (id: number) => post<Project>(`/api/projects/${id}/restore`),
  deleteProject: (id: number) => del(`/api/projects/${id}`),
  addCampaign: (id: number, name: string) => post(`/api/projects/${id}/campaigns`, { name }),
  attachReferences: (id: number, ids: number[]) => post(`/api/projects/${id}/references`, { ids }),
  detachReference: (id: number, rid: number) => del(`/api/projects/${id}/references/${rid}`),
  attachProfiles: (id: number, ids: number[]) => post(`/api/projects/${id}/profiles`, { ids }),
  projectActivity: (id: number) => get<Activity[]>(`/api/projects/${id}/activity`),
  // references
  categories: () => get<string[]>("/api/reference-categories"),
  references: (f: { q?: string; category?: string; tag?: string; project_id?: number; collection_id?: number; favorite?: boolean } = {}) =>
    get<Reference[]>(`/api/references${qs(f)}`),
  reference: (id: number) => get<Reference>(`/api/references/${id}`),
  tags: () => get<{ tag: string; count: number }[]>("/api/references/tags"),
  uploadReferences: (files: File[], meta: { category: string; tags?: string; project_id?: number; collection_id?: number; description?: string }) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("category", meta.category);
    if (meta.tags) fd.append("tags", meta.tags);
    if (meta.description) fd.append("description", meta.description);
    if (meta.project_id) fd.append("project_id", String(meta.project_id));
    if (meta.collection_id) fd.append("collection_id", String(meta.collection_id));
    return post<Reference[]>("/api/references", fd);
  },
  updateReference: (id: number, b: Partial<Reference>) => patch<Reference>(`/api/references/${id}`, b),
  deleteReference: (id: number) => del(`/api/references/${id}`),
  collections: (project_id?: number) => get<Collection[]>(`/api/collections${qs({ project_id })}`),
  createCollection: (b: { name: string; description?: string; project_id?: number | null; reference_ids?: number[] }) =>
    post<Collection>("/api/collections", b),
  addToCollection: (id: number, ids: number[]) => post<Collection>(`/api/collections/${id}/items`, { ids }),
  removeFromCollection: (id: number, rid: number) => del(`/api/collections/${id}/items/${rid}`),
  deleteCollection: (id: number) => del(`/api/collections/${id}`),
  // profiles
  profiles: (kind?: string) => get<Profile[]>(`/api/profiles${qs({ kind })}`),
  profile: (id: number) => get<Profile>(`/api/profiles/${id}`),
  profileFields: () => get<{ fields: Record<string, string[]>; image_roles: string[] }>("/api/profiles/attribute-fields"),
  createProfile: (b: Partial<Profile> & { kind: string; name: string; project_ids?: number[] }) => post<Profile>("/api/profiles", b),
  updateProfile: (id: number, b: Partial<Profile> & { project_ids?: number[]; workflow_ids?: number[] }) =>
    patch<Profile>(`/api/profiles/${id}`, b),
  deleteProfile: (id: number) => del(`/api/profiles/${id}`),
  addProfileImage: (id: number, reference_id: number, role: string) =>
    post<Profile>(`/api/profiles/${id}/images`, { reference_id, role }),
  removeProfileImage: (id: number, imageId: number) => del(`/api/profiles/${id}/images/${imageId}`),
  // workflows
  workflowCategories: () => get<string[]>("/api/workflow-categories"),
  workflows: (f: { project_id?: number; category?: string } = {}) => get<Workflow[]>(`/api/workflows${qs(f)}`),
  workflow: (id: number) => get<Workflow>(`/api/workflows/${id}`),
  importWorkflow: (b: { name: string; data: unknown; category: string; description?: string; project_id?: number | null; is_template?: boolean }) =>
    post<Workflow>("/api/workflows", b),
  updateWorkflow: (id: number, b: Partial<Workflow>) => patch<Workflow>(`/api/workflows/${id}`, b),
  deleteWorkflow: (id: number) => del(`/api/workflows/${id}`),
  convertWorkflow: (id: number) => post<Workflow>(`/api/workflows/${id}/convert`),
  attachApiJson: (id: number, data: unknown) => post<Workflow>(`/api/workflows/${id}/api-json`, { data }),
  rediscover: (id: number) => post<Workflow>(`/api/workflows/${id}/rediscover`),
  dependencies: (id: number) => get<DependencyReport>(`/api/workflows/${id}/dependencies`),
  workflowInputs: (id: number) => get<{ key: string; node_id: string; input: string; class_type: string; value: unknown }[]>(`/api/workflows/${id}/inputs`),
  duplicateWorkflow: (id: number, project_id?: number) => post<Workflow>(`/api/workflows/${id}/duplicate${qs({ project_id })}`),
  // consistency
  consistencyMethods: () => get<Record<string, string>>("/api/consistency/methods"),
  consistencyPlan: (workflowId: number, profileId?: number | null) =>
    get<ConsistencyPlan>(`/api/consistency/plan/${workflowId}${qs({ profile_id: profileId })}`),
  consistencyConfigs: (f: { project_id?: number } = {}) => get<ConsistencyConfig[]>(`/api/consistency${qs(f)}`),
  consistencyConfig: (id: number) => get<ConsistencyConfig>(`/api/consistency/${id}`),
  createConsistency: (b: Partial<ConsistencyConfig>) => post<ConsistencyConfig>("/api/consistency", b),
  updateConsistency: (id: number, b: Partial<ConsistencyConfig>) => patch<ConsistencyConfig>(`/api/consistency/${id}`, b),
  deleteConsistency: (id: number) => del(`/api/consistency/${id}`),
  // production
  generate: (b: {
    workflow_id?: number; consistency_config_id?: number; project_id?: number | null; campaign_id?: number | null;
    name?: string; values?: Record<string, unknown>; image_bindings?: Record<string, number>; variations?: number;
    seed_mode?: string; base_seed?: number | null;
  }) => post<{ batch_id: string; jobs: Job[] }>("/api/generate", b),
  jobs: (f: { project_id?: number; status?: string; batch_id?: string; limit?: number } = {}) => get<Job[]>(`/api/jobs${qs(f)}`),
  job: (id: number) => get<Job>(`/api/jobs/${id}`),
  cancelJob: (id: number) => post<Job>(`/api/jobs/${id}/cancel`),
  reproduceJob: (id: number) => post<Job>(`/api/jobs/${id}/reproduce`),
  outputs: (f: { project_id?: number; job_id?: number; batch_id?: string; favorite?: boolean; selected?: boolean } = {}) =>
    get<OutputSummary[]>(`/api/outputs${qs(f)}`),
  output: (id: number) => get<OutputSummary>(`/api/outputs/${id}`),
  updateOutput: (id: number, b: Partial<Pick<OutputSummary, "favorite" | "selected" | "rating" | "note">>) =>
    patch<OutputSummary>(`/api/outputs/${id}`, b),
  compareOutput: (id: number, b: { reference_ids?: number[]; output_ids?: number[] }) =>
    post<{ output_id: number; results: CompareResult[]; note: string }>(`/api/outputs/${id}/compare`, b),
  exportOutputs: (ids: number[]) => post<Blob>("/api/outputs/export", { output_ids: ids }),
  // comfy & settings
  comfyStatus: () => get<ComfyStatus>("/api/comfy/status"),
  diagnostics: () => get<{ status: ComfyStatus; checks: { name: string; ok: boolean; detail: string }[] }>("/api/comfy/diagnostics"),
  settings: () => get<{ comfy_url: string }>("/api/settings"),
  saveSettings: (comfy_url: string) => put<{ comfy_url: string; status: ComfyStatus }>("/api/settings", { comfy_url }),
  testUrl: (comfy_url: string) => post<{ reachable: boolean; version?: string; error?: string }>("/api/settings/test", { comfy_url }),
  customNodes: () => get<{ package: string; version: string; package_path: string; comfy_reachable: boolean; nodes: CustomNodeInfo[] }>("/api/custom-nodes"),
  seedDemo: () => post<Project>("/api/demo/jewelry"),
};

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
