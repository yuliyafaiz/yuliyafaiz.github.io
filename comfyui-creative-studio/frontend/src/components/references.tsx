import { useState, type DragEvent } from "react";
import { Check, ImagePlus, Search, Star, Upload } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, label } from "../lib/hooks";
import type { Reference } from "../lib/types";
import { EmptyState, Modal, Spinner, useAction } from "./ui";

export function ReferenceTile({ r, selected, onClick, onFavorite, compact }: {
  r: Reference; selected?: boolean; onClick?: () => void; onFavorite?: () => void; compact?: boolean;
}) {
  return (
    <div className={`tile contain ${selected ? "selected" : ""}`} onClick={onClick} data-testid="reference-tile">
      <img src={r.thumb_url} alt={r.title} loading="lazy" />
      {selected && <div className="tile-check"><Check size={14} /></div>}
      {onFavorite && (
        <div className={`tile-actions ${r.favorite ? "show" : ""}`}>
          <button className={`tile-btn ${r.favorite ? "on" : ""}`} aria-label="Favorite"
            onClick={(e) => { e.stopPropagation(); onFavorite(); }}>
            <Star size={14} fill={r.favorite ? "currentColor" : "none"} />
          </button>
        </div>
      )}
      {!compact && (
        <div className="tile-overlay">
          <div className="ellipsis" style={{ fontWeight: 550 }}>{r.title}</div>
          <div className="muted tiny">{label(r.category)} · {r.width}×{r.height}</div>
        </div>
      )}
    </div>
  );
}

/** Modal to pick one or more references from the library (with category filter + search). */
export function ReferencePicker({ title = "Choose reference", multiple, initial = [], categoryHint, onPick, onClose }: {
  title?: string; multiple?: boolean; initial?: number[]; categoryHint?: string;
  onPick: (refs: Reference[]) => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState(categoryHint ?? "");
  const [picked, setPicked] = useState<number[]>(initial);
  const refs = useAsync(() => api.references({ q, category }), [q, category]);
  const cats = useAsync(api.categories, []);
  const toggle = (r: Reference) => {
    if (!multiple) { onPick([r]); return; }
    setPicked((p) => (p.includes(r.id) ? p.filter((x) => x !== r.id) : [...p, r.id]));
  };
  return (
    <Modal title={title} onClose={onClose} size="wide"
      footer={multiple ? (
        <>
          <span className="muted small right">{picked.length} selected</span>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={() => onPick((refs.data ?? []).filter((r) => picked.includes(r.id)))}>Use selection</button>
        </>
      ) : undefined}>
      <div className="row" style={{ marginBottom: 14 }}>
        <div className="search grow"><Search size={15} /><input className="input" placeholder="Search references…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select className="select" style={{ width: 180 }} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {(cats.data ?? []).map((c) => <option key={c} value={c}>{label(c)}</option>)}
        </select>
      </div>
      {refs.loading && !refs.data ? <Spinner /> : refs.data?.length ? (
        <div className="gallery sm">
          {refs.data.map((r) => <ReferenceTile key={r.id} r={r} compact selected={picked.includes(r.id)} onClick={() => toggle(r)} />)}
        </div>
      ) : <EmptyState icon={<ImagePlus size={28} />} title="No references found">Upload images in the Reference Studio first.</EmptyState>}
    </Modal>
  );
}

/** Drag & drop / click uploader. */
export function UploadDrop({ category, projectId, collectionId, onDone, compact }: {
  category: string; projectId?: number; collectionId?: number; onDone: (r: Reference[]) => void; compact?: boolean;
}) {
  const [over, setOver] = useState(false);
  const { run, busy } = useAction();
  const upload = async (files: File[]) => {
    if (!files.length) return;
    const r = await run(() => api.uploadReferences(files, { category, project_id: projectId, collection_id: collectionId }),
      `${files.length} reference${files.length > 1 ? "s" : ""} uploaded`);
    if (r) onDone(r);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void upload([...e.dataTransfer.files].filter((f) => f.type.startsWith("image/")));
  };
  return (
    <label className={`dropzone ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)} onDrop={onDrop} style={compact ? { padding: 12 } : undefined}>
      <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden data-testid="upload-input"
        onChange={(e) => void upload([...(e.target.files ?? [])])} />
      <div className="row" style={{ justifyContent: "center" }}>
        {busy ? <Spinner /> : <Upload size={16} />}
        <span>{busy ? "Uploading…" : <>Drop images or <u>browse</u> · stored as <b>{label(category)}</b></>}</span>
      </div>
      {!compact && <div className="tiny" style={{ marginTop: 6 }}>PNG, JPEG or WEBP up to 50 MB. Use PNG with transparency for product cut-outs.</div>}
    </label>
  );
}
