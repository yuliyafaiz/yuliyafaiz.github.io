import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FolderPlus, Images, Package, Plus, Search, Star, Trash2, UserRound, X } from "lucide-react";
import { PageHead } from "../components/Layout";
import { ReferencePicker, ReferenceTile, UploadDrop } from "../components/references";
import { EmptyState, Modal, Spinner, Swatches, Tabs, TagEditor, useAction } from "../components/ui";
import { api } from "../lib/api";
import { formatDate, label, useAsync } from "../lib/hooks";
import type { Collection, Reference } from "../lib/types";

type Tab = "library" | "collections" | "profiles";

export function ReferenceStudio() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "library";
  return (
    <div className="page">
      <PageHead title="Reference Studio" sub="Your visual library: products, characters, styles, lighting and compositions — organised once, reused across projects and workflows." />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t })} tabs={[
        { value: "library", label: "Library" }, { value: "collections", label: "Collections" }, { value: "profiles", label: "Profiles" },
      ]} />
      {tab === "library" && <Library />}
      {tab === "collections" && <Collections />}
      {tab === "profiles" && <Profiles />}
    </div>
  );
}

function Library() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [uploadCat, setUploadCat] = useState("product");
  const [openId, setOpenId] = useState<number>();
  const refs = useAsync(() => api.references({ q, category, tag, favorite: favorite || undefined }), [q, category, tag, favorite]);
  const all = useAsync(() => api.references(), []);
  const cats = useAsync(api.categories, []);
  const tags = useAsync(api.tags, []);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of all.data ?? []) c[r.category] = (c[r.category] ?? 0) + 1;
    return c;
  }, [all.data]);
  const { run } = useAction();
  const reloadAll = () => { void refs.reload(); void all.reload(); void tags.reload(); };
  const toggleFav = async (r: Reference) => { await run(() => api.updateReference(r.id, { favorite: !r.favorite })); reloadAll(); };

  return (
    <div className="rail">
      <aside className="stack tight">
        <button className={`facet ${!category && !favorite ? "on" : ""}`} onClick={() => { setCategory(""); setFavorite(false); }}>All references<span className="count">{all.data?.length ?? 0}</span></button>
        <button className={`facet ${favorite ? "on" : ""}`} onClick={() => setFavorite(!favorite)}><span className="row" style={{ gap: 6 }}><Star size={13} />Favorites</span></button>
        <div className="nav-section" style={{ padding: "12px 10px 4px" }}>Categories</div>
        {(cats.data ?? []).map((c) => (
          <button key={c} className={`facet ${category === c ? "on" : ""}`} onClick={() => setCategory(category === c ? "" : c)}>{label(c)}<span className="count">{counts[c] ?? 0}</span></button>
        ))}
        {!!tags.data?.length && <>
          <div className="nav-section" style={{ padding: "12px 10px 4px" }}>Tags</div>
          <div className="row wrap" style={{ gap: 5, padding: "0 6px" }}>
            {tags.data.slice(0, 30).map((t) => (
              <button key={t.tag} className={`tag`} style={{ cursor: "pointer", border: tag === t.tag ? "1px solid var(--accent)" : "1px solid transparent" }} onClick={() => setTag(tag === t.tag ? "" : t.tag)}>{t.tag} <span className="muted">{t.count}</span></button>
            ))}
          </div>
        </>}
      </aside>
      <div className="stack">
        <div className="row wrap">
          <div className="search grow" style={{ minWidth: 220 }}><Search size={15} /><input className="input" placeholder="Search title, filename, description…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {tag && <span className="tag">#{tag}<button onClick={() => setTag("")} aria-label="Clear tag"><X size={11} /></button></span>}
        </div>
        <div className="row">
          <select className="select" style={{ width: 170 }} value={uploadCat} onChange={(e) => setUploadCat(e.target.value)} aria-label="Upload category">
            {(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <div className="grow"><UploadDrop compact category={uploadCat} onDone={reloadAll} /></div>
        </div>
        {refs.loading && !refs.data ? <Spinner /> : refs.data?.length ? (
          <div className="gallery">{refs.data.map((r) => <ReferenceTile key={r.id} r={r} onClick={() => setOpenId(r.id)} onFavorite={() => toggleFav(r)} />)}</div>
        ) : <EmptyState icon={<Images size={30} />} title="No references match">Upload images above, or clear filters.</EmptyState>}
      </div>
      {openId && <ReferenceDrawer id={openId} onClose={() => setOpenId(undefined)} onChange={reloadAll} />}
    </div>
  );
}

function ReferenceDrawer({ id, onClose, onChange }: { id: number; onClose: () => void; onChange: () => void }) {
  const ref = useAsync(() => api.reference(id), [id]);
  const cats = useAsync(api.categories, []);
  const collections = useAsync(() => api.collections(), []);
  const [draft, setDraft] = useState<Partial<Reference>>({});
  const { run, busy } = useAction();
  useEffect(() => { if (ref.data) setDraft({ title: ref.data.title, category: ref.data.category, tags: ref.data.tags, description: ref.data.description }); }, [ref.data]);
  const r = ref.data;
  const save = async () => { const x = await run(() => api.updateReference(id, draft), "Reference saved"); if (x) { ref.setData(x); onChange(); } };
  return (
    <div className="drawer" role="dialog" aria-label="Reference details">
      <div className="modal-head"><h2>Reference</h2><button className="btn ghost icon" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
      {!r ? <div className="modal-body"><Spinner /></div> : (
        <div className="modal-body stack">
          <a href={r.file_url} target="_blank" rel="noreferrer" className="tile contain" style={{ aspectRatio: "4/3" }}><img src={r.file_url} alt={r.title} /></a>
          <div className="row between small"><span className="muted">{r.width}×{r.height} · {r.mime.split("/")[1]}{r.has_alpha ? " · alpha" : ""}</span><Swatches colors={r.palette} /></div>
          <label className="field"><span>Title</span><input className="input" value={draft.title ?? ""} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
          <label className="field"><span>Category</span>
            <select className="select" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
              {(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </select></label>
          <div className="field"><span>Tags</span><TagEditor tags={draft.tags ?? []} onChange={(tags) => setDraft({ ...draft, tags })} /></div>
          <label className="field"><span>Description</span><textarea className="textarea" value={draft.description ?? ""} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
          <div className="row"><button className="btn primary" disabled={busy} onClick={save}>Save</button>
            <button className={`btn ${r.favorite ? "active" : ""}`} onClick={async () => { const x = await run(() => api.updateReference(id, { favorite: !r.favorite })); if (x) { ref.setData(x); onChange(); } }}><Star size={14} />{r.favorite ? "Favorited" : "Favorite"}</button>
            <button className="btn danger right" onClick={async () => { if (confirm("Delete this reference? It will be removed from profiles and collections.")) { await run(() => api.deleteReference(id), "Deleted"); onChange(); onClose(); } }}><Trash2 size={14} /></button></div>
          <div className="sep" />
          <div className="field"><span>Add to collection</span>
            <div className="row wrap">{(collections.data ?? []).map((c) => (
              <button key={c.id} className={`btn sm ${c.reference_ids.includes(id) ? "active" : ""}`} onClick={async () => {
                await run(async () => { if (c.reference_ids.includes(id)) await api.removeFromCollection(c.id, id); else await api.addToCollection(c.id, [id]); });
                void collections.reload();
              }}>{c.name}</button>
            ))}{!collections.data?.length && <span className="muted small">No collections yet.</span>}</div></div>
          <dl className="kv small"><dt>File</dt><dd className="ellipsis">{r.original_name}</dd><dt>SHA-256</dt><dd className="mono tiny">{r.sha256.slice(0, 24)}…</dd>
            <dt>Added</dt><dd>{formatDate(r.created_at)}</dd><dt>Projects</dt><dd>{r.project_ids.length || "none"}</dd></dl>
        </div>
      )}
    </div>
  );
}

function Collections() {
  const cols = useAsync(() => api.collections(), []);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<Collection>();
  return (
    <div className="stack">
      <div className="row"><button className="btn primary" onClick={() => setCreating(true)}><FolderPlus size={15} />New collection</button></div>
      {cols.data?.length ? <div className="grid-3">{cols.data.map((c) => (
        <button key={c.id} className="card flush" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => setOpen(c)}>
          <div className="mosaic">{[0, 1, 2, 3].map((i) => c.cover_urls[i] ? <img key={i} src={c.cover_urls[i]} alt="" /> : <div key={i} className="empty" />)}</div>
          <div style={{ padding: 14 }}><b>{c.name}</b><div className="muted small">{c.count} references</div></div>
        </button>
      ))}</div> : <EmptyState title="No collections">Group references into reusable boards, e.g. “Winter lighting” or “Product originals”.</EmptyState>}
      {creating && <NewCollection onClose={() => setCreating(false)} onDone={() => { setCreating(false); void cols.reload(); }} />}
      {open && <CollectionView c={open} onClose={() => { setOpen(undefined); void cols.reload(); }} />}
    </div>
  );
}

function NewCollection({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const { run } = useAction();
  return (
    <Modal title="New collection" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={!name} onClick={async () => { if (await run(() => api.createCollection({ name }), "Collection created")) onDone(); }}>Create</button></>}>
      <label className="field"><span>Name</span><input className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} /></label>
    </Modal>
  );
}

function CollectionView({ c, onClose }: { c: Collection; onClose: () => void }) {
  const refs = useAsync(() => api.references({ collection_id: c.id }), [c.id]);
  const [picking, setPicking] = useState(false);
  const { run } = useAction();
  return (
    <Modal title={c.name} onClose={onClose} size="wide" footer={<>
      <button className="btn danger" style={{ marginRight: "auto" }} onClick={async () => { if (confirm("Delete collection? References are kept.")) { await run(() => api.deleteCollection(c.id)); onClose(); } }}>Delete collection</button>
      <UploadDrop compact category="style" collectionId={c.id} onDone={() => void refs.reload()} />
      <button className="btn" onClick={() => setPicking(true)}><Plus size={14} />Add from library</button></>}>
      {refs.data?.length ? <div className="gallery sm">{refs.data.map((r) => (
        <div key={r.id} className="stack tight"><ReferenceTile r={r} compact />
          <button className="btn sm ghost" onClick={async () => { await run(() => api.removeFromCollection(c.id, r.id)); void refs.reload(); }}>Remove</button></div>
      ))}</div> : <EmptyState title="Empty collection" />}
      {picking && <ReferencePicker multiple onClose={() => setPicking(false)} onPick={async (sel) => { setPicking(false); await run(() => api.addToCollection(c.id, sel.map((r) => r.id))); void refs.reload(); }} />}
    </Modal>
  );
}

function Profiles() {
  const profiles = useAsync(() => api.profiles(), []);
  const [creating, setCreating] = useState<"product" | "character">();
  return (
    <div className="stack">
      <div className="row">
        <button className="btn primary" onClick={() => setCreating("product")}><Package size={15} />New product profile</button>
        <button className="btn" onClick={() => setCreating("character")}><UserRound size={15} />New character profile</button>
      </div>
      <p className="muted small" style={{ maxWidth: 760 }}>Profiles bundle reference images, descriptive attributes and details to preserve. They feed workflows through image bindings,
        prompt fragments and the Creative Studio profile-loader nodes. Metadata alone does not guarantee visual consistency — that depends on the model, conditioning method and workflow.</p>
      {profiles.data?.length ? <div className="grid-3">{profiles.data.map((p) => (
        <Link key={p.id} to={`/references/profiles/${p.id}`} className="card flush" data-testid="profile-card">
          <div className="cover">{p.images[0] ? <img src={p.images[0].reference.thumb_url} alt="" /> : p.kind === "product" ? <Package size={30} /> : <UserRound size={30} />}</div>
          <div style={{ padding: 14 }} className="stack tight">
            <div className="row between"><b className="ellipsis">{p.name}</b><span className={`badge ${p.kind === "product" ? "accent" : "info"}`}>{p.kind}</span></div>
            <div className="muted small ellipsis">{p.description || "No description"}</div>
            <div className="small text-2">{p.images.length} images · {p.preserve_details.length} details to preserve · {p.workflow_ids.length} workflows</div>
          </div>
        </Link>
      ))}</div> : <EmptyState title="No profiles yet">Create a Product Profile for each hero product, or a Character Profile for recurring talent.</EmptyState>}
      {creating && <NewProfile kind={creating} onClose={() => setCreating(undefined)} />}
    </div>
  );
}

function NewProfile({ kind, onClose }: { kind: "product" | "character"; onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const projects = useAsync(() => api.projects(), []);
  const [projectId, setProjectId] = useState<number>();
  const { run } = useAction();
  const nav = useNavigate();
  return (
    <Modal title={`New ${kind} profile`} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={!name} onClick={async () => {
        const p = await run(() => api.createProfile({ kind, name, description, project_ids: projectId ? [projectId] : [] }), "Profile created");
        if (p) nav(`/references/profiles/${p.id}`);
      }}>Create</button></>}>
      <div className="stack">
        <label className="field"><span>Name</span><input className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={kind === "product" ? "Aurora Solitaire Ring" : "Model — Mila"} /></label>
        <label className="field"><span>Description</span><textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <label className="field"><span>Project (optional)</span>
          <select className="select" value={projectId ?? ""} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)}>
            <option value="">None</option>{(projects.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select></label>
      </div>
    </Modal>
  );
}
