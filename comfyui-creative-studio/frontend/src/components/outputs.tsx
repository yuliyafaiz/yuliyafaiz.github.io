import { useState } from "react";
import { Check, CheckCircle2, Download, RotateCcw, Star } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync, formatDate, label } from "../lib/hooks";
import type { CompareResult, OutputMeta, OutputSummary } from "../lib/types";
import { Callout, Modal, Spinner, useAction } from "./ui";
import { ReferencePicker } from "./references";

export function OutputTile({ o, checked, onOpen, onToggleCheck, onChange }: {
  o: OutputSummary; checked?: boolean; onOpen: () => void; onToggleCheck?: () => void; onChange: (o: OutputSummary) => void;
}) {
  const { run } = useAction();
  const toggle = async (field: "favorite" | "selected") => {
    const r = await run(() => api.updateOutput(o.id, { [field]: !o[field] }));
    if (r) onChange(r);
  };
  return (
    <div className={`tile ${checked ? "selected" : ""}`} onClick={onOpen} data-testid="output-tile">
      <img src={o.thumb_url} alt={`Output ${o.id}`} loading="lazy" />
      {onToggleCheck && (
        <button className="tile-check" aria-label="Select for comparison" style={{ cursor: "pointer" }}
          onClick={(e) => { e.stopPropagation(); onToggleCheck(); }}>{checked && <Check size={14} />}</button>
      )}
      <div className={`tile-actions ${o.favorite || o.selected ? "show" : ""}`}>
        <button className={`tile-btn ${o.favorite ? "on" : ""}`} aria-label="Favorite" onClick={(e) => { e.stopPropagation(); void toggle("favorite"); }}>
          <Star size={14} fill={o.favorite ? "currentColor" : "none"} />
        </button>
        <button className={`tile-btn ${o.selected ? "on" : ""}`} aria-label="Select as final" onClick={(e) => { e.stopPropagation(); void toggle("selected"); }}>
          <CheckCircle2 size={14} />
        </button>
      </div>
      <div className="tile-overlay row between">
        <span>#{o.id} · job {o.job_id}</span>
        {o.selected && <span className="badge accent">Final</span>}
      </div>
    </div>
  );
}

