import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Archive, ArchiveRestore, FolderKanban, Plus, Sparkles, Trash2, UserRound, Package, Workflow as WfIcon } from "lucide-react";
import { PageHead } from "../components/Layout";
import { OutputLightbox, OutputTile } from "../components/outputs";
import { ReferencePicker, ReferenceTile, UploadDrop } from "../components/references";
import { EmptyState, ErrorNote, Modal, Segmented, Spinner, StatusBadge, Tabs, useAction } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, label, relativeTime, useAsync } from "../lib/hooks";

export function Projects() {
  const [status, setStatus] = useState<"active" | "archived">("active");
  const projects = useAsync(() => api.projects(status), [status]);
  const [creating, setCreating] = useState(false);
  return (
    <div className="page">
      <PageHead title="Projects" sub="Organise production by project and campaign. References and profiles are reusable across projects."
        actions={<>
          <Segmented value={status} onChange={setStatus} options={[{ value: "active", label: "Active" }, { value: "archived", label: "Archived" }]} />
          <button className="btn primary" onClick={() => setCreating(true)}><Plus size={15} />New project</button>
        </>} />
      <ErrorNote error={projects.error} />
      {!projects.data ? <Spinner /> : projects.data.length ? (
        <div className="grid-3">
          {projects.data.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="card flush" data-testid="project-card">
              <div className="cover">{p.cover_url ? <img src={p.cover_url} alt="" /> : <FolderKanban size={36} />}</div>
              <div style={{ padding: 16 }} className="stack tight">
                <div className="row between"><h3 className="ellipsis">{p.name}</h3>{p.template_key && <span className="badge">{label(p.template_key)}</span>}</div>
                <div className="muted small ellipsis">{p.client || "No client"} · updated {relativeTime(p.updated_at)}</div>
                <div className="row wrap small text-2" style={{ gap: 14, marginTop: 4 }}>
                  <span>{p.campaigns.length} campaigns</span><span>{p.counts.references ?? 0} refs</span>
                  <span>{p.counts.outputs ?? 0} outputs</span><span>{p.counts.selected ?? 0} finals</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState icon={<FolderKanban size={30} />} title={status === "active" ? "No active projects" : "No archived projects"}
          action={status === "active" ? <button className="btn primary" onClick={() => setCreating(true)}><Plus size={15} />New project</button> : undefined}>
          A project groups campaigns, references, profiles, workflows and generations.
        </EmptyState>
      )}
      {creating && <NewProjectModal onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const tpls = useAsync(api.templates, []);
  const [form, setForm] = useState({ name: "", client: "", description: "", template_key: "jewelry_campaign" });
  const { run, busy } = useAction();
  const nav = useNavigate();
  const tpl = tpls.data?.find((t) => t.key === form.template_key);
  const submit = async () => {
    const p = await run(() => api.createProject(form), "Project created");
    if (p) nav(`/projects/${p.id}`);
  };
  return (
    <Modal title="New project" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!form.name || busy} onClick={submit}>Create project</button></>}>
      <div className="stack">
        <label className="field"><span>Name</span><input className="input" autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Luxury Jewelry Campaign" /></label>
        <label className="field"><span>Client / brand</span><input className="input" value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} /></label>
        <label className="field"><span>Template</span>
          <select className="select" value={form.template_key} onChange={(e) => setForm({ ...form, template_key: e.target.value })}>
            {(tpls.data ?? []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          {tpl && <span className="hint">{tpl.description} {tpl.campaigns.length > 0 && <>Creates campaigns: {tpl.campaigns.join(", ")}; collections: {tpl.collections.join(", ")}.</>}</span>}
        </label>
        <label className="field"><span>Description</span><textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Defaults to the template description" /></label>
      </div>
    </Modal>
  );
}

type Tab = "overview" | "references" | "profiles" | "workflows" | "outputs";

export function ProjectDetailPage() {
  const id = Number(useParams().id);
  const project = useAsync(() => api.project(id), [id]);
  const activity = useAsync(() => api.projectActivity(id), [id]);
  const [tab, setTab] = useState<Tab>("overview");
  const { run, busy } = useAction();
  const nav = useNavigate();
  const [editing, setEditing] = useState(false);
  const p = project.data;
  if (project.error) return <div className="page"><ErrorNote error={project.error} /></div>;
  if (!p) return <div className="page"><Spinner /></div>;
  const reload = () => { void project.reload(); void activity.reload(); };

  return (
    <div className="page">
      <PageHead crumbs={<><Link to="/projects">Projects</Link><span>/</span></>}
        title={<span className="row">{p.name}{p.status === "archived" && <span className="badge warn">Archived</span>}</span>}
        sub={p.description}
        actions={<>
          <button className="btn" onClick={() => setEditing(true)}>Edit</button>
          {p.status === "active" ? (
            <button className="btn" disabled={busy} onClick={async () => { await run(() => api.archiveProject(id), "Project archived"); reload(); }}><Archive size={15} />Archive</button>
          ) : (<>
            <button className="btn" onClick={async () => { await run(() => api.restoreProject(id), "Project restored"); reload(); }}><ArchiveRestore size={15} />Restore</button>
            <button className="btn danger" onClick={async () => { if (confirm("Delete this archived project permanently? References and profiles are kept.")) { await run(() => api.deleteProject(id), "Project deleted"); nav("/projects"); } }}><Trash2 size={15} />Delete</button>
          </>)}
          <Link className="btn primary" to={`/production?project=${id}`}><Sparkles size={15} />Generate</Link>
        </>} />

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: "overview", label: "Overview" },
        { value: "references", label: `References (${p.references.length})` },
        { value: "profiles", label: `Profiles (${p.profiles.length})` },
        { value: "workflows", label: `Workflows (${p.workflows.length})` },
        { value: "outputs", label: `Outputs (${p.counts.outputs ?? 0})` },
      ]} />

      {tab === "overview" && (
        <div className="split">
          <div className="stack" style={{ gap: 20 }}>
            <section className="card">
              <div className="card-head"><h2>Campaigns</h2><AddCampaign projectId={id} onDone={reload} /></div>
              {p.campaigns.length ? <table className="table"><thead><tr><th>Name</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody>
                {p.campaigns.map((c) => (
                  <tr key={c.id}><td>{c.name}</td><td><span className={`badge ${c.status === "active" ? "ok" : ""}`}>{c.status}</span></td>
                    <td className="muted small">{formatDate(c.created_at)}</td>
                    <td><Link className="btn sm" to={`/production?project=${id}&campaign=${c.id}`}>Generate</Link></td></tr>
                ))}</tbody></table> : <p className="muted small">No campaigns yet.</p>}
            </section>
            <section className="card">
              <div className="card-head"><h2>Recent jobs</h2><Link to={`/production?project=${id}`} className="btn ghost sm">Production board</Link></div>
              <RecentJobs projectId={id} />
            </section>
          </div>
          <div className="stack" style={{ gap: 20 }}>
            <section className="card">
              <h2 style={{ marginBottom: 12 }}>Details</h2>
              <dl className="kv small">
                <dt>Client</dt><dd>{p.client || "—"}</dd>
                <dt>Template</dt><dd>{p.template_key ? label(p.template_key) : "—"}</dd>
                <dt>Created</dt><dd>{formatDate(p.created_at)}</dd>
                <dt>Updated</dt><dd>{formatDate(p.updated_at)}</dd>
                <dt>Jobs</dt><dd>{p.counts.jobs ?? 0}</dd>
                <dt>Final selects</dt><dd>{p.counts.selected ?? 0}</dd>
                {Object.entries(p.meta).map(([k, v]) => <Fragment key={k}><dt>{label(k)}</dt><dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd></Fragment>)}
              </dl>
            </section>
            <section className="card">
              <h2 style={{ marginBottom: 12 }}>History</h2>
              <div className="list">{(activity.data ?? []).slice(0, 25).map((a) => (
                <div key={a.id} className="list-item small"><span className="grow text-2">{a.message}</span><span className="muted tiny nowrap">{relativeTime(a.created_at)}</span></div>
              ))}</div>
            </section>
          </div>
        </div>
      )}

      {tab === "references" && <ProjectReferences projectId={id} refs={p.references} onChange={reload} />}

      {tab === "profiles" && (
        p.profiles.length ? <div className="grid-3">{p.profiles.map((pr) => (
          <Link key={pr.id} to={`/references/profiles/${pr.id}`} className="card flush">
            <div className="cover">{pr.images[0] ? <img src={pr.images[0].reference.thumb_url} alt="" /> : pr.kind === "product" ? <Package size={30} /> : <UserRound size={30} />}</div>
            <div style={{ padding: 14 }}><div className="row between"><b>{pr.name}</b><span className="badge">{pr.kind}</span></div>
              <div className="muted small ellipsis">{pr.description}</div></div>
          </Link>
        ))}</div> : <EmptyState title="No profiles in this project" action={<Link className="btn" to="/references?tab=profiles">Open profiles</Link>}>Create Product or Character profiles in the Reference Studio and link them to this project.</EmptyState>
      )}

      {tab === "workflows" && (
        p.workflows.length ? <div className="card flush"><table className="table"><thead><tr><th>Workflow</th><th>Category</th><th>Format</th><th>Nodes</th><th></th></tr></thead><tbody>
          {p.workflows.map((w) => (
            <tr key={w.id} className="clickable" onClick={() => nav(`/workflows/${w.id}`)}>
              <td><div className="row"><WfIcon size={15} className="muted" /><b>{w.name}</b></div></td><td>{label(w.category)}</td>
              <td><span className={`badge ${w.executable ? "ok" : "warn"}`}>{w.executable ? "Executable" : "Needs API format"}</span></td>
              <td>{w.node_count}</td><td><Link className="btn sm" onClick={(e) => e.stopPropagation()} to={`/production?project=${id}&workflow=${w.id}`}>Run</Link></td></tr>
          ))}</tbody></table></div> : <EmptyState title="No workflows assigned" action={<Link className="btn" to="/workflows">Import a workflow</Link>} />
      )}

      {tab === "outputs" && <ProjectOutputs projectId={id} />}
      {editing && <EditProject p={p} onClose={() => setEditing(false)} onDone={() => { setEditing(false); reload(); }} />}
    </div>
  );
}

