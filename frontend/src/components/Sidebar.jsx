import { NavLink } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  Code2,
  Download,
  FileCode2,
  FlaskConical,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  SearchCheck,
  Settings,
  Sparkles,
  Wrench,
} from "lucide-react";

const agentItems = [
  { to: "/product-manager", label: "Product Manager", icon: Sparkles },
  { to: "/architect", label: "Architect", icon: Boxes },
  { to: "/developer", label: "Developer", icon: Code2 },
  { to: "/tester", label: "Tester", icon: FlaskConical },
  { to: "/reviewer", label: "Reviewer", icon: SearchCheck },
];

const projectItems = [
  { to: "/generated-project", label: "Generated Project", icon: FolderKanban },
  { to: "/preview", label: "Project Preview", icon: FileCode2 },
  { to: "/activity", label: "Agent Activity", icon: Activity },
  { to: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { to: "/export", label: "Export Project", icon: Download },
  { to: "/github", label: "GitHub", icon: GitBranch },
];

function LinkItem({ item }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        `sidebar-link ${isActive ? "active" : ""}`
      }
    >
      <Icon size={18} strokeWidth={1.9} />
      <span>{item.label}</span>
    </NavLink>
  );
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <Bot size={22} />
        </div>
        <div>
          <strong>AI Dev Team</strong>
          <span>Multi-Agent SDLC</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section">
          <span className="nav-heading">Workspace</span>
          <LinkItem item={{ to: "/", label: "Dashboard", icon: LayoutDashboard }} />
        </div>

        <div className="nav-section">
          <span className="nav-heading">AI Agents</span>
          {agentItems.map((item) => (
            <LinkItem key={item.to} item={item} />
          ))}
        </div>

        <div className="nav-section">
          <span className="nav-heading">Project</span>
          {projectItems.map((item) => (
            <LinkItem key={item.to} item={item} />
          ))}
        </div>

        <div className="nav-section">
          <span className="nav-heading">System</span>
          <LinkItem item={{ to: "/settings", label: "Settings", icon: Settings }} />
        </div>
      </nav>

      <div className="sidebar-footer">
        <div className="online-dot" />
        <span>Local development</span>
      </div>
    </aside>
  );
}
