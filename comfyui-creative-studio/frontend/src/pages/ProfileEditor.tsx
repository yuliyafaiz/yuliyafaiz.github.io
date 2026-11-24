import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Copy, Plus, Trash2, X } from "lucide-react";
import { PageHead } from "../components/Layout";
import { ReferencePicker } from "../components/references";
import { Callout, ErrorNote, Spinner, useAction, useToast } from "../components/ui";
import { api } from "../lib/api";
import { label, useAsync } from "../lib/hooks";
import type { Profile } from "../lib/types";

export function ProfileEditor() {
  const id = Number(useParams().id);
  const prof = useAsync(() => api.profile(id), [id]);
  const fields = useAsync(api.profileFields, []);
  const workflows = useAsync(() => api.workflows(), []);
  const projects = useAsync(() => api.projects("all"), []);
  const [draft, setDraft] = useState<Profile>();
  const [pickRole, setPickRole] = useState<string>();
  const [newDetail, setNewDetail] = useState("");
  const [newAttr, setNewAttr] = useState("");
  const { run, busy } = useAction();
  const toast = useToast();
  const nav = useNavigate();
  useEffect(() => { if (prof.data) setDraft(prof.data); }, [prof.data]);
  if (prof.error) return <div className="page"><ErrorNote error={prof.error} /></div>;
  if (!draft || !prof.data) return <div className="page"><Spinner /></div>;
  const p = prof.data;
  const suggested = fields.data?.fields[draft.kind] ?? [];
  const attrKeys = [...new Set([...suggested, ...Object.keys(draft.attributes)])];
  const dirty = JSON.stringify(draft) !== JSON.stringify(p);

  const save = async () => {
    const r = await run(() => api.updateProfile(id, {
      name: draft.name, description: draft.description, category: draft.category, attributes: draft.attributes,
      preserve_details: draft.preserve_details, notes: draft.notes, generation_settings: draft.generation_settings,
    }), "Profile saved");
    if (r) prof.setData(r);
  };
  const setAttr = (k: string, v: string) => {
    const a = { ...draft.attributes };
    if (v === "" && !suggested.includes(k)) delete a[k]; else a[k] = v;
    setDraft({ ...draft, attributes: a });
  };
  const roles = fields.data?.image_roles ?? ["primary", "detail"];
  const primaryRoles = draft.kind === "product" ? ["primary", "detail", "angle", "material"] : ["face", "primary", "angle", "other"];

  return (
    <div className="page">
      <PageHead crumbs={<><Link to="/references?tab=profiles">Profiles</Link><span>/</span></>}
        title={<span className="row">{p.name}<span className={`badge ${p.kind === "product" ? "accent" : "info"}`}>{p.kind} profile</span></span>}
        actions={<>
          <button className="btn danger" onClick={async () => { if (confirm("Delete this profile?")) { await run(() => api.deleteProfile(id), "Profile deleted"); nav("/references?tab=profiles"); } }}><Trash2 size={15} /></button>
          <Link className="btn" to={`/consistency?profile=${id}`}>Use in consistency config</Link>
          <button className="btn primary" disabled={!dirty || busy} onClick={save}>{dirty ? "Save changes" : "Saved"}</button>
        </>} />

      <div className="split">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card">
            <div className="card-head"><h2>Reference images</h2></div>
            <div className="stack">
              {primaryRoles.concat(roles.filter((r) => !primaryRoles.includes(r))).map((role) => {
                const imgs = p.images.filter((i) => i.role === role);
                if (!imgs.length && !primaryRoles.includes(role)) return null;
                return (
                  <div key={role}>
                    <div className="row between" style={{ marginBottom: 8 }}>
                      <span className="small" style={{ fontWeight: 600 }}>{label(role)} <span className="muted">({imgs.length})</span></span>
                      <button className="btn sm" onClick={() => setPickRole(role)}><Plus size={13} />Add</button>
                    </div>
                    {imgs.length ? <div className="gallery sm">{imgs.map((i) => (
                      <div key={i.id} className="tile contain"><img src={i.reference.thumb_url} alt={i.reference.title} />
                        <div className="tile-actions"><button className="tile-btn" aria-label="Remove image" onClick={async () => {
                          await run(() => api.removeProfileImage(id, i.id)); void prof.reload();
                        }}><X size={14} /></button></div>
                        <div className="tile-overlay tiny ellipsis">{i.reference.title}</div></div>
                    ))}</div> : <p className="muted small">No {label(role).toLowerCase()} images.{role === "primary" && draft.kind === "product" && " Use a cut-out PNG with transparent background for product-preserving workflows."}{role === "face" && " Without face images the loader falls back to primary images."}</p>}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="card stack">
            <h2>Identity</h2>
            <div className="grid-2">
              <label className="field"><span>Name</span><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
              <label className="field"><span>{draft.kind === "product" ? "Product category" : "Role / type"}</span><input className="input" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} placeholder={draft.kind === "product" ? "ring, necklace, earrings…" : "lead model"} /></label>
            </div>
            <label className="field"><span>Visual description</span><textarea className="textarea" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
          </section>

          <section className="card stack">
            <h2>{draft.kind === "product" ? "Shape & material" : "Visual attributes"}</h2>
            <div className="grid-2">{attrKeys.map((k) => (
              <label key={k} className="field"><span>{label(k)}</span><input className="input" value={draft.attributes[k] ?? ""} onChange={(e) => setAttr(k, e.target.value)} /></label>
            ))}</div>
            <form className="row" onSubmit={(e) => { e.preventDefault(); if (newAttr) { setDraft((d) => d && ({ ...d, attributes: { ...d.attributes, [newAttr.trim().toLowerCase().replace(/\s+/g, "_")]: "" } })); setNewAttr(""); } }}>
              <input className="input" style={{ maxWidth: 260 }} placeholder="Custom attribute name…" value={newAttr} onChange={(e) => setNewAttr(e.target.value)} />
              <button className="btn sm" type="submit">Add attribute</button>
            </form>
          </section>

          <section className="card stack">
            <h2>Important details to preserve</h2>
            <div className="list">{draft.preserve_details.map((d, i) => (
              <div key={i} className="list-item"><span className="grow">{d}</span>
                <button className="btn sm ghost icon" aria-label="Remove detail" onClick={() => setDraft({ ...draft, preserve_details: draft.preserve_details.filter((_, j) => j !== i) })}><X size={14} /></button></div>
            ))}</div>
            <form className="row" onSubmit={(e) => { e.preventDefault(); if (newDetail.trim()) { setDraft({ ...draft, preserve_details: [...draft.preserve_details, newDetail.trim()] }); setNewDetail(""); } }}>
              <input className="input grow" placeholder={draft.kind === "product" ? "e.g. six-prong setting, stone count, engraving" : "e.g. freckles, scar above left brow"} value={newDetail} onChange={(e) => setNewDetail(e.target.value)} />
              <button className="btn sm" type="submit"><Plus size={13} />Add</button>
            </form>
          </section>

          <section className="card stack">
            <h2>Notes & generation settings</h2>
            <label className="field"><span>Notes</span><textarea className="textarea" value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} /></label>
            <JsonField value={draft.generation_settings} onChange={(v) => setDraft({ ...draft, generation_settings: v })} />
          </section>
        </div>

        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <div className="row between"><h2>Prompt fragment</h2>
              <button className="btn sm" onClick={() => { void navigator.clipboard?.writeText(p.prompt_fragment?.positive ?? ""); toast("Copied", "ok"); }}><Copy size={13} />Copy</button></div>
            <p className="small text-2">{p.prompt_fragment?.positive || <span className="muted">Add a description and attributes.</span>}</p>
            {p.prompt_fragment?.negative && <><div className="muted tiny">Negative</div><p className="small text-2">{p.prompt_fragment.negative}</p></>}
            <Callout kind="info">The same deterministic fragment is produced inside ComfyUI by the Profile Loader nodes. Text complements image conditioning; it does not guarantee consistency by itself.</Callout>
          </section>
          <section className="card stack">
            <h2>Associated workflows</h2>
            {(workflows.data ?? []).map((w) => (
              <label key={w.id} className="check small"><input type="checkbox" checked={p.workflow_ids.includes(w.id)} onChange={async (e) => {
                const ids = e.target.checked ? [...p.workflow_ids, w.id] : p.workflow_ids.filter((x) => x !== w.id);
                const r = await run(() => api.updateProfile(id, { workflow_ids: ids })); if (r) prof.setData(r);
              }} />{w.name}</label>
            ))}
          </section>
          <section className="card stack">
            <h2>Projects</h2>
            {(projects.data ?? []).map((pr) => (
              <label key={pr.id} className="check small"><input type="checkbox" checked={p.project_ids.includes(pr.id)} onChange={async (e) => {
                const ids = e.target.checked ? [...p.project_ids, pr.id] : p.project_ids.filter((x) => x !== pr.id);
                const r = await run(() => api.updateProfile(id, { project_ids: ids })); if (r) prof.setData(r);
              }} />{pr.name}</label>
            ))}
          </section>
        </div>
      </div>
      {pickRole && <ReferencePicker multiple title={`Add ${label(pickRole).toLowerCase()} images`} categoryHint={draft.kind === "product" ? "" : ""}
        onClose={() => setPickRole(undefined)} onPick={async (refs) => {
          const role = pickRole; setPickRole(undefined);
          for (const r of refs) await run(() => api.addProfileImage(id, r.id, role));
          void prof.reload();
        }} />}
    </div>
  );
}

function JsonField({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [err, setErr] = useState("");
  return (
    <label className="field"><span>Generation settings (JSON)</span>
      <textarea className="textarea mono" rows={5} value={text} onChange={(e) => {
        setText(e.target.value);
        try { const v = JSON.parse(e.target.value || "{}"); setErr(""); onChange(v); } catch { setErr("Invalid JSON"); }
      }} />
      <span className="hint" style={err ? { color: "var(--err)" } : undefined}>{err || "Recommended values for workflows using this profile, e.g. denoise, mask expand, working size."}</span>
    </label>
  );
}