function AddCampaign({ projectId, onDone }: { projectId: number; onDone: () => void }) {
  const [name, setName] = useState("");
  const { run } = useAction();
  return (
    <form className="row" onSubmit={async (e) => { e.preventDefault(); if (!name) return; await run(() => api.addCampaign(projectId, name), "Campaign added"); setName(""); onDone(); }}>
      <input className="input" style={{ width: 220, height: 30 }} placeholder="New campaign…" value={name} onChange={(e) => setName(e.target.value)} />
      <button className="btn sm" type="submit" disabled={!name}><Plus size={14} />Add</button>
    </form>
  );
}

function EditProject({ p, onClose, onDone }: { p: { id: number; name: string; client: string; description: string }; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: p.name, client: p.client, description: p.description });
  const { run, busy } = useAction();
  return (
    <Modal title="Edit project" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={busy || !f.name} onClick={async () => { if (await run(() => api.updateProject(p.id, f), "Saved")) onDone(); }}>Save</button></>}>
      <div className="stack">
        <label className="field"><span>Name</span><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label className="field"><span>Client</span><input className="input" value={f.client} onChange={(e) => setF({ ...f, client: e.target.value })} /></label>
        <label className="field"><span>Description</span><textarea className="textarea" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
      </div>
    </Modal>
  );
}

