import { useState } from "react";
import { Dices, ImagePlus, X } from "lucide-react";
import type { Reference, WorkflowParam } from "../lib/types";
import { label } from "../lib/hooks";
import { ReferencePicker } from "./references";

/** Editable control for one workflow parameter.
 * ``value`` undefined = untouched (show workflow default); "" = cleared while editing (backend uses the default). */
export function ParamField({ p, value, onChange }: { p: WorkflowParam; value: unknown; onChange: (v: unknown) => void }) {
  const v = value ?? p.default;
  const id = `param-${p.key}`;
  const common = { id, "aria-label": p.label };
  let control;
  if (p.type === "text") {
    const long = String(v ?? "").length > 60 || p.group === "prompt";
    control = long ? (
      <textarea {...common} className="textarea" value={String(v ?? "")} onChange={(e) => onChange(e.target.value)} rows={3} />
    ) : (
      <input {...common} className="input" value={String(v ?? "")} onChange={(e) => onChange(e.target.value)} />
    );
  } else if (p.type === "choice" && p.choices?.length) {
    control = (
      <select {...common} className="select" value={String(v ?? "")} onChange={(e) => onChange(e.target.value)}>
        {!p.choices.map(String).includes(String(v)) && <option value={String(v)}>{String(v)} (not on server)</option>}
        {p.choices.map((c) => <option key={String(c)} value={String(c)}>{String(c)}</option>)}
      </select>
    );
  } else if (p.type === "int" || p.type === "float" || p.type === "seed") {
    control = (
      <div className="row">
        <input {...common} className="input" type="number" value={v === undefined || v === null ? "" : String(v)}
          step={p.type === "float" ? p.step ?? 0.05 : 1} min={p.min} max={p.max}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
        {p.type === "seed" && (
          <button type="button" className="btn icon" title="Random seed" aria-label="Random seed"
            onClick={() => onChange(Math.floor(Math.random() * 2 ** 40))}><Dices size={15} /></button>
        )}
      </div>
    );
  } else {
    control = <input {...common} className="input" value={String(v ?? "")} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <label className="field" htmlFor={id}>
      <span className="row between"><span>{p.label}</span><span className="muted tiny mono">{p.key}</span></span>
      {control}
    </label>
  );
}

/** Image input bound to a library reference. */
export function ImageBinding({ p, reference, onChange }: { p: WorkflowParam; reference?: Reference; onChange: (r: Reference | null) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="field">
      <span className="row between"><span>{p.label}</span><span className="muted tiny mono">{p.key}</span></span>
      <div className="panel row">
        {reference ? <img className="thumb" src={reference.thumb_url} alt="" /> : <div className="thumb" style={{ display: "grid", placeItems: "center" }}><ImagePlus size={16} color="var(--muted)" /></div>}
        <div className="grow">
          <div className="ellipsis">{reference ? reference.title : <span className="muted">Workflow default: {String(p.default)}</span>}</div>
          {reference && <div className="muted tiny">{label(reference.category)} · {reference.width}×{reference.height}{reference.has_alpha ? " · alpha" : ""}</div>}
        </div>
        <button type="button" className="btn sm" onClick={() => setOpen(true)}>{reference ? "Change" : "Choose"}</button>
        {reference && <button type="button" className="btn sm icon ghost" aria-label="Clear" onClick={() => onChange(null)}><X size={14} /></button>}
      </div>
      {open && <ReferencePicker title={`Reference for “${p.label}”`} onClose={() => setOpen(false)} onPick={(r) => { onChange(r[0]); setOpen(false); }} />}
    </div>
  );
}

export function groupParams(params: WorkflowParam[]): [string, WorkflowParam[]][] {
  const order = ["prompt", "references", "profile", "conditioning", "sampling", "size", "models", "metadata", "custom"];
  const groups = new Map<string, WorkflowParam[]>();
  for (const p of params) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
}
