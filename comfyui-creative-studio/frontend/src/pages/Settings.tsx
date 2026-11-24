import { Fragment, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { PageHead } from "../components/Layout";
import { Callout, Spinner, useAction } from "../components/ui";
import { api } from "../lib/api";
import { bytes, useAsync } from "../lib/hooks";

export function SettingsPage() {
  const settings = useAsync(api.settings, []);
  const diag = useAsync(api.diagnostics, []);
  const [url, setUrl] = useState("");
  const [test, setTest] = useState<{ reachable: boolean; version?: string; error?: string }>();
  const { run, busy } = useAction();
  useEffect(() => { if (settings.data) setUrl(settings.data.comfy_url); }, [settings.data]);
  const s = diag.data?.status;
  return (
    <div className="page">
      <PageHead title="Settings" sub="Connection to your local ComfyUI and diagnostics." />
      <div className="split">
        <div className="stack" style={{ gap: 20 }}>
          <section className="card stack">
            <h2>ComfyUI server</h2>
            <label className="field"><span>Server URL</span><input className="input mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://127.0.0.1:8188" /></label>
            <div className="row">
              <button className="btn" disabled={busy} onClick={async () => setTest(await run(() => api.testUrl(url)))}>Test</button>
              <button className="btn primary" disabled={busy || url === settings.data?.comfy_url} onClick={async () => { await run(() => api.saveSettings(url), "Saved"); void settings.reload(); void diag.reload(); }}>Save</button>
              {test && (test.reachable ? <span className="badge ok">Reachable · ComfyUI {test.version}</span> : <span className="badge err">{test.error}</span>)}
            </div>
            <p className="muted small">Default comes from <span className="mono">CS_COMFY_URL</span> in <span className="mono">.env</span>; a value saved here overrides it.
              Start ComfyUI normally (e.g. <span className="mono">python main.py</span>); it listens on port 8188 by default.</p>
          </section>
          <section className="card stack">
            <div className="card-head" style={{ marginBottom: 0 }}><h2>Diagnostics</h2><button className="btn sm" onClick={() => void diag.reload()}><RefreshCw size={13} />Run again</button></div>
            {!diag.data ? <Spinner /> : diag.data.checks.map((c) => (
              <div key={c.name} className="row" style={{ alignItems: "flex-start" }}>
                {c.ok ? <CheckCircle2 size={17} color="var(--ok)" /> : <XCircle size={17} color={c.name.includes("IPAdapter") || c.name.includes("device") ? "var(--warn)" : "var(--err)"} />}
                <div><div style={{ fontWeight: 550 }}>{c.name}</div><div className="small muted">{c.detail}</div></div>
              </div>
            ))}
          </section>
        </div>
        <section className="card stack">
          <h2>System</h2>
          {s?.reachable ? (
            <dl className="kv small">
              <dt>ComfyUI</dt><dd>{s.version}</dd><dt>Python</dt><dd>{s.python}</dd><dt>PyTorch</dt><dd>{s.pytorch}</dd><dt>OS</dt><dd>{s.os}</dd>
              <dt>RAM</dt><dd>{bytes(s.ram_free)} free of {bytes(s.ram_total)}</dd>
              {s.devices?.map((d) => <Fragment key={d.name}><dt>Device</dt><dd>{d.name} ({d.type}) · {bytes(d.vram_free)} / {bytes(d.vram_total)}</dd></Fragment>)}
              <dt>WebSocket</dt><dd>{s.websocket_connected ? "connected" : "not connected"}</dd>
            </dl>
          ) : <Callout kind="err">{s?.error ?? "Not connected"}</Callout>}
          <Callout kind="info">On Apple Silicon, ComfyUI reports the device as <span className="mono">mps</span>. Unified memory is shared between CPU and GPU; see docs/MODEL_COMPATIBILITY.md for model sizing.</Callout>
        </section>
      </div>
    </div>
  );
}
