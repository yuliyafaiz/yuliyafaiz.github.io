import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Gem, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { PageHead } from "../components/Layout";
import { ImageBinding, ParamField } from "../components/params";
import { CompareMeters, OutputLightbox } from "../components/outputs";
import { Callout, EmptyState, ErrorNote, Spinner, StatusBadge, useAction } from "../components/ui";
import { api } from "../lib/api";
import { label, relativeTime, useAsync } from "../lib/hooks";
import type { CompareResult, ConsistencyConfig, Reference } from "../lib/types";

export function Consistency() {
  const [params] = useSearchParams();
  const configs = useAsync(() => api.consistencyConfigs(), []);
  const methods = useAsync(api.consistencyMethods, []);
  const profileHint = params.get("profile");
  return (
    <div className="page">
      <PageHead title="Consistency Manager" sub="Reusable bindings between profiles, reference images and conditioning workflows (IPAdapter, ControlNet, inpainting, img2img). Configure once, re-run on any project."
        actions={<Link className="btn primary" to={`/consistency/new${profileHint ? `?profile=${profileHint}` : ""}`}><Plus size={15} />New configuration</Link>} />
      <div className="split">
        <div>
          {!configs.data ? <Spinner /> : configs.data.length ? (
            <div className="grid-2">{configs.data.map((c) => (
              <Link key={c.id} to={`/consistency/${c.id}`} className="card stack tight" data-testid="config-card">
                <div className="row between"><b className="ellipsis">{c.name}</b><Gem size={15} color="var(--accent)" /></div>
                <div className="muted small ellipsis">{c.description || "—"}</div>
                <div className="small text-2">Workflow: {c.workflow_name}</div>
                <div className="small text-2">Profile: {c.profile_name ?? "none"}</div>
                <div className="row wrap" style={{ gap: 5, marginTop: 4 }}>{c.methods.map((m) => <span key={m} className="badge accent">{label(m)}</span>)}
                  <span className="badge">{Object.keys(c.image_bindings).length} image bindings</span></div>
              </Link>
            ))}</div>
          ) : <EmptyState icon={<Gem size={30} />} title="No configurations" action={<Link className="btn primary" to="/consistency/new">Create configuration</Link>}>
            Combine a workflow with a Product or Character Profile and the reference images that condition it.</EmptyState>}
        </div>
        <section className="card stack">
          <h2>Supported methods</h2>
          <p className="muted small">Creative Studio does not reimplement these algorithms; it records how existing ComfyUI nodes are fed so results can be reproduced.</p>
          {Object.entries(methods.data ?? {}).map(([k, v]) => <div key={k}><div className="small" style={{ fontWeight: 600 }}>{label(k)}</div><div className="small muted">{v}</div></div>)}
        </section>
      </div>
    </div>
  );
}

