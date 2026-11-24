import { NavLink, Outlet } from "react-router-dom";
import { Boxes, FolderKanban, Gem, Images, LayoutDashboard, Puzzle, Settings, Sparkles, Workflow } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/references", label: "Reference Studio", icon: Images },
  { to: "/workflows", label: "Workflows", icon: Workflow },
  { to: "/consistency", label: "Consistency", icon: Gem },
  { to: "/production", label: "Production Board", icon: Sparkles },
];
const NAV2 = [
  { to: "/custom-nodes", label: "Custom Nodes", icon: Puzzle },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function ConnectionIndicator() {
  const st = useAsync(api.comfyStatus, [], 5000);
  const s = st.data;
  const state = !s ? "…" : s.reachable ? `ComfyUI ${s.version ?? ""}` : "ComfyUI offline";
  return (
    <NavLink to="/settings" className="panel row" style={{ gap: 10 }} data-testid="connection">
      <span className={`dot ${s ? (s.reachable ? "ok" : "err") : ""}`} />
      <div className="grow">
        <div className="small" style={{ fontWeight: 550 }}>{state}</div>
        <div className="tiny muted ellipsis">{s?.reachable ? `${s.queue_running ?? 0} running · ${s.queue_pending ?? 0} queued` : s?.url ?? "checking"}</div>
      </div>
    </NavLink>
  );
}

export function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Boxes size={16} /></div>
          <div><div className="brand-name">Creative Studio</div><div className="brand-sub">for ComfyUI</div></div>
        </div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <n.icon size={17} />{n.label}
          </NavLink>
        ))}
        <div className="nav-section">System</div>
        {NAV2.map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <n.icon size={17} />{n.label}
          </NavLink>
        ))}
        <div className="sidebar-foot"><ConnectionIndicator /></div>
      </aside>
      <main className="main"><Outlet /></main>
    </div>
  );
}

export function PageHead({ title, sub, crumbs, actions }: { title: React.ReactNode; sub?: React.ReactNode; crumbs?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="page-head">
      <div className="grow">
        {crumbs && <div className="crumbs">{crumbs}</div>}
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  );
}
