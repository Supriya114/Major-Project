import { useEffect, useState } from "react";
import { Bell, ChevronDown, CircleHelp, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import { useProject } from "../context/ProjectContext";
import { listProjects } from "../services/api";

function routeFor(project) {
  const status = project?.status || "";
  const agent = project?.current_agent || project?.currentAgent || "";
  if (["COMPLETED", "PROJECT_COMPLETED", "APPROVED"].includes(status)) return "/generated-project";
  if (status === "DEVELOPER_REVIEWED_REQUIREMENTS") return "/product-manager";
  if (["DEVELOPER_READY", "DEVELOPER_GENERATING", "DEVELOPER_GENERATION_FAILED", "DEVELOPER_FIX_REQUESTED"].includes(status)) return "/developer";
  if (["TESTER_GENERATING", "TESTER_READY", "TESTS_FAILED", "TESTS_COMPLETED"].includes(status)) return "/tester";
  if (status === "REVIEW_READY") return "/reviewer";
  if (agent === "ARCHITECT") return "/architect";
  if (agent === "DEVELOPER") return "/developer";
  if (agent === "TESTER") return "/tester";
  if (agent === "REVIEWER") return "/reviewer";
  return "/product-manager";
}

export default function Layout({ children }) {
  const { project, setProject } = useProject();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    listProjects()
      .then((result) => {
        if (!mounted) return;
        const items = (result.projects || []).map((item) => ({
          ...item,
          id: item.id || item._id,
          currentAgent: item.currentAgent || item.current_agent || "PRODUCT_MANAGER",
        }));
        setProjects(items);
        if (project?.id) {
          const matching = items.find((item) => item.id === project.id);
          if (matching) {
            setProject(matching);
          } else {
            // The saved project no longer exists. Never fall back to another
            // user's/older project automatically.
            setProject({
              id: null,
              name: "No project selected",
              description: "Create a project to begin the AI-driven SDLC workflow.",
              status: "IDLE",
              currentAgent: "PRODUCT_MANAGER",
            });
          }
        }
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, [project?.id, setProject]);

  function selectProject(item) {
    setProject(item);
    setOpen(false);
    navigate(routeFor(item));
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-area">
        <header className="topbar">
          <div style={{ position: "relative" }}>
            <span className="topbar-label">CURRENT PROJECT</span>
            <button className="project-selector" onClick={() => setOpen((value) => !value)} type="button">
              {project?.name || "No project selected"}
              <ChevronDown size={15} />
            </button>
            {open && (
              <div className="project-menu">
                <button
                  type="button"
                  className="project-menu-item"
                  onClick={() => {
                    setOpen(false);
                    navigate("/");
                  }}
                >
                  <strong><Plus size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />New project</strong>
                  <span>Create a separate workflow</span>
                </button>
                {projects.length === 0 ? (
                  <div className="project-menu-empty">No existing projects</div>
                ) : projects.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`project-menu-item ${item.id === project?.id ? "selected" : ""}`}
                    onClick={() => selectProject(item)}
                  >
                    <strong>{item.name}</strong>
                    <span>{item.status?.replaceAll("_", " ")}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="topbar-actions">
            <button className="icon-button" title="Help" type="button"><CircleHelp size={19} /></button>
            <button className="icon-button" title="Notifications" type="button"><Bell size={19} /></button>
            <div className="avatar">SD</div>
          </div>
        </header>
        <div className="page-container">{children}</div>
      </main>
    </div>
  );
}