export function MetadataPanel({ meta }: { meta: OutputMeta }) {
  const g = meta.generation;
  return (
    <div className="stack">
      <dl className="kv">
        <dt>Workflow</dt><dd>{meta.workflow?.name ?? "—"}</dd>
        <dt>Seed</dt><dd className="mono">{String(g.seed ?? "—")}</dd>
        <dt>Steps / CFG</dt><dd>{g.steps ?? "—"} / {g.cfg ?? "—"}</dd>
        <dt>Sampler</dt><dd>{g.sampler ?? "—"} · {g.scheduler ?? "—"}</dd>
        {g.denoise != null && <><dt>Denoise</dt><dd>{g.denoise}</dd></>}
        <dt>Size</dt><dd>{meta.output?.width}×{meta.output?.height}</dd>
        {g.variant && <><dt>Variant</dt><dd>{g.variant.label} — {g.variant.text}</dd></>}
        <dt>Methods</dt><dd>{g.methods?.map(label).join(", ") || "—"}</dd>
        <dt>Execution</dt><dd>{meta.comfy?.execution_seconds != null ? `${meta.comfy.execution_seconds.toFixed(2)} s` : "—"}</dd>
        <dt>Completed</dt><dd>{formatDate(meta.completed_at)}</dd>
      </dl>
      {g.prompt && <div><div className="muted small">Prompt</div><div className="small text-2">{g.prompt}</div></div>}
      {g.negative_prompt && <div><div className="muted small">Negative</div><div className="small text-2">{g.negative_prompt}</div></div>}
      {g.runtime_values_from && <div className="muted tiny">Prompt/seed recorded at runtime by node #{g.runtime_values_from} (Generation Metadata Saver).</div>}
      <div>
        <div className="muted small" style={{ marginBottom: 4 }}>Models</div>
        {g.models.length ? g.models.map((m) => (
          <div key={m.node_id + m.input} className="small"><b>{m.name}</b> <span className="muted">({m.kind})</span>
            <div className="mono tiny muted ellipsis">{m.sha256 ? `sha256 ${m.sha256}` : "hash unavailable"}</div></div>
        )) : <span className="muted small">No model inputs</span>}
      </div>
      {meta.reference_images.length > 0 && (
        <div>
          <div className="muted small" style={{ marginBottom: 4 }}>Reference images</div>
          {meta.reference_images.map((r) => (
            <div key={r.parameter} className="row small"><img className="thumb" src={`/api/references/${r.reference_id}/thumb`} alt="" />
              <div className="grow"><div className="ellipsis">{r.title}</div><div className="mono tiny muted">{r.parameter}</div></div></div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CompareMeters({ results }: { results: CompareResult[] }) {
  return (
    <div className="stack">
      {results.map((r) => (
        <div key={`${r.kind}${r.id}`} className="panel stack tight">
          <div className="row small"><img className="thumb" src={r.kind === "reference" ? `/api/references/${r.id}/thumb` : `/api/outputs/${r.id}/thumb`} alt="" />
            <b className="ellipsis">{r.kind === "reference" ? r.title : `Output #${r.id}`}</b></div>
          <Meter label="Structure (SSIM)" v={r.structural_similarity} />
          <Meter label="Colour histogram" v={r.color_histogram_correlation} />
          <Meter label="Perceptual hash" v={r.perceptual_hash_similarity} />
        </div>
      ))}
    </div>
  );
}

function Meter({ label, v }: { label: string; v: number }) {
  return (
    <div className="meter"><span className="muted">{label}</span>
      <div className="progress"><div style={{ width: `${Math.max(0, v) * 100}%` }} /></div>
      <span className="mono">{v.toFixed(2)}</span></div>
  );
}

export function OutputLightbox({ id, onClose, onChange }: { id: number; onClose: () => void; onChange?: (o: OutputSummary) => void }) {
  const out = useAsync(() => api.output(id), [id]);
  const { run, busy } = useAction();
  const nav = useNavigate();
  const [picking, setPicking] = useState(false);
  const [cmp, setCmp] = useState<{ results: CompareResult[]; note: string }>();
  const o = out.data;
  const update = async (b: Parameters<typeof api.updateOutput>[1]) => {
    const r = await run(() => api.updateOutput(id, b));
    if (r) { out.setData(r); onChange?.(r); }
  };
  return (
    <Modal title={o ? `Output #${o.id}` : "Output"} onClose={onClose} size="full">
      {!o ? <div style={{ padding: 30 }}><Spinner /></div> : (
        <div className="lightbox">
          <div className="lightbox-img"><img src={o.file_url} alt={`Output ${o.id}`} /></div>
          <div className="lightbox-side">
            <div className="row wrap">
              <button className={`btn sm ${o.favorite ? "active" : ""}`} onClick={() => update({ favorite: !o.favorite })}><Star size={14} />Favorite</button>
              <button className={`btn sm ${o.selected ? "active" : ""}`} onClick={() => update({ selected: !o.selected })}><CheckCircle2 size={14} />Final</button>
              <a className="btn sm" href={`/api/outputs/${o.id}/metadata`}><Download size={14} />Metadata</a>
              <a className="btn sm" href={o.file_url} download><Download size={14} />Image</a>
            </div>
            <div className="row">
              <span className="muted small">Rating</span>
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} className="btn ghost sm icon" aria-label={`Rate ${n}`} onClick={() => update({ rating: n === o.rating ? 0 : n })}>
                  <Star size={14} color={n <= o.rating ? "var(--accent)" : "var(--muted)"} fill={n <= o.rating ? "var(--accent)" : "none"} />
                </button>
              ))}
            </div>
            {o.meta && <MetadataPanel meta={o.meta} />}
            <div className="row wrap">
              <button className="btn sm" disabled={busy} onClick={async () => {
                const j = await run(() => api.reproduceJob(o.job_id), "Re-submitted with identical settings");
                if (j) nav(`/production?batch=${j.batch_id}`);
              }}><RotateCcw size={14} />Reproduce</button>
              <button className="btn sm" onClick={() => setPicking(true)}>Compare with references…</button>
            </div>
            {cmp && <><Callout kind="info">{cmp.note}</Callout><CompareMeters results={cmp.results} /></>}
          </div>
        </div>
      )}
      {picking && o && (
        <ReferencePicker multiple title="Compare with references" initial={o.meta?.reference_images.map((r) => r.reference_id) ?? []}
          onClose={() => setPicking(false)}
          onPick={async (refs) => {
            setPicking(false);
            const r = await run(() => api.compareOutput(o.id, { reference_ids: refs.map((x) => x.id) }));
            if (r) setCmp(r);
          }} />
      )}
    </Modal>
  );
}

/** Side-by-side comparison of 2–4 outputs with a parameter diff table. */
export function CompareView({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const outs = useAsync(() => Promise.all(ids.map((i) => api.output(i))), [ids.join(",")]);
  const rows: [string, (m: OutputMeta) => unknown][] = [
    ["Workflow", (m) => m.workflow?.name], ["Seed", (m) => m.generation.seed], ["Steps", (m) => m.generation.steps],
    ["CFG", (m) => m.generation.cfg], ["Sampler", (m) => m.generation.sampler], ["Scheduler", (m) => m.generation.scheduler],
    ["Denoise", (m) => m.generation.denoise], ["Variant", (m) => m.generation.variant?.label],
    ["Size", (m) => `${m.output?.width}×${m.output?.height}`], ["Prompt", (m) => m.generation.prompt],
    ["Models", (m) => m.generation.models.map((x) => x.name).join(", ")],
  ];
  const paramKeys = [...new Set((outs.data ?? []).flatMap((o) => Object.keys(o.meta?.parameter_values ?? {})))].sort();
  return (
    <Modal title={`Compare ${ids.length} outputs`} onClose={onClose} size="full">
      {!outs.data ? <div style={{ padding: 30 }}><Spinner /></div> : (
        <div className="modal-body stack">
          <div className="compare-grid" style={{ gridTemplateColumns: `repeat(${ids.length}, minmax(0, 1fr))` }}>
            {outs.data.map((o) => <div key={o.id}><img src={o.file_url} alt={`Output ${o.id}`} /><div className="small muted" style={{ marginTop: 4 }}>#{o.id} · job {o.job_id}</div></div>)}
          </div>
          <table className="table small" data-testid="compare-table">
            <tbody>
              {rows.map(([name, f]) => {
                const vals = outs.data!.map((o) => (o.meta ? f(o.meta) : undefined));
                const differs = new Set(vals.map((v) => JSON.stringify(v))).size > 1;
                return (
                  <tr key={name} className={differs ? "diff" : ""}>
                    <td className="muted nowrap">{name}{differs && " ●"}</td>
                    {vals.map((v, i) => <td key={i} style={{ maxWidth: 320 }}>{v == null || v === "" ? "—" : String(v)}</td>)}
                  </tr>
                );
              })}
              {paramKeys.map((k) => {
                const vals = outs.data!.map((o) => o.meta?.parameter_values?.[k]);
                const differs = new Set(vals.map((v) => JSON.stringify(v))).size > 1;
                if (!differs) return null;
                return (
                  <tr key={k} className="diff"><td className="mono tiny nowrap">{k} ●</td>
                    {vals.map((v, i) => <td key={i} className="small ellipsis" style={{ maxWidth: 320 }}>{v == null ? "—" : String(v).slice(0, 200)}</td>)}</tr>
                );
              })}
            </tbody>
          </table>
          <div className="muted tiny">● rows differ between the selected outputs.</div>
        </div>
      )}
    </Modal>
  );
}