function RecentJobs({ projectId }: { projectId: number }) {
  const jobs = useAsync(() => api.jobs({ project_id: projectId, limit: 8 }), [projectId], 4000);
  if (!jobs.data) return <Spinner />;
  if (!jobs.data.length) return <p className="muted small">No jobs yet.</p>;
  return (
    <div className="list">{jobs.data.map((j) => (
      <Link key={j.id} to={`/production?batch=${j.batch_id}`} className="list-item clickable">
        {j.outputs[0] ? <img className="thumb" src={j.outputs[0].thumb_url} alt="" /> : <div className="thumb" />}
        <div className="grow"><div className="ellipsis small">{j.name}</div><div className="muted tiny">#{j.id} · {relativeTime(j.created_at)} · {j.outputs.length} outputs</div></div>
        <StatusBadge status={j.status} />
      </Link>
    ))}</div>
  );
}

function ProjectReferences({ projectId, refs, onChange }: { projectId: number; refs: import("../lib/types").Reference[]; onChange: () => void }) {
  const [category, setCategory] = useState("product");
  const [picking, setPicking] = useState(false);
  const cats = useAsync(api.categories, []);
  const { run } = useAction();
  return (
    <div className="stack">
      <div className="row wrap">
        <select className="select" style={{ width: 180 }} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Upload category">
          {(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <div className="grow"><UploadDrop compact category={category} projectId={projectId} onDone={onChange} /></div>
        <button className="btn" onClick={() => setPicking(true)}>Add from library…</button>
      </div>
      {refs.length ? <div className="gallery">{refs.map((r) => (
        <div key={r.id} style={{ position: "relative" }}>
          <ReferenceTile r={r} />
          <button className="btn sm ghost" style={{ marginTop: 4 }} onClick={async () => { await run(() => api.detachReference(projectId, r.id)); onChange(); }}>Remove from project</button>
        </div>
      ))}</div> : <EmptyState title="No references yet">Upload product photos, style and lighting references, or reuse existing ones from the library.</EmptyState>}
      {picking && <ReferencePicker multiple title="Add references to project" initial={refs.map((r) => r.id)} onClose={() => setPicking(false)}
        onPick={async (sel) => { setPicking(false); await run(() => api.attachReferences(projectId, sel.map((r) => r.id)), "References added"); onChange(); }} />}
    </div>
  );
}

function ProjectOutputs({ projectId }: { projectId: number }) {
  const [filter, setFilter] = useState<"all" | "selected" | "favorite">("all");
  const outs = useAsync(() => api.outputs({ project_id: projectId, selected: filter === "selected" ? true : undefined, favorite: filter === "favorite" ? true : undefined }), [projectId, filter]);
  const [open, setOpen] = useState<number>();
  return (
    <div className="stack">
      <Segmented value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "favorite", label: "Favorites" }, { value: "selected", label: "Final selects" }]} />
      {outs.data?.length ? <div className="gallery lg">{outs.data.map((o) => (
        <OutputTile key={o.id} o={o} onOpen={() => setOpen(o.id)} onChange={() => void outs.reload()} />
      ))}</div> : <EmptyState title="No outputs">Generated images for this project appear here.</EmptyState>}
      {open && <OutputLightbox id={open} onClose={() => setOpen(undefined)} onChange={() => void outs.reload()} />}
    </div>
  );
}
