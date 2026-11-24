import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Columns2, Download, Sparkles, Square, X } from "lucide-react";
import { PageHead } from "../components/Layout";
import { groupParams, ImageBinding, ParamField } from "../components/params";
import { CompareView, OutputLightbox, OutputTile } from "../components/outputs";
import { Callout, EmptyState, Progress, Segmented, Spinner, StatusBadge, Tabs, useAction } from "../components/ui";
import { api, downloadBlob } from "../lib/api";
import { label, relativeTime, useAsync } from "../lib/hooks";
import type { Job, Reference } from "../lib/types";

export function Production() {
  const [sp, setSp] = useSearchParams();
  const batch = sp.get("batch") ?? "";
  const [tab, setTab] = useState<"jobs" | "gallery">(batch ? "jobs" : "jobs");
  return (
    <div className="page">
      <PageHead title="Production Board" sub="Configure and launch generations, follow them live, then review, compare and select final assets."
        actions={batch ? <button className="btn" onClick={() => { sp.delete("batch"); setSp(sp); }}><X size={14} />Clear batch filter</button> : undefined} />
      <div className="split-left">
        <GeneratePanel onSubmitted={(b) => { sp.set("batch", b); setSp(sp); setTab("jobs"); }} />
        <div className="stack">
          <Tabs value={tab} onChange={setTab} tabs={[{ value: "jobs", label: "Jobs" }, { value: "gallery", label: "Gallery" }]} />
          {tab === "jobs" ? <JobsBoard batch={batch} projectId={sp.get("project") ? Number(sp.get("project")) : undefined} /> : <Gallery batch={batch} />}
        </div>
      </div>
    </div>
  );
}