export function ConsistencyEditor() {
  const idParam = useParams().id!;
  const isNew = idParam === "new";
  const [search] = useSearchParams();
  const nav = useNavigate();
  const existing = useAsync(() => (isNew ? Promise.resolve(undefined) : api.consistencyConfig(Number(idParam))), [idParam]);
  const workflows = useAsync(() => api.workflows(), []);
  const profiles = useAsync(() => api.profiles(), []);
  const projects = useAsync(() => api.projects(), []);
  const refs = useAsync(() => api.references(), []);
  const [c, setC] = useState<Partial<ConsistencyConfig>>({ name: "", description: "", image_bindings: {}, values: {}, use_profile_prompt: true,
    profile_id: search.get("profile") ? Number(search.get("profile")) : null });
  useEffect(() => { if (existing.data) setC(existing.data); }, [existing.data]);
  const plan = useAsync(() => (c.workflow_id ? api.consistencyPlan(c.workflow_id, c.profile_id) : Promise.resolve(undefined)), [c.workflow_id, c.profile_id]);
  const refById = useMemo(() => new Map((refs.data ?? []).map((r) => [r.id, r])), [refs.data]);
  const { run, busy } = useAction();
  const [variations, setVariations] = useState(3);

  if (existing.error) return <div className="page"><ErrorNote error={existing.error} /></div>;
  const save = async () => {
    const body = { name: c.name, description: c.description, profile_id: c.profile_id ?? null, project_id: c.project_id ?? null,
      image_bindings: c.image_bindings, values: c.values, use_profile_prompt: c.use_profile_prompt };
    const r = isNew ? await run(() => api.createConsistency({ ...body, workflow_id: c.workflow_id }), "Configuration created")
      : await run(() => api.updateConsistency(Number(idParam), body), "Configuration saved");
    if (r && isNew) nav(`/consistency/${r.id}`, { replace: true });
    if (r && !isNew) existing.setData(r);
    return r;
  };
  const setBinding = (key: string, r: Reference | null) => {
    const b = { ...(c.image_bindings ?? {}) };
    if (r) b[key] = r.id; else delete b[key];
    setC({ ...c, image_bindings: b });
  };

  return (
    <div className="page">
      <PageHead crumbs={<><Link to="/consistency">Consistency</Link><span>/</span></>} title={isNew ? "New configuration" : c.name || "Configuration"}
        actions={<>
          {!isNew && <button className="btn danger" onClick={async () => { if (confirm("Delete configuration?")) { await run(() => api.deleteConsistency(Number(idParam))); nav("/consistency"); } }}><Trash2 size={15} /></button>}
          <button className="btn" disabled={busy || !c.name || !c.workflow_id} onClick={save}>Save</button>
          {!isNew && <>
            <input className="input" type="number" min={1} max={32} style={{ width: 70 }} value={variations} onChange={(e) => setVariations(Number(e.target.value))} aria-label="Variations" />
            <button className="btn primary" disabled={busy} onClick={async () => {
              const saved = await save(); if (!saved) return;
              const r = await run(() => api.generate({ consistency_config_id: Number(idParam), variations, seed_mode: "increment" }), "Batch submitted");
              if (r) nav(`/production?batch=${r.batch_id}`);
            }}><Sparkles size={15} />Generate {variations}</button>
          </>}
        </>} />

      <div className="split">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <div className="grid-2">
              <label className="field"><span>Name</span><input className="input" value={c.name ?? ""} onChange={(e) => setC({ ...c, name: e.target.value })} placeholder="Aurora · packshot on black marble" /></label>
              <label className="field"><span>Workflow</span>
                <select className="select" value={c.workflow_id ?? ""} disabled={!isNew} onChange={(e) => setC({ ...c, workflow_id: Number(e.target.value), image_bindings: {}, values: {} })}>
                  <option value="">Choose a workflow…</option>{(workflows.data ?? []).filter((w) => w.executable).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select></label>
              <label className="field"><span>Profile</span>
                <select className="select" value={c.profile_id ?? ""} onChange={(e) => setC({ ...c, profile_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">No profile</option>{(profiles.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.kind})</option>)}
                </select></label>
              <label className="field"><span>Project</span>
                <select className="select" value={c.project_id ?? ""} onChange={(e) => setC({ ...c, project_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Any project</option>{(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select></label>
            </div>
            <label className="field"><span>Description</span><input className="input" value={c.description ?? ""} onChange={(e) => setC({ ...c, description: e.target.value })} /></label>
            <label className="check"><input type="checkbox" checked={!!c.use_profile_prompt} onChange={(e) => setC({ ...c, use_profile_prompt: e.target.checked })} />
              Append the profile's prompt fragment to the positive/negative prompts</label>
          </section>

          {c.workflow_id && plan.data && (<>
            <section className="card stack">
              <div className="card-head" style={{ marginBottom: 0 }}><h2>Reference bindings</h2>
                {c.profile_id && Object.keys(plan.data.suggested_bindings).length > 0 && (
                  <button className="btn sm" onClick={() => setC({ ...c, image_bindings: { ...c.image_bindings, ...plan.data!.suggested_bindings } })}><Wand2 size={13} />Apply profile images</button>
                )}</div>
              {plan.data.profile_loader_nodes.length > 0 && <Callout kind="info">This workflow loads the profile in-graph (node {plan.data.profile_loader_nodes.join(", ")}). Profile images are uploaded and passed automatically when a profile is selected.</Callout>}
              {plan.data.image_parameters.length ? plan.data.image_parameters.map((p) => (
                <ImageBinding key={p.key} p={p} reference={c.image_bindings?.[p.key] ? refById.get(c.image_bindings[p.key]) : undefined} onChange={(r) => setBinding(p.key, r)} />
              )) : <p className="muted small">This workflow has no LoadImage inputs.</p>}
            </section>
            <section className="card stack">
              <h2>Conditioning parameters</h2>
              {plan.data.conditioning_parameters.length ? <div className="grid-2">{plan.data.conditioning_parameters.map((p) => (
                <ParamField key={p.key} p={p} value={c.values?.[p.key]} onChange={(v) => setC({ ...c, values: { ...c.values, [p.key]: v } })} />
              ))}</div> : <p className="muted small">No conditioning strengths detected. Expose inputs on the workflow's Parameters tab.</p>}
            </section>
          </>)}
          {!isNew && <ConfigResults configId={Number(idParam)} bindings={c.image_bindings ?? {}} />}
        </div>

        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>Methods in this workflow</h2>
            {plan.data?.methods.length ? plan.data.methods.map((m) => <div key={m.key}><span className="badge accent">{label(m.key)}</span><p className="small muted" style={{ marginTop: 4 }}>{m.info}</p></div>)
              : <p className="muted small">{c.workflow_id ? "No conditioning nodes detected." : "Choose a workflow."}</p>}
          </section>
          <Callout kind="warn">Reference preservation is limited by the model and method. Masked compositing keeps product pixels exact; IPAdapter, ControlNet and img2img guide but do not guarantee geometry, stone placement or identity. Always review outputs against the references.</Callout>
        </div>
      </div>
    </div>
  );
}

function ConfigResults({ configId, bindings }: { configId: number; bindings: Record<string, number> }) {
  const jobs = useAsync(() => api.jobs({ limit: 200 }).then((js) => js.filter((j) => j.consistency_config_id === configId)), [configId], 5000);
  const [open, setOpen] = useState<number>();
  const [cmp, setCmp] = useState<{ id: number; results: CompareResult[] }>();
  const { run } = useAction();
  const outputs = (jobs.data ?? []).flatMap((j) => j.outputs);
  return (
    <section className="card stack">
      <h2>Results & reference comparison</h2>
      {(jobs.data ?? []).slice(0, 6).map((j) => (
        <div key={j.id} className="row small"><StatusBadge status={j.status} /><span className="grow ellipsis">{j.name}</span><span className="muted">{relativeTime(j.created_at)}</span></div>
      ))}
      {outputs.length ? <div className="gallery sm">{outputs.map((o) => (
        <div key={o.id} className="stack tight"><div className="tile" onClick={() => setOpen(o.id)}><img src={o.thumb_url} alt="" /></div>
          <button className="btn sm" disabled={!Object.keys(bindings).length} onClick={async () => {
            const r = await run(() => api.compareOutput(o.id, { reference_ids: [...new Set(Object.values(bindings))] }));
            if (r) setCmp({ id: o.id, results: r.results });
          }}>Compare</button></div>
      ))}</div> : <p className="muted small">Run the configuration to see results here.</p>}
      {cmp && <><div className="small">Output #{cmp.id} vs bound references — heuristic signals, not proof of preservation:</div><CompareMeters results={cmp.results} /></>}
      {open && <OutputLightbox id={open} onClose={() => setOpen(undefined)} />}
    </section>
  );
}
