import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../components/ui";
import { Projects } from "../pages/Projects";
import { Production } from "../pages/Production";
import { Workflows } from "../pages/Workflows";
import { job, project, workflow } from "./fixtures";
import { mockApi } from "./mockApi";

const wrap = (ui: React.ReactNode, path = "/") => render(
  <ToastProvider><MemoryRouter initialEntries={[path]}><Routes><Route path="*" element={ui} /></Routes></MemoryRouter></ToastProvider>,
);

afterEach(() => vi.unstubAllGlobals());

describe("Projects page", () => {
  it("lists projects and creates one from a template", async () => {
    const calls = mockApi({
      "/api/projects": [project],
      "/api/project-templates": [{ key: "jewelry_campaign", label: "Jewelry campaign", description: "d", campaigns: ["Packshots"], collections: [] }],
      "POST /api/projects": { ...project, id: 2, name: "New one" },
    });
    wrap(<Projects />);
    expect(await screen.findByText("Luxury Jewelry Campaign")).toBeInTheDocument();
    expect(screen.getByText("1 finals")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /New project/ })[0]);
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByPlaceholderText("Luxury Jewelry Campaign"), "New one");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/projects")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ name: "New one", template_key: "jewelry_campaign" });
  });
});

describe("Workflows import", () => {
  it("detects the JSON format while pasting", async () => {
    mockApi({ "/api/workflows": [], "/api/workflow-categories": ["jewelry_campaign"], "/api/projects": [] });
    wrap(<Workflows />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Import workflow/ }))[0]);
    const box = screen.getByPlaceholderText(/class_type/);
    await userEvent.click(box);
    await userEvent.paste('{"nodes": [], "links": []}');
    expect(await screen.findByText(/UI \(graph\) format detected/)).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.paste('{"3": {"class_type": "KSampler", "inputs": {}}}');
    expect(await screen.findByText(/API format detected/)).toBeInTheDocument();
  });
});

describe("Production board", () => {
  const base = {
    "/api/projects": [project], "/api/workflows": [workflow], "/api/consistency": [], "/api/references": [],
    "/api/workflows/7": workflow,
    "/api/workflows/7/dependencies": { checked: true, ready: true, missing_nodes: [], missing_models: [], invalid_values: [], structure_issues: [], node_types: [], models: [], methods: [] },
  };

  it("shows job states and summarised ComfyUI errors as reported by the backend", async () => {
    mockApi({
      ...base,
      "/api/comfy/status": { url: "http://comfy", reachable: true, websocket_connected: true },
      "/api/jobs": [
        job({ id: 1, status: "running", progress: { value: 3, max: 20, node: "3" } }),
        job({ id: 2, variation_index: 1, status: "failed", error: { type: "prompt_outputs_failed_validation", message: "Prompt outputs failed validation",
          node_errors: { "4": { class_type: "CheckpointLoaderSimple", errors: [{ message: "Value not in list", details: "ckpt_name: 'x' not in []" }] } } } }),
        job({ id: 3, variation_index: 2, status: "submitted", progress: { connection: "unreachable" } }),
      ],
    });
    wrap(<Production />, "/production");
    expect(await screen.findByText(/step 3\/20/)).toBeInTheDocument();
    expect(screen.getByText(/#4 CheckpointLoaderSimple/)).toBeInTheDocument();
    expect(screen.getByText(/status unknown, not assumed finished/)).toBeInTheDocument();
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  it("submits a batch with only edited values", async () => {
    const calls = mockApi({
      ...base, "/api/jobs": [],
      "/api/comfy/status": { url: "http://comfy", reachable: true, websocket_connected: true },
      "POST /api/generate": { batch_id: "new", jobs: [] },
    });
    wrap(<Production />, "/production?workflow=7&project=1");
    const steps = await screen.findByLabelText("Steps");
    await userEvent.clear(steps);
    await userEvent.type(steps, "12");
    await userEvent.click(screen.getByRole("button", { name: /Generate 2 variations/ }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/generate")).toBe(true));
    const body = calls.find((c) => c.path === "/api/generate")!.body as Record<string, unknown>;
    expect(body).toMatchObject({ workflow_id: 7, project_id: 1, variations: 2, seed_mode: "increment", values: { "3.steps": 12 } });
    expect(Object.keys(body.values as object)).toEqual(["3.steps"]);
  });

  it("disables generation when ComfyUI is offline", async () => {
    mockApi({ ...base, "/api/jobs": [], "/api/comfy/status": { url: "http://comfy", reachable: false, websocket_connected: false } });
    wrap(<Production />, "/production?workflow=7");
    expect(await screen.findByText(/ComfyUI is offline/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generate 2 variations/ })).toBeDisabled();
  });
});
