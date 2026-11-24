import { CheckCircle2, Puzzle, XCircle } from "lucide-react";
import { PageHead } from "../components/Layout";
import { Callout, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";

export function CustomNodes() {
  const info = useAsync(api.customNodes, []);
  const d = info.data;
  const installed = d?.nodes.filter((n) => n.installed).length ?? 0;
  return (
    <div className="page">
      <PageHead title="Custom Nodes" sub="An independently installable ComfyUI node package that brings profiles, reference boards, prompt templates, structured variants and metadata into the graph itself." />
      {!d ? <Spinner /> : (
        <div className="split">
          <div className="stack" style={{ gap: 14 }}>
            {d.nodes.map((n) => (
              <section key={n.name} className="card stack tight" data-testid="node-card">
                <div className="row between">
                  <div className="row"><Puzzle size={16} color="var(--accent)" /><h3>{n.display_name}</h3><span className="mono tiny muted">{n.name}</span></div>
                  {n.installed === null ? <span className="badge">Unknown</span> : n.installed ? <span className="badge ok"><CheckCircle2 size={12} />Installed</span> : <span className="badge warn"><XCircle size={12} />Not loaded</span>}
                </div>
                <p className="small text-2">{n.description}</p>
                <div className="grid-2 small">
                  <div><div className="muted tiny" style={{ marginBottom: 4 }}>INPUTS</div>
                    {[...n.inputs, ...n.optional_inputs.map((i) => ({ ...i, optional: true }))].map((i) => (
                      <div key={i.name}><span className="mono">{i.name}</span> <span className="muted">{i.type}{"optional" in i ? " · optional" : ""}</span></div>
                    ))}</div>
                  <div><div className="muted tiny" style={{ marginBottom: 4 }}>OUTPUTS</div>
                    {n.outputs.length ? n.outputs.map((o) => <div key={o.name}><span className="mono">{o.name}</span> <span className="muted">{o.type}</span></div>) : <span className="muted">Output node (saves files)</span>}</div>
                </div>
              </section>
            ))}
          </div>
          <div className="stack" style={{ gap: 20 }}>
            <section className="card stack">
              <h2>Status</h2>
              {!d.comfy_reachable ? <Callout kind="warn">ComfyUI is offline — installation status unknown.</Callout>
                : installed === d.nodes.length ? <Callout kind="ok">All {installed} nodes are loaded in the connected ComfyUI.</Callout>
                  : <Callout kind="warn">{installed}/{d.nodes.length} nodes loaded. Install the package and restart ComfyUI.</Callout>}
              <dl className="kv small"><dt>Package</dt><dd>{d.package}</dd><dt>Version</dt><dd>{d.version}</dd><dt>Source</dt><dd className="mono tiny">{d.package_path}</dd></dl>
            </section>
            <section className="card stack">
              <h2>Install</h2>
              <p className="small text-2">Symlink (or copy) the package into ComfyUI's <span className="mono">custom_nodes</span> folder and restart ComfyUI. No extra Python dependencies.</p>
              <pre className="code">{`cd /path/to/ComfyUI/custom_nodes
ln -s /path/to/comfyui-creative-studio/${d.package_path} .`}</pre>
              <p className="small muted">Nodes appear under the <b>Creative Studio</b> category. See docs/CUSTOM_NODES.md for details.</p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
