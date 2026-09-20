import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import { ProjectProvider } from "./context/ProjectContext";
import Dashboard from "./pages/Dashboard";
import ProductManager from "./pages/ProductManager";
import Architect from "./pages/Architect";
import Developer from "./pages/Developer";
import Tester from "./pages/Tester";
import Reviewer from "./pages/Reviewer";
import AgentActivity from "./pages/AgentActivity";
import Settings from "./pages/Settings";
import GeneratedProject from "./pages/GeneratedProject";
import {
  Preview,
  Evaluation,
  ExportProject,
  GitHub,
} from "./pages/PlaceholderPages";

export default function App() {
  return (
    <ProjectProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/product-manager" element={<ProductManager />} />
          <Route path="/architect" element={<Architect />} />
          <Route path="/developer" element={<Developer />} />
          <Route path="/tester" element={<Tester />} />
          <Route path="/reviewer" element={<Reviewer />} />
          <Route path="/generated-project" element={<GeneratedProject />} />
          <Route path="/preview" element={<Preview />} />
          <Route path="/activity" element={<AgentActivity />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/export" element={<ExportProject />} />
          <Route path="/github" element={<GitHub />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </ProjectProvider>
  );
}
