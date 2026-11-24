import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { JobStatus } from "../lib/types";

/* ---------- toasts ---------- */
type Toast = { id: number; text: string; kind: "info" | "ok" | "err" };
const ToastCtx = createContext<(text: string, kind?: Toast["kind"]) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: Toast["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "err" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/** Run an async action and toast errors. Returns the result or undefined on error. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, success?: string): Promise<T | undefined> => {
      setBusy(true);
      try {
        const r = await fn();
        if (success) toast(success, "ok");
        return r;
      } catch (e) {
        toast((e as Error).message, "err");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );
  return { run, busy };
}

/* ---------- modal ---------- */
export function Modal(props: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; size?: "wide" | "full" }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && props.onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()}>
      <div className={`modal ${props.size ?? ""}`} role="dialog" aria-modal="true" aria-label={typeof props.title === "string" ? props.title : undefined}>
        <div className="modal-head">
          <h2>{props.title}</h2>
          <button className="btn ghost icon" onClick={props.onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className={props.size === "full" ? "" : "modal-body"}>{props.children}</div>
        {props.footer && <div className="modal-foot">{props.footer}</div>}
      </div>
    </div>
  );
}

/* ---------- misc ---------- */
export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon}
      <h3>{title}</h3>
      {children && <p className="small" style={{ maxWidth: 460 }}>{children}</p>}
      {action}
    </div>
  );
}

export function Callout({ kind = "info", children }: { kind?: "info" | "warn" | "err" | "ok"; children: ReactNode }) {
  const Icon = { info: Info, warn: AlertTriangle, err: XCircle, ok: CheckCircle2 }[kind];
  const color = { info: "var(--info)", warn: "var(--warn)", err: "var(--err)", ok: "var(--ok)" }[kind];
  return (
    <div className={`callout ${kind}`}>
      <Icon size={16} color={color} />
      <div className="grow">{children}</div>
    </div>
  );
}

const STATUS_STYLE: Record<JobStatus, string> = {
  pending: "", submitted: "info", running: "accent", completed: "ok",
  failed: "err", interrupted: "warn", cancelled: "", lost: "warn",
};
const STATUS_LABEL: Record<JobStatus, string> = {
  pending: "Pending", submitted: "Queued", running: "Running", completed: "Completed",
  failed: "Failed", interrupted: "Interrupted", cancelled: "Cancelled", lost: "Lost",
};
export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge ${STATUS_STYLE[status]}`} data-testid="status">{STATUS_LABEL[status]}</span>;
}

export function Progress({ value, max, indeterminate }: { value?: number; max?: number; indeterminate?: boolean }) {
  const pct = value != null && max ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={`progress ${indeterminate ? "indeterminate" : ""}`} role="progressbar" aria-valuenow={Math.round(pct)}>
      <div style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Spinner() {
  return <div className="spinner" aria-label="Loading" />;
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)} type="button">{o.label}</button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ value, tabs, onChange }: { value: T; tabs: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={t.value === value} className={`tab ${t.value === value ? "on" : ""}`} onClick={() => onChange(t.value)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TagEditor({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const parts = draft.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (parts.length) onChange([...new Set([...tags, ...parts])]);
    setDraft("");
  };
  return (
    <div className="stack tight">
      <div className="row wrap" style={{ gap: 6 }}>
        {tags.map((t) => (
          <span key={t} className="tag">
            {t}
            <button aria-label={`Remove ${t}`} onClick={() => onChange(tags.filter((x) => x !== t))}><X size={11} /></button>
          </span>
        ))}
        {!tags.length && <span className="muted small">No tags</span>}
      </div>
      <input className="input" placeholder="Add tags, comma separated…" value={draft} onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} onBlur={add} />
    </div>
  );
}

export function ErrorNote({ error }: { error?: Error }) {
  if (!error) return null;
  return <Callout kind="err">{error.message}</Callout>;
}

export function Swatches({ colors }: { colors: string[] }) {
  return (
    <div className="swatches">
      {colors.map((c) => <span key={c} className="swatch" style={{ background: c }} title={c} />)}
    </div>
  );
}
