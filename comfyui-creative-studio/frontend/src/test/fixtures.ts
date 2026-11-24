import type { Job, Project, Workflow } from "../lib/types";

export const project: Project = {
  id: 1, name: "Luxury Jewelry Campaign", description: "Winter", client: "Acme", status: "active", template_key: "jewelry_campaign",
  meta: {}, cover_reference_id: null, cover_url: null, created_at: "2026-11-24T10:00:00Z", updated_at: "2026-11-24T10:00:00Z",
  campaigns: [{ id: 1, project_id: 1, name: "Winter Collection 2026", description: "", status: "active", created_at: "2026-11-24T10:00:00Z" }],
  counts: { references: 3, outputs: 6, selected: 1 },
};

export const workflow: Workflow = {
  id: 7, name: "Packshot", description: "", category: "jewelry_campaign", project_id: 1, is_template: false, source_format: "api",
  executable: true, api_source: "imported", conversion_warnings: [], node_types: ["KSampler"], models: [], node_count: 8,
  created_at: "2026-11-24T10:00:00Z", updated_at: "2026-11-24T10:00:00Z",
  parameters: [
    { key: "6.text", node_id: "6", input: "text", label: "Positive prompt", type: "text", group: "prompt", default: "a ring", role: "positive" },
    { key: "3.steps", node_id: "3", input: "steps", label: "Steps", type: "int", group: "sampling", default: 20, min: 1, max: 100 },
    { key: "3.sampler_name", node_id: "3", input: "sampler_name", label: "Sampler", type: "choice", group: "sampling", default: "euler", choices: ["euler", "dpmpp_2m"] },
  ],
};

export function job(over: Partial<Job>): Job {
  return {
    id: 1, project_id: 1, campaign_id: null, workflow_id: 7, consistency_config_id: null, batch_id: "b1", variation_index: 0,
    name: "Packshot · v1", status: "submitted", comfy_prompt_id: "p1", server_url: "http://comfy", parameter_values: { "3.seed": 5 },
    image_bindings: {}, progress: {}, error: null, execution_seconds: null, created_at: "2026-11-24T10:00:00Z",
    submitted_at: null, finished_at: null, outputs: [], ...over,
  };
}