function GeneratePanel({ onSubmitted }: { onSubmitted: (batch: string) => void }) {
  const [sp] = useSearchParams();
  const [mode, setMode] = useState<"workflow" | "config">(sp.get("config") ? "config" : "workflow");
  const [projectId, setProjectId] = useState<number | undefined>(sp.get("project") ? Number(sp.get("project")) : undefined);
  const [campaignId, setCampaignId] = useState<number | undefined>(sp.get("campaign") ? Number(sp.get("campaign")) : undefined);
  const [workflowId, setWorkflowId] = useState<number | undefined>(sp.get("workflow") ? Number(sp.get("workflow")) : undefined);
  const [configId, setConfigId] = useState<number | undefined>(sp.get("config") ? Number(sp.get("config")) : undefined);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [bindings, setBindings] = useState<Record<string, number>>({});
  const [variations, setVariations] = useState(2);
  const [seedMode, setSeedMode] = useState<"increment" | "random" | "fixed">("increment");
  const [baseSeed, setBaseSeed] = useState<string>("");
  const [name, setName] = useState("");
  const projects = useAsync(() => api.projects(), []);
  const workflows = useAsync(() => api.workflows(), []);
  const configs = useAsync(() => api.consistencyConfigs(), []);
  const refs = useAsync(() => api.references(), []);
  const status = useAsync(api.comfyStatus, [], 6000);
  const config = configs.data?.find((c) => c.id === configId);
  const wfId = mode === "config" ? config?.workflow_id : workflowId;
  const wf = useAsync(() => (wfId ? api.workflow(wfId) : Promise.resolve(undefined)), [wfId]);
  const deps = useAsync(() => (wfId ? api.dependencies(wfId) : Promise.resolve(undefined)), [wfId]);
  const project = projects.data?.find((p) => p.id === projectId);
  const refById = useMemo(() => new Map((refs.data ?? []).map((r) => [r.id, r])), [refs.data]);
  const { run, busy } = useAction();

  useEffect(() => { setValues({}); setBindings({}); }, [wfId]);
  useEffect(() => { if (config?.project_id && !projectId) setProjectId(config.project_id); }, [config, projectId]);

  const effectiveBindings = { ...(config?.image_bindings ?? {}), ...bindings };
  const defaults = { ...(config?.values ?? {}) };
  const params = wf.data?.parameters ?? [];
  const canRun = !!wf.data?.executable && !!status.data?.reachable && (mode === "workflow" ? !!workflowId : !!configId);

  const submit = async () => {
    const r = await run(() => api.generate({
      workflow_id: mode === "workflow" ? workflowId : undefined, consistency_config_id: mode === "config" ? configId : undefined,
      project_id: projectId ?? null, campaign_id: campaignId ?? null, name: name || undefined, values, image_bindings: bindings,
      variations, seed_mode: seedMode, base_seed: baseSeed === "" ? null : Number(baseSeed),
    }), "Batch submitted to ComfyUI");
    if (r) onSubmitted(r.batch_id);
  };

  return (
    <section className="card stack" style={{ position: "sticky", top: 20 }}>
      <div className="row between"><h2>New generation</h2><Segmented value={mode} onChange={setMode} options={[{ value: "workflow", label: "Workflow" }, { value: "config", label: "Config" }]} /></div>
      <div className="grid-2">
        <label className="field"><span>Project</span><select className="select" value={projectId ?? ""} onChange={(e) => { setProjectId(e.target.value ? Number(e.target.value) : undefined); setCampaignId(undefined); }}>
          <option value="">No project</option>{(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label className="field"><span>Campaign</span><select className="select" value={campaignId ?? ""} disabled={!project} onChange={(e) => setCampaignId(e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">—</option>{(project?.campaigns ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      </div>
      {mode === "workflow" ? (
        <label className="field"><span>Workflow</span><select className="select" value={workflowId ?? ""} onChange={(e) => setWorkflowId(e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">Choose…</option>{(workflows.data ?? []).map((w) => <option key={w.id} value={w.id} disabled={!w.executable}>{w.name}{w.executable ? "" : " (not executable)"}</option>)}</select></label>
      ) : (
        <label className="field"><span>Consistency configuration</span><select className="select" value={configId ?? ""} onChange={(e) => setConfigId(e.target.value ? Number(e.target.value) : undefined)}>
          <option value="">Choose…</option>{(configs.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          {config && <span className="hint">Workflow “{config.workflow_name}”{config.profile_name && <>, profile “{config.profile_name}”</>}. Values below override the configuration for this batch only.</span>}</label>
      )}

      {status.data && !status.data.reachable && <Callout kind="err">ComfyUI is offline ({status.data.url}). <Link to="/settings"><u>Check settings</u></Link></Callout>}
      {deps.data && deps.data.checked && !deps.data.ready && (
        <Callout kind="warn">Dependency check failed: {[...deps.data.missing_nodes.map((n) => `node ${n}`), ...deps.data.missing_models.map((m) => `model ${m.value}`)].join(", ") || "graph issues"}.
          ComfyUI will reject the job. <Link to={`/workflows/${wfId}`}><u>Details</u></Link></Callout>
      )}

      {wf.data && (
        <div className="stack" style={{ maxHeight: "52vh", overflowY: "auto", paddingRight: 4 }}>
          {groupParams(params).map(([group, ps]) => (
            <div key={group} className="stack tight">
              <div className="nav-section" style={{ padding: "6px 0 0" }}>{label(group)}</div>
              {ps.map((p) => p.type === "image" ? (
                <ImageBinding key={p.key} p={p} reference={effectiveBindings[p.key] ? refById.get(effectiveBindings[p.key]) : undefined}
                  onChange={(r: Reference | null) => setBindings((b) => { const n = { ...b }; if (r) n[p.key] = r.id; else delete n[p.key]; return n; })} />
              ) : (
                <ParamField key={p.key} p={{ ...p, default: p.key in defaults ? defaults[p.key] : p.default }} value={values[p.key]}
                  onChange={(v) => setValues((x) => ({ ...x, [p.key]: v }))} />
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="sep" />
      <div className="grid-2">
        <label className="field"><span>Variations</span><input className="input" type="number" min={1} max={32} value={variations} onChange={(e) => setVariations(Math.max(1, Math.min(32, Number(e.target.value))))} /></label>
        <label className="field"><span>Seed mode</span><select className="select" value={seedMode} onChange={(e) => setSeedMode(e.target.value as typeof seedMode)}>
          <option value="increment">Increment from base</option><option value="random">Random per variation</option><option value="fixed">Fixed (same seed)</option></select></label>
        <label className="field"><span>Base seed</span><input className="input" type="number" placeholder="workflow value" value={baseSeed} onChange={(e) => setBaseSeed(e.target.value)} /></label>
        <label className="field"><span>Batch name</span><input className="input" placeholder="optional" value={name} onChange={(e) => setName(e.target.value)} /></label>
      </div>
      <button className="btn primary" disabled={!canRun || busy} onClick={submit}><Sparkles size={15} />{busy ? "Submitting…" : `Generate ${variations} variation${variations > 1 ? "s" : ""}`}</button>
    </section>
  );
}

function JobsBoard({ batch, projectId }: { batch: string; projectId?: number }) {
  const [active, setActive] = useState(true);
  const jobs = useAsync(() => api.jobs({ batch_id: batch || undefined, project_id: projectId, limit: 150 }), [batch, projectId], active ? 1500 : 5000);
  useEffect(() => { setActive(!!jobs.data?.some((j) => j.status === "submitted" || j.status === "running")); }, [jobs.data]);
  const [open, setOpen] = useState<number>();
  const { run } = useAction();
  const batches = useMemo(() => {
    const m = new Map<string, Job[]>();
    for (const j of jobs.data ?? []) m.set(j.batch_id, [...(m.get(j.batch_id) ?? []), j]);
    return [...m.entries()];
  }, [jobs.data]);
  if (!jobs.data) return <Spinner />;
  if (!jobs.data.length) return <EmptyState icon={<Sparkles size={28} />} title="No jobs yet">Configure a generation on the left. Jobs are tracked until ComfyUI's history confirms the result.</EmptyState>;
  return (
    <div className="stack">
      {batches.map(([b, js]) => {
        const done = js.filter((j) => j.status === "completed").length;
        return (
          <section key={b} className="card">
            <div className="card-head">
              <div><h3>{js[0].name.replace(/ · v\d+$/, "")}</h3><div className="muted tiny">batch {b.slice(0, 8)} · {relativeTime(js[js.length - 1].created_at)} · {done}/{js.length} completed</div></div>
              <Link className="btn sm ghost" to={`/production?batch=${b}`}>Focus</Link>
            </div>
            <div className="list">{[...js].sort((a, z) => a.variation_index - z.variation_index).map((j) => (
              <div key={j.id} className="list-item" data-testid="job-row" style={{ alignItems: "flex-start" }}>
                <div style={{ width: 110 }} className="stack tight"><StatusBadge status={j.status} /><span className="muted tiny">#{j.id} · v{j.variation_index + 1}</span></div>
                <div className="grow stack tight">
                  {(j.status === "submitted" || j.status === "running") && <>
                    <Progress value={j.progress.value} max={j.progress.max} indeterminate={!j.progress.max} />
                    <span className="muted tiny">{j.progress.connection === "unreachable" ? "ComfyUI unreachable — status unknown, not assumed finished"
                      : j.status === "submitted" ? `Queued${j.progress.queue_position ? ` · position ${j.progress.queue_position}` : ""}` : `Running${j.progress.node ? ` · node ${j.progress.node}` : ""}${j.progress.max ? ` · step ${j.progress.value}/${j.progress.max}` : ""}`}</span>
                  </>}
                  {j.error && <div className="small" style={{ color: j.status === "failed" ? "var(--err)" : "var(--warn)" }}>{j.error.message}{j.error.node_type && ` (node ${j.error.node_id} ${j.error.node_type})`}
                    {j.error.node_errors && <NodeErrors errors={j.error.node_errors} />}</div>}
                  {j.outputs.length > 0 && <div className="row wrap" style={{ gap: 6 }}>{j.outputs.map((o) => (
                    <img key={o.id} src={o.thumb_url} alt="" className="thumb lg" style={{ cursor: "pointer" }} onClick={() => setOpen(o.id)} />
                  ))}</div>}
                  <span className="muted tiny">seed {jobSeed(j)}{j.execution_seconds != null && ` · ${j.execution_seconds.toFixed(1)} s`}</span>
                </div>
                {(j.status === "submitted" || j.status === "running") && <button className="btn sm" onClick={async () => { await run(() => api.cancelJob(j.id), j.status === "running" ? "Interrupt sent" : "Removed from queue"); void jobs.reload(); }}><Square size={12} />{j.status === "running" ? "Interrupt" : "Cancel"}</button>}
              </div>
            ))}</div>
          </section>
        );
      })}
      {open && <OutputLightbox id={open} onClose={() => setOpen(undefined)} />}
    </div>
  );
}

function Gallery({ batch }: { batch: string }) {
  const [filter, setFilter] = useState<"all" | "favorite" | "selected">("all");
  const projects = useAsync(() => api.projects(), []);
  const [projectId, setProjectId] = useState<number>();
  const outs = useAsync(() => api.outputs({ batch_id: batch || undefined, project_id: projectId, favorite: filter === "favorite" || undefined, selected: filter === "selected" || undefined }), [batch, projectId, filter], 5000);
  const [checked, setChecked] = useState<number[]>([]);
  const [open, setOpen] = useState<number>();
  const [comparing, setComparing] = useState(false);
  const { run } = useAction();
  const toggle = (id: number) => setChecked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  return (
    <div className="stack">
      <div className="row wrap">
        <Segmented value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "favorite", label: "Favorites" }, { value: "selected", label: "Final selects" }]} />
        <select className="select" style={{ width: 220 }} value={projectId ?? ""} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)} aria-label="Project filter">
          <option value="">All projects</option>{(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <div className="right row">
          {checked.length > 0 && <span className="muted small">{checked.length} selected</span>}
          <button className="btn sm" disabled={checked.length < 2 || checked.length > 4} onClick={() => setComparing(true)}><Columns2 size={14} />Compare</button>
          <button className="btn sm" disabled={!checked.length} onClick={async () => { const b = await run(() => api.exportOutputs(checked), "Export ready"); if (b) downloadBlob(b, "creative_studio_export.zip"); }}><Download size={14} />Export</button>
        </div>
      </div>
      <p className="muted tiny">Tick 2–4 images to compare settings side by side. Export bundles images with their metadata and exact API prompt.</p>
      {!outs.data ? <Spinner /> : outs.data.length ? <div className="gallery lg">{outs.data.map((o) => (
        <OutputTile key={o.id} o={o} checked={checked.includes(o.id)} onToggleCheck={() => toggle(o.id)} onOpen={() => setOpen(o.id)} onChange={() => void outs.reload()} />
      ))}</div> : <EmptyState title="No outputs">Completed jobs appear here.</EmptyState>}
      {open && <OutputLightbox id={open} onClose={() => setOpen(undefined)} onChange={() => void outs.reload()} />}
      {comparing && <CompareView ids={checked} onClose={() => setComparing(false)} />}
    </div>
  );
}

function jobSeed(j: Job): string {
  const fromOutput = j.outputs.find((o) => o.summary?.seed != null)?.summary?.seed;
  if (fromOutput != null) return String(fromOutput);
  const v = Object.entries(j.parameter_values).find(([k]) => /(^|\.)(seed|noise_seed)$/.test(k))?.[1];
  return v != null ? String(v) : "set in graph";
}

/** Summarise ComfyUI node_errors ({node_id: {class_type, errors: [{message, details}]}}). */
function NodeErrors({ errors }: { errors: Record<string, unknown> }) {
  const rows = Object.entries(errors).flatMap(([nid, e]) => {
    const ne = e as { class_type?: string; errors?: { message?: string; details?: string }[] };
    return (ne.errors ?? []).map((x, i) => <li key={nid + i}><span className="mono">#{nid} {ne.class_type}</span>: {x.message}{x.details ? ` — ${x.details}` : ""}</li>);
  });
  if (!rows.length) return null;
  return <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18, color: "var(--text-2)" }}>{rows}</ul>;
}
