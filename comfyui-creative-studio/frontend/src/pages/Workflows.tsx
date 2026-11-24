import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CheckCircle2, Download, FileJson, RefreshCw, Sparkles, Trash2, Upload, Workflow as WfIcon, XCircle } from "lucide-react";
import { PageHead } from "../components/Layout";
import { Callout, EmptyState, ErrorNote, Modal, Spinner, Tabs, useAction } from "../components/ui";
import { api } from "../lib/api";
import { label, relativeTime, useAsync } from "../lib/hooks";
import type { WorkflowParam } from "../lib/types";

/** Client-side mirror of the backend format detection, for instant feedback while importing. */
export function detectFormat(data: unknown): "api" | "ui" | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const d = data as Record<string, unknown>;
  const inner = d.prompt && typeof d.prompt === "object" ? (d.prompt as Record<string, unknown>) : d;
  if (Array.isArray(d.nodes) && "links" in d) return "ui";
  const vals = Object.values(inner);
  if (vals.length && vals.every((v) => v && typeof v === "object" && "class_type" in (v as object) && "inputs" in (v as object))) return "api";
  return null;
}

export function Workflows() {
  const [category, setCategory] = useState("");
  const wfs = useAsync(() => api.workflows({ category }), [category]);
  const cats = useAsync(api.workflowCategories, []);
  const [importing, setImporting] = useState(false);
  const nav = useNavigate();
  return (
    <div className="page">
      <PageHead title="Workflows" sub="Import ComfyUI workflows, check their dependencies against your server, and expose the parameters creators should change."
        actions={<>
          <select className="select" style={{ width: 200 }} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filter category">
            <option value="">All categories</option>{(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <button className="btn primary" onClick={() => setImporting(true)}><Upload size={15} />Import workflow</button>
        </>} />
      {!wfs.data ? <Spinner /> : wfs.data.length ? (
        <div className="card flush"><table className="table"><thead><tr><th>Workflow</th><th>Category</th><th>Source</th><th>Status</th><th>Params</th><th>Updated</th></tr></thead>
          <tbody>{wfs.data.map((w) => (
            <tr key={w.id} className="clickable" onClick={() => nav(`/workflows/${w.id}`)}>
              <td><div className="row"><WfIcon size={15} className="muted" /><div><b>{w.name}</b>{w.is_template && <span className="badge" style={{ marginLeft: 8 }}>Template</span>}
                <div className="muted tiny ellipsis" style={{ maxWidth: 420 }}>{w.description}</div></div></div></td>
              <td className="small">{label(w.category)}</td>
              <td><span className="badge">{w.source_format === "api" ? "API export" : "UI workflow"}</span></td>
              <td>{w.executable ? <span className="badge ok">Executable{w.api_source === "converted" ? " (converted)" : ""}</span> : <span className="badge warn">Not executable</span>}</td>
              <td className="small">{w.parameters.length}</td>
              <td className="muted small nowrap">{relativeTime(w.updated_at)}</td>
            </tr>
          ))}</tbody></table></div>
      ) : <EmptyState icon={<FileJson size={30} />} title="No workflows" action={<button className="btn primary" onClick={() => setImporting(true)}>Import workflow</button>}>
        Export from ComfyUI with <b>Workflow → Export (API)</b> for the most reliable result. Regular saved workflows are converted using your server's node definitions.</EmptyState>}
      {importing && <ImportModal onClose={() => setImporting(false)} />}
    </div>
  );
}

function ImportModal({ onClose }: { onClose: () => void }) {
  const cats = useAsync(api.workflowCategories, []);
  const projects = useAsync(() => api.projects(), []);
  const [text, setText] = useState("");
  const [form, setForm] = useState({ name: "", category: "product_photography", description: "", project_id: "" as string, is_template: false });
  const { run, busy } = useAction();
  const nav = useNavigate();
  const parsed = useMemo(() => { try { return text ? JSON.parse(text) : undefined; } catch { return null; } }, [text]);
  const fmt = parsed ? detectFormat(parsed) : null;
  const onFile = async (f?: File) => {
    if (!f) return;
    setText(await f.text());
    if (!form.name) setForm((x) => ({ ...x, name: f.name.replace(/\.json$/i, "").replace(/[_-]+/g, " ") }));
  };
  return (
    <Modal title="Import ComfyUI workflow" onClose={onClose} size="wide" footer={<><button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={!fmt || !form.name || busy} onClick={async () => {
        const w = await run(() => api.importWorkflow({ ...form, project_id: form.project_id ? Number(form.project_id) : null, data: parsed }), "Workflow imported");
        if (w) nav(`/workflows/${w.id}`);
      }}>Import</button></>}>
      <div className="grid-2">
        <div className="stack">
          <label className="dropzone"><input type="file" accept=".json,application/json" hidden onChange={(e) => void onFile(e.target.files?.[0])} />
            <div className="row" style={{ justifyContent: "center" }}><Upload size={16} />Choose a workflow .json</div></label>
          <label className="field"><span>…or paste JSON</span><textarea className="textarea mono" rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder='{"3": {"class_type": "KSampler", "inputs": {…}}}' /></label>
          {text && (parsed === null ? <Callout kind="err">Not valid JSON.</Callout> : fmt === "api" ? <Callout kind="ok">API format detected — directly executable via /prompt.</Callout>
            : fmt === "ui" ? <Callout kind="warn">UI (graph) format detected. It will be converted using your ComfyUI's /object_info. For exact results, use <b>Export (API)</b> in ComfyUI.</Callout>
              : <Callout kind="err">Not a ComfyUI workflow (expected nodes/links or {"{node_id: {class_type, inputs}}"}).</Callout>)}
        </div>
        <div className="stack">
          <label className="field"><span>Name</span><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="field"><span>Category</span><select className="select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}</select></label>
          <label className="field"><span>Project</span><select className="select" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">No project (library)</option>{(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="field"><span>Description</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={form.is_template} onChange={(e) => setForm({ ...form, is_template: e.target.checked })} />Reusable template</label>
        </div>
      </div>
    </Modal>
  );
}

type Tab = "overview" | "parameters" | "json";

export function WorkflowDetailPage() {
  const id = Number(useParams().id);
  const wf = useAsync(() => api.workflow(id), [id]);
  const deps = useAsync(() => api.dependencies(id), [id]);
  const [tab, setTab] = useState<Tab>("overview");
  const [jsonView, setJsonView] = useState<"api" | "original">("api");
  const [attach, setAttach] = useState(false);
  const { run, busy } = useAction();
  const nav = useNavigate();
  const w = wf.data;
  if (wf.error) return <div className="page"><ErrorNote error={wf.error} /></div>;
  if (!w) return <div className="page"><Spinner /></div>;
  const d = deps.data;
  const reload = () => { void wf.reload(); void deps.reload(); };

  return (
    <div className="page">
      <PageHead crumbs={<><Link to="/workflows">Workflows</Link><span>/</span></>} title={w.name} sub={w.description}
        actions={<>
          <button className="btn danger" onClick={async () => { if (confirm("Delete workflow?")) { await run(() => api.deleteWorkflow(id), "Deleted"); nav("/workflows"); } }}><Trash2 size={15} /></button>
          <button className="btn" onClick={async () => { const c = await run(() => api.duplicateWorkflow(id), "Duplicated"); if (c) nav(`/workflows/${c.id}`); }}>Duplicate</button>
          <Link className="btn primary" to={`/production?workflow=${id}`} aria-disabled={!w.executable}><Sparkles size={15} />Run</Link>
        </>} />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Overview & dependencies" }, { value: "parameters", label: `Parameters (${w.parameters.length})` }, { value: "json", label: "JSON" }]} />

      {tab === "overview" && (
        <div className="split">
          <div className="stack" style={{ gap: 20 }}>
            {!w.executable && (
              <Callout kind="warn"><b>Not executable yet.</b> This is a UI-format workflow. {w.conversion_warnings.join(" ")}
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="btn sm" disabled={busy} onClick={async () => { await run(() => api.convertWorkflow(id), "Converted to API format"); reload(); }}><RefreshCw size={13} />Convert with /object_info</button>
                  <button className="btn sm" onClick={() => setAttach(true)}>Attach Export (API) file</button>
                </div></Callout>
            )}
            {w.executable && w.api_source === "converted" && (
              <Callout kind="info">Converted from the UI format by Creative Studio. ComfyUI's own <b>Export (API)</b> is authoritative — attach it if results differ.
                {w.conversion_warnings.length > 0 && <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{w.conversion_warnings.map((x) => <li key={x}>{x}</li>)}</ul>}
                <div style={{ marginTop: 8 }}><button className="btn sm" onClick={() => setAttach(true)}>Attach Export (API) file</button></div></Callout>
            )}
            <section className="card">
              <div className="card-head"><h2>Dependency check</h2>
                <button className="btn sm" onClick={() => void deps.reload()}><RefreshCw size={13} />Re-check</button></div>
              {!d ? <Spinner /> : !d.checked ? <Callout kind="warn">ComfyUI is not reachable, so installed nodes and models could not be checked.</Callout> : (
                <div className="stack">
                  {d.ready ? <Callout kind="ok">All nodes and models are available on the connected ComfyUI.</Callout>
                    : <Callout kind="err">This workflow cannot run on the connected ComfyUI yet — see below.</Callout>}
                  <DepRow ok={!d.missing_nodes.length} title="Custom nodes" detail={d.missing_nodes.length ? `Missing: ${d.missing_nodes.join(", ")}` : `${d.node_types.length} node types installed`} />
                  <DepRow ok={!d.missing_models.length} title="Models" detail={d.missing_models.length ? d.missing_models.map((m) => `${m.value} (${m.class_type}.${m.input})`).join(", ") : `${d.models.length} model references found`} />
                  <DepRow ok={!d.structure_issues.some((i) => i.severity === "error")} title="Graph structure"
                    detail={d.structure_issues.length ? d.structure_issues.map((i) => `#${i.node_id} ${i.class_type}: ${i.message}${i.severity === "warning" ? " (warning)" : ""}`).join(" · ") : "Inputs, links and types match the server's node definitions"} />
                  {d.invalid_values.length > 0 && <DepRow ok={false} title="Values" detail={d.invalid_values.map((v) => `#${v.node_id} ${v.input}=${String(v.value)}`).join(", ")} />}
                </div>
              )}
            </section>
            <section className="card">
              <h2 style={{ marginBottom: 12 }}>Models referenced</h2>
              {w.models.length ? <table className="table small"><thead><tr><th>Name</th><th>Kind</th><th>Node</th></tr></thead><tbody>
                {w.models.map((m) => <tr key={m.node_id + m.input}><td className="mono">{m.name}</td><td>{m.kind}</td><td className="muted">#{m.node_id} {m.class_type}</td></tr>)}</tbody></table>
                : <p className="muted small">No model files referenced.</p>}
            </section>
          </div>
          <div className="stack" style={{ gap: 20 }}>
            <section className="card">
              <h2 style={{ marginBottom: 12 }}>Details</h2>
              <dl className="kv small">
                <dt>Category</dt><dd>{label(w.category)}</dd>
                <dt>Imported as</dt><dd>{w.source_format === "api" ? "API format" : "UI workflow"}</dd>
                <dt>Executable</dt><dd>{w.executable ? `yes (${w.api_source})` : "no"}</dd>
                <dt>Nodes</dt><dd>{w.node_count}</dd>
                <dt>Methods</dt><dd>{w.methods?.length ? w.methods.map(label).join(", ") : "—"}</dd>
                <dt>Template</dt><dd>{w.is_template ? "yes" : "no"}</dd>
              </dl>
            </section>
            <section className="card">
              <h2 style={{ marginBottom: 12 }}>Node types</h2>
              <div className="row wrap" style={{ gap: 5 }}>{w.node_types.map((t) => <span key={t} className={`tag ${d?.missing_nodes.includes(t) ? "" : ""}`} style={d?.missing_nodes.includes(t) ? { color: "var(--err)" } : undefined}>{t}</span>)}</div>
            </section>
          </div>
        </div>
      )}

      {tab === "parameters" && <ParamEditor workflowId={id} params={w.parameters} onSaved={reload} />}

      {tab === "json" && (
        <div className="stack">
          <div className="row">
            <div className="segmented"><button className={jsonView === "api" ? "on" : ""} onClick={() => setJsonView("api")}>API format</button><button className={jsonView === "original" ? "on" : ""} onClick={() => setJsonView("original")}>Original (preserved)</button></div>
            <a className="btn sm right" href={`/api/workflows/${id}/download?which=${jsonView}`}><Download size={13} />Download</a>
          </div>
          <pre className="code">{JSON.stringify(jsonView === "api" ? w.api_json : w.original_json, null, 2) ?? "—"}</pre>
        </div>
      )}
      {attach && <AttachApi id={id} onClose={() => setAttach(false)} onDone={() => { setAttach(false); reload(); }} />}
    </div>
  );
}

function DepRow({ ok, title, detail }: { ok: boolean; title: string; detail: string }) {
  return (
    <div className="row" style={{ alignItems: "flex-start" }}>
      {ok ? <CheckCircle2 size={17} color="var(--ok)" /> : <XCircle size={17} color="var(--err)" />}
      <div className="grow"><div style={{ fontWeight: 550 }}>{title}</div><div className="small muted" style={{ overflowWrap: "anywhere" }}>{detail}</div></div>
    </div>
  );
}

function AttachApi({ id, onClose, onDone }: { id: number; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("");
  const { run } = useAction();
  return (
    <Modal title="Attach Export (API) JSON" onClose={onClose} size="wide" footer={<><button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={async () => { let data; try { data = JSON.parse(text); } catch { return; } if (await run(() => api.attachApiJson(id, data), "API format attached")) onDone(); }}>Attach</button></>}>
      <p className="small muted" style={{ marginBottom: 10 }}>In ComfyUI open the workflow and choose <b>Workflow → Export (API)</b>. The original UI workflow stays preserved.</p>
      <label className="dropzone" style={{ marginBottom: 10 }}><input type="file" accept=".json" hidden onChange={async (e) => setText((await e.target.files?.[0]?.text()) ?? "")} />Choose file</label>
      <textarea className="textarea mono" rows={14} value={text} onChange={(e) => setText(e.target.value)} />
    </Modal>
  );
}

function ParamEditor({ workflowId, params, onSaved }: { workflowId: number; params: WorkflowParam[]; onSaved: () => void }) {
  const [list, setList] = useState(params);
  const [adding, setAdding] = useState(false);
  const inputs = useAsync(() => api.workflowInputs(workflowId), [workflowId]);
  const { run, busy } = useAction();
  const dirty = JSON.stringify(list) !== JSON.stringify(params);
  return (
    <div className="stack">
      <div className="row">
        <p className="muted small grow">Parameters are the inputs shown when generating. They were discovered automatically (prompts, sampler, size, models, image inputs, conditioning strengths); rename, remove or expose any other literal input.</p>
        <button className="btn" onClick={() => setAdding(true)}>Expose another input…</button>
        <button className="btn" onClick={async () => { const w = await run(() => api.rediscover(workflowId), "Parameters rediscovered"); if (w) setList(w.parameters); }}>Re-discover</button>
        <button className="btn primary" disabled={!dirty || busy} onClick={async () => { if (await run(() => api.updateWorkflow(workflowId, { parameters: list }), "Parameters saved")) onSaved(); }}>Save</button>
      </div>
      <div className="card flush"><table className="table"><thead><tr><th>Label</th><th>Input</th><th>Type</th><th>Group</th><th>Default</th><th></th></tr></thead><tbody>
        {list.map((p, i) => (
          <tr key={p.key}>
            <td><input className="input" value={p.label} aria-label={`Label for ${p.key}`} onChange={(e) => setList(list.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} /></td>
            <td className="mono tiny">{p.key}<div className="muted">{p.class_type}</div></td>
            <td><span className="badge">{p.type}</span></td>
            <td className="small">{p.group}</td>
            <td className="small ellipsis" style={{ maxWidth: 260 }}>{String(p.default ?? "")}</td>
            <td><button className="btn sm ghost" onClick={() => setList(list.filter((_, j) => j !== i))}>Remove</button></td>
          </tr>
        ))}</tbody></table></div>
      {adding && (
        <Modal title="Expose an input" onClose={() => setAdding(false)} size="wide">
          <table className="table small"><tbody>{(inputs.data ?? []).filter((x) => !list.some((p) => p.key === x.key)).map((x) => (
            <tr key={x.key} className="clickable" onClick={() => {
              const t = typeof x.value === "number" ? (Number.isInteger(x.value) ? "int" : "float") : typeof x.value === "boolean" ? "bool" : "text";
              setList([...list, { key: x.key, node_id: x.node_id, input: x.input, class_type: x.class_type, label: `${x.class_type} · ${x.input}`, type: t as WorkflowParam["type"], group: "custom", default: x.value }]);
              setAdding(false);
            }}><td className="mono">{x.key}</td><td>{x.class_type}</td><td className="ellipsis" style={{ maxWidth: 380 }}>{String(x.value)}</td></tr>
          ))}</tbody></table>
        </Modal>
      )}
    </div>
  );
}
