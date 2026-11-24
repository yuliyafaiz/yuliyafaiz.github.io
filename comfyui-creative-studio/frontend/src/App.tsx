import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/ui";
import { Dashboard } from "./pages/Dashboard";
import { Projects, ProjectDetailPage } from "./pages/Projects";
import { ReferenceStudio } from "./pages/ReferenceStudio";
import { ProfileEditor } from "./pages/ProfileEditor";
import { Workflows, WorkflowDetailPage } from "./pages/Workflows";
import { Consistency, ConsistencyEditor } from "./pages/Consistency";
import { Production } from "./pages/Production";
import { CustomNodes } from "./pages/CustomNodes";
import { SettingsPage } from "./pages/Settings";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="projects" element={<Projects />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="references" element={<ReferenceStudio />} />
        <Route path="references/profiles/:id" element={<ProfileEditor />} />
        <Route path="workflows" element={<Workflows />} />
        <Route path="workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="consistency" element={<Consistency />} />
        <Route path="consistency/:id" element={<ConsistencyEditor />} />
        <Route path="production" element={<Production />} />
        <Route path="custom-nodes" element={<CustomNodes />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter><AppRoutes /></BrowserRouter>
    </ToastProvider>
  );
}
