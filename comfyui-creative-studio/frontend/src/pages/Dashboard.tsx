import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, ArrowRight, FolderKanban, Gem, Images, Sparkles, Star, Workflow } from "lucide-react";
import { PageHead } from "../components/Layout";
import { OutputLightbox } from "../components/outputs";
import { EmptyState, Progress, Spinner, StatusBadge, useAction } from "../components/ui";
import { api } from "../lib/api";
import { label, relativeTime, useAsync, bytes } from "../lib/hooks";

export function Dashboard() {
  const dash = useAsync(api.dashboard, [], 4000);
  const status = useAsync(api.comfyStatus, [], 8000);
  const { run, busy } = useAction();
  const nav = useNavigate();
  const [open, setOpen] = useState<number>();
  const d = dash.data;
  const s = status.data;

  if (!d) return <div className="page"><Spinner /></div>;
  const empty = d.stats.projects === 0;

  return (
    <div className="page">
      <PageHead title="Studio overview" sub="Projects, references, workflows and generations managed on top of your local ComfyUI."
        actions={<>
          <Link className="btn" to="/references"><Images size={15} />Add references</Link>
          <Link className="btn primary" to="/production"><Sparkles size={15} />New generation</Link>
        </>} />

      {empty && (
        <div className="card hero" style={{ marginBottom: 20 }}>
          <div className="row between wrap">
            <div className="stack tight" style={{ maxWidth: 640 }}>
              <span className="badge accent" style={{ width: "fit-content" }}>Get started</span>
              <h2 style={{ fontSize: 20 }}>Load the luxury jewelry campaign demo</h2>
              <p className="text-2">Creates a project with placeholder product, style and lighting references, a Product Profile,
                three API-format workflows and ready consistency configurations. The “pipeline check” config runs on any
                ComfyUI with the Creative Studio nodes installed — no model download needed.</p>
            </div>
            <button className="btn primary" disabled={busy} onClick={async () => {
              const p = await run(api.seedDemo, "Demo project created");
              if (p) nav(`/projects/${p.id}`);
            }}><Gem size={15} />Create demo project</button>
          </div>
        </div>
      )}

      <div className="stats card" style={{ marginBottom: 20 }}>
        {(["projects", "references", "profiles", "workflows", "jobs", "outputs"] as const).map((k) => (
          <div key={k} className="stat"><span className="stat-value">{d.stats[k] ?? 0}</span><span className="stat-label">{label(k)}</span></div>
        ))}
      </div>

      <div className="split">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card">
            <div className="card-head"><h2><Sparkles size={16} />Recent generations</h2><Link to="/production" className="btn ghost sm">Production board<ArrowRight size={14} /></Link></div>
            {d.recent_outputs.length ? (
              <div className="gallery">{d.recent_outputs.map((o) => (
                <div key={o.id} className="tile" onClick={() => setOpen(o.id)}><img src={o.thumb_url} alt={`Output ${o.id}`} />
                  <div className="tile-overlay small">#{o.id} · seed {String(o.summary?.seed ?? "—")}</div></div>
              ))}</div>
            ) : <EmptyState icon={<Sparkles size={26} />} title="No generations yet">Outputs appear here once ComfyUI reports a job as completed.</EmptyState>}
          </section>

          <section className="card">
            <div className="card-head"><h2><FolderKanban size={16} />Recent projects</h2><Link to="/projects" className="btn ghost sm">All projects<ArrowRight size={14} /></Link></div>
            {d.recent_projects.length ? (
              <div className="grid-3">{d.recent_projects.map((p) => (
                <Link key={p.id} to={`/projects/${p.id}`} className="card flush">
                  <div className="cover" style={{ aspectRatio: "16/8" }}>{p.cover_url ? <img src={p.cover_url} alt="" /> : <FolderKanban size={30} />}</div>
                  <div style={{ padding: 12 }}><div className="ellipsis" style={{ fontWeight: 600 }}>{p.name}</div>
                    <div className="muted small">{p.client || "No client"} · {relativeTime(p.updated_at)}</div></div>
                </Link>
              ))}</div>
            ) : <EmptyState title="No projects" action={<Link to="/projects" className="btn">Create a project</Link>} />}
          </section>

          <section className="card">
            <div className="card-head"><h2><Star size={16} />Favorite references</h2><Link to="/references" className="btn ghost sm">Reference Studio<ArrowRight size={14} /></Link></div>
            {d.favorite_references.length ? (
              <div className="gallery sm">{d.favorite_references.map((r) => (
                <Link key={r.id} to="/references" className="tile contain"><img src={r.thumb_url} alt={r.title} /></Link>
              ))}</div>
            ) : <p className="muted small">Star references in the Reference Studio to pin them here.</p>}
          </section>
        </div>

        <div className="stack" style={{ gap: 20 }}>
          <section className="card">
            <div className="card-head"><h2>ComfyUI</h2><span className={`badge ${s?.reachable ? "ok" : "err"}`}>{s ? (s.reachable ? "Connected" : "Offline") : "…"}</span></div>
            {s?.reachable ? (
              <dl className="kv small">
                <dt>Version</dt><dd>{s.version}</dd>
                <dt>Device</dt><dd>{s.devices?.[0]?.name} ({s.devices?.[0]?.type})</dd>
                <dt>RAM free</dt><dd>{bytes(s.ram_free)} of {bytes(s.ram_total)}</dd>
                <dt>Queue</dt><dd>{s.queue_running} running · {s.queue_pending} pending</dd>
                <dt>Live events</dt><dd>{s.websocket_connected ? "WebSocket connected" : "polling only"}</dd>
              </dl>
            ) : <p className="muted small">{s?.error ?? "Checking…"} <Link to="/settings" className="text-2"><u>Settings</u></Link></p>}
          </section>

          <section className="card">
            <div className="card-head"><h2><Activity size={16} />Active jobs</h2><span className="badge">{d.active_jobs.length}</span></div>
            {d.active_jobs.length ? <div className="list">{d.active_jobs.map((j) => (
              <Link key={j.id} to={`/production?batch=${j.batch_id}`} className="list-item clickable">
                <div className="grow stack tight"><div className="row between"><span className="ellipsis small">{j.name}</span><StatusBadge status={j.status} /></div>
                  <Progress value={j.progress.value} max={j.progress.max} indeterminate={!j.progress.max} /></div>
              </Link>
            ))}</div> : <p className="muted small">Nothing running.</p>}
          </section>

          <section className="card">
            <div className="card-head"><h2><Workflow size={16} />Workflow shortcuts</h2></div>
            {d.workflow_shortcuts.length ? <div className="list">{d.workflow_shortcuts.map((w) => (
              <Link key={w.id} to={`/production?workflow=${w.id}`} className="list-item clickable">
                <div className="grow"><div className="ellipsis small" style={{ fontWeight: 550 }}>{w.name}</div><div className="muted tiny">{label(w.category)} · {w.node_count} nodes</div></div>
                <ArrowRight size={14} className="muted" />
              </Link>
            ))}</div> : <p className="muted small">Import a workflow to create shortcuts.</p>}
          </section>

          <section className="card">
            <div className="card-head"><h2>Activity</h2></div>
            <div className="list">{d.activity.map((a) => (
              <div key={a.id} className="list-item small"><span className="grow text-2">{a.message}</span><span className="muted tiny nowrap">{relativeTime(a.created_at)}</span></div>
            ))}{!d.activity.length && <p className="muted small">No activity yet.</p>}</div>
          </section>
        </div>
      </div>
      {open && <OutputLightbox id={open} onClose={() => setOpen(undefined)} />}
    </div>
  );
}
