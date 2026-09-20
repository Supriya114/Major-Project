import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  Check,
  Code2,
  FlaskConical,
  Play,
  Plus,
  SearchCheck,
  Sparkles,
} from "lucide-react";

import AgentCard from "../components/AgentCard";
import MetricCard from "../components/MetricCard";
import {createProject,listProjects,deleteProject,} from "../services/api";
import { useProject } from "../context/ProjectContext";

const WORKFLOW_STAGES = [
  "Requirements",
  "Developer Review",
  "Human Approval",
  "Architecture",
  "Development",
  "Testing",
  "Review",
];

function getStageIndex(project) {
  const status = project?.status || "";
  const agent = project?.current_agent || project?.currentAgent || "";

  if (
    status === "CREATED" ||
    status === "REQUIREMENTS_READY" ||
    agent === "PRODUCT_MANAGER"
  ) {
    return 0;
  }

  if (
    status === "DEVELOPER_REVIEWED_REQUIREMENTS" ||
    status === "REQUIREMENTS_REVISED" ||
    agent === "DEVELOPER"
  ) {
    return status === "DEVELOPER_REVIEWED_REQUIREMENTS" ? 2 : 1;
  }

  if (
    status === "ARCHITECTURE_READY" ||
    status === "ARCHITECTURE_REVISION_REQUESTED" ||
    agent === "ARCHITECT"
  ) {
    return 3;
  }

  if (
    status === "ARCHITECTURE_APPROVED" ||
    status === "DEVELOPER_GENERATING" ||
    status === "DEVELOPER_READY" ||
    status === "DEVELOPER_GENERATION_FAILED" ||
    status === "DEVELOPER_FIX_REQUESTED"
  ) {
    return 4;
  }

  if (
    status === "TESTER_GENERATING" ||
    status === "TESTER_READY" ||
    status === "TESTS_FAILED" ||
    status === "TESTS_COMPLETED" ||
    agent === "TESTER"
  ) {
    return 5;
  }

  if (
    status === "TESTS_APPROVED" ||
    status === "REVIEW_READY" ||
    agent === "REVIEWER"
  ) {
    return 6;
  }

  if (
    status === "COMPLETED" ||
    ["PROJECT_COMPLETED", "APPROVED"].includes(status)
  ) {
    return WORKFLOW_STAGES.length - 1;
  }

  return 0;
}

function getRouteForProject(project) {
  const status = project?.status || "";
  const agent = project?.current_agent || project?.currentAgent || "";

  if (["COMPLETED", "PROJECT_COMPLETED", "APPROVED"].includes(status)) {
    return "/generated-project";
  }

  if (status === "DEVELOPER_REVIEWED_REQUIREMENTS") {
    return "/product-manager";
  }

  if (["DEVELOPER_READY", "DEVELOPER_GENERATING", "DEVELOPER_GENERATION_FAILED", "DEVELOPER_FIX_REQUESTED"].includes(status)) {
    return "/developer";
  }

  if (["TESTER_GENERATING", "TESTER_READY", "TESTS_FAILED", "TESTS_COMPLETED"].includes(status)) {
    return "/tester";
  }

  if (status === "REVIEW_READY") {
    return "/reviewer";
  }

  if (agent === "PRODUCT_MANAGER") {
    return "/product-manager";
  }

  if (agent === "ARCHITECT") {
    return "/architect";
  }

  if (agent === "DEVELOPER") {
    return "/developer";
  }

  if (agent === "TESTER") {
    return "/tester";
  }

  if (agent === "REVIEWER") {
    return "/reviewer";
  }

  if (agent === "HUMAN_APPROVAL") {
    if (status === "REQUIREMENTS_APPROVED") return "/architect";
    if (status === "ARCHITECTURE_APPROVED") return "/developer";
    if (status === "DEVELOPER_READY") return "/developer";
    if (status === "TESTS_COMPLETED") return "/tester";
    if (status === "REVIEW_READY") return "/reviewer";
    return "/product-manager";
  }

  return "/product-manager";
}

function formatStatus(status) {
  if (!status) return "UNKNOWN";

  return status
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatAgent(agent) {
  if (!agent) return "Product Manager";

  return agent
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(date) {
  if (!date) return "—";

  try {
    return new Date(date).toLocaleString();
  } catch {
    return "—";
  }
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { project, setProject } = useProject();

  const [projects, setProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  function getAgentStatus(agentName, project) {
    if (!project) return "waiting";
  
    const status = project.status || "";
    const currentAgent =
      project.current_agent ||
      project.currentAgent ||
      "";
  
    // Completed project
    if (
      status === "COMPLETED" ||
      ["PROJECT_COMPLETED", "APPROVED"].includes(status)
    ) {
      return "completed";
    }
  
    // Human approval happens between workflow stages.
    if (currentAgent === "HUMAN_APPROVAL") {
      if (status === "DEVELOPER_REVIEWED_REQUIREMENTS") {
        return agentName === "PRODUCT_MANAGER" ? "completed" : "waiting";
      }
      if (status === "DEVELOPER_READY") {
        return agentName === "DEVELOPER" ? "completed" : "waiting";
      }
      if (status === "TESTS_COMPLETED") {
        return agentName === "TESTER" ? "completed" : "waiting";
      }
      return "waiting";
    }
  
    // Current agent is active
    if (currentAgent === agentName) {
      return "active";
    }
  
    const stageOrder = {
      PRODUCT_MANAGER: 0,
      DEVELOPER: 1,
      ARCHITECT: 2,
      TESTER: 3,
      REVIEWER: 4,
    };
  
    const currentIndex = stageOrder[currentAgent];
  
    if (currentIndex === undefined) {
      return "waiting";
    }
  
    const agentIndex = stageOrder[agentName];
  
    if (agentIndex === undefined) {
      return "waiting";
    }
  
    if (agentIndex < currentIndex) {
      return "completed";
    }
  
    return "waiting";
  }
  async function loadProjects() {
    try {
      setLoadingProjects(true);
      setError("");
  
      const result = await listProjects();
  
      const normalized = (result.projects || []).map((item) => ({
        ...item,
        id: item.id || item._id,
        currentAgent:
          item.currentAgent ||
          item.current_agent ||
          "PRODUCT_MANAGER",
      }));
  
      setProjects(normalized);
  
      // Do NOT automatically select the first project.
      // A newly opened workspace must never silently resume an older project.
      // The user explicitly selects/resumes the project they want.
    } catch (err) {
      console.error("Failed to load projects:", err);
      setError(err.message);
    } finally {
      setLoadingProjects(false);
    }
  }
  
  useEffect(() => {
    loadProjects();
  }, []);

  async function handleCreate(event) {
    event.preventDefault();

    setCreating(true);
    setError("");

    try {
      const created = await createProject({
        name,
        description,
      });

      const normalizedProject = {
        ...created,
        id: created.id || created._id,
        currentAgent:
          created.currentAgent ||
          created.current_agent ||
          "PRODUCT_MANAGER",
      };

      setProject(normalizedProject);

      setProjects((current) => [
        normalizedProject,
        ...current,
      ]);

      setShowForm(false);
      setName("");
      setDescription("");

      navigate("/product-manager");
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  function resumeProject(selectedProject) {
    const normalizedProject = {
      ...selectedProject,
      id: selectedProject.id || selectedProject._id,
      currentAgent:
        selectedProject.currentAgent ||
        selectedProject.current_agent ||
        "PRODUCT_MANAGER",
    };

    setProject(normalizedProject);

    navigate(getRouteForProject(normalizedProject));
  }

  function viewProject(selectedProject) {
    const normalizedProject = {
      ...selectedProject,
      id: selectedProject.id || selectedProject._id,
      currentAgent:
        selectedProject.currentAgent ||
        selectedProject.current_agent ||
        "PRODUCT_MANAGER",
    };

    setProject(normalizedProject);

    if (
      selectedProject.status === "COMPLETED" ||
      ["PROJECT_COMPLETED", "APPROVED"].includes(selectedProject.status)
    ) {
      navigate("/generated-project");
    } else {
      navigate("/product-manager");
    }
  }

  async function handleDelete(selectedProject) {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${selectedProject.name}"? This action cannot be undone.`
    );
  
    if (!confirmed) return;
  
    try {
      setError("");
  
      await deleteProject(selectedProject.id);
  
      // Remove from Dashboard immediately
      setProjects((current) =>
        current.filter(
          (item) => item.id !== selectedProject.id
        )
      );
  
      // If this was the currently selected project,
      // clear the selected project
      if (project?.id === selectedProject.id) {
        setProject({
          id: null,
          name: "No project selected",
          description:
            "Create a project to begin the AI-driven SDLC workflow.",
          status: "IDLE",
          currentAgent: "PRODUCT_MANAGER",
        });
      }
    } catch (err) {
      setError(err.message);
    }
  }
  

  return (
    <>
      {/* HERO */}
      <section className="hero">
        <div>
          <span className="eyebrow">
            MULTI-AGENT SOFTWARE ENGINEERING
          </span>

          <h1>
            Build software with an AI development team.
          </h1>

          <p>
            Transform an idea into requirements, architecture,
            source code, tests, and reviewed software through a
            controlled human-in-the-loop workflow.
          </p>
        </div>

        <button
          className="primary-button"
          onClick={() => {
            setError("");
            setShowForm(true);
          }}
        >
          <Plus size={18} />
          New Project
        </button>
      </section>

      {/* CREATE PROJECT MODAL */}
      {showForm && (
        <div className="modal-backdrop">
          <form
            className="modal-card"
            onSubmit={handleCreate}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">
                  START WORKFLOW
                </span>

                <h2>Create a new project</h2>
              </div>

              <button
                type="button"
                className="icon-button"
                onClick={() => setShowForm(false)}
              >
                ×
              </button>
            </div>

            <label>
              Project name

              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Student PG Finder"
                required
              />
            </label>

            <label>
              What do you want to build?

              <textarea
                value={description}
                onChange={(e) =>
                  setDescription(e.target.value)
                }
                placeholder="Describe the software idea in natural language..."
                rows={6}
              />
            </label>

            {error && (
              <div className="error-box">
                {error}
              </div>
            )}

            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setShowForm(false)}
              >
                Cancel
              </button>

              <button
                className="primary-button"
                disabled={creating}
              >
                {creating
                  ? "Creating..."
                  : "Create Project"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* YOUR PROJECTS */}
      <section className="section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              PROJECT WORKSPACE
            </span>

            <h2>Your projects</h2>
          </div>

          <button
            className="text-button"
            onClick={() => setShowForm(true)}
          >
            New project
            <Plus size={16} />
          </button>
        </div>

        {loadingProjects ? (
          <div className="empty-projects">
            Loading your projects...
          </div>
        ) : projects.length === 0 ? (
          <div className="empty-projects">
            <div className="empty-project-icon">
              <Sparkles size={24} />
            </div>

            <h3>No projects yet</h3>

            <p>
              Create your first project and let the AI
              development team start the SDLC workflow.
            </p>

            <button
              className="primary-button"
              onClick={() => setShowForm(true)}
            >
              <Plus size={18} />
              Create your first project
            </button>
          </div>
        ) : (
          <div className="projects-grid">
            {projects.map((item) => {
              const stageIndex = getStageIndex(item);

              const isCompleted =
                item.status === "COMPLETED" ||
                ["PROJECT_COMPLETED", "APPROVED"].includes(item.status);

              return (
                <article
                  className="project-card"
                  key={item.id || item._id}
                >
                  <div className="project-card-top">
                    <div>
                      <span className="project-status-label">
                        {isCompleted
                          ? "COMPLETED"
                          : "IN PROGRESS"}
                      </span>

                      <h3>{item.name}</h3>
                    </div>

                    <div className="project-status-badge">
                      {formatStatus(item.status)}
                    </div>
                  </div>

                  <p className="project-description">
                    {item.description ||
                      "No project description provided."}
                  </p>

                  {/* WORKFLOW PROGRESS */}
                  <div className="project-progress">
                    {WORKFLOW_STAGES.map(
                      (stage, index) => {
                        const completed =
                          index < stageIndex ||
                          isCompleted;

                        const current =
                          index === stageIndex &&
                          !isCompleted;

                        return (
                          <div
                            className="project-stage"
                            key={stage}
                          >
                            <div
                              className={`stage-dot ${
                                completed
                                  ? "completed"
                                  : current
                                  ? "current"
                                  : ""
                              }`}
                            >
                              {completed ? (
                                <Check size={12} />
                              ) : (
                                index + 1
                              )}
                            </div>

                            <span
                              className={
                                current
                                  ? "current-stage-text"
                                  : ""
                              }
                            >
                              {stage}
                            </span>
                          </div>
                        );
                      }
                    )}
                  </div>

                  <div className="project-card-info">
                    <div>
                      <span>Current agent</span>

                      <strong>
                        {formatAgent(
                          item.current_agent ||
                            item.currentAgent
                        )}
                      </strong>
                    </div>

                    <div>
                      <span>Last updated</span>

                      <strong>
                        {formatDate(item.updated_at)}
                      </strong>
                    </div>
                  </div>

                  <div className="project-card-actions">
                    <button
                      className="secondary-button"
                      onClick={() =>
                        viewProject(item)
                      }
                    >
                      View
                    </button>

                    {!isCompleted && (
                      <button
                        className="primary-button"
                        onClick={() =>
                          resumeProject(item)
                        }
                      >
                        <Play size={16} />
                        Resume Project
                      </button>
                    )}

                    {isCompleted && (
                      <button
                        className="primary-button"
                        onClick={() =>
                          resumeProject(item)
                        }
                      >
                        <ArrowRight size={16} />
                        Open Project
                      </button>
                    )}
                    <button
                      className="danger-button"
                      onClick={() => handleDelete(item)}
                      > Delete
                      </button>
 
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* CURRENT PROJECT METRICS */}
      <section className="metrics-grid">
        <MetricCard
          label="Project Status"
          value={project?.status || "IDLE"}
          detail="Current state"
        />

        <MetricCard
          label="Current Agent"
          value={formatAgent(
            project?.currentAgent
          )}
          detail="Workflow stage"
        />

        <MetricCard
          label="Tests"
          value="—"
          detail="Available after testing"
        />

        <MetricCard
          label="Coverage"
          value="—"
          detail="Available after testing"
        />
      </section>

      {/* AGENTS */}
      <section className="section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              WORKFLOW
            </span>

            <h2>AI development team</h2>
          </div>

          <button
            className="text-button"
            onClick={() => navigate("/activity")}
          >
            View activity
            <ArrowRight size={16} />
          </button>
        </div>

        <div className="agent-grid">
        <AgentCard
        icon={<Sparkles size={21} />}
        name="Product Manager"
        role="Requirements"
        status={getAgentStatus("PRODUCT_MANAGER", project)}
        description="Turns the user's idea into structured functional and non-functional requirements."
       />

<AgentCard
  icon={<Boxes size={21} />}
  name="Architect"
  role="System design"
  status={getAgentStatus("ARCHITECT", project)}
  description="Defines technology, modules, architecture, database design, and APIs."
/>

<AgentCard
  icon={<Code2 size={21} />}
  name="Developer"
  role="Implementation"
  status={getAgentStatus("DEVELOPER", project)}
  description="Generates the project structure, source code, and implementation feedback."
/>
<AgentCard
  icon={<FlaskConical size={21} />}
  name="Tester"
  role="Validation"
  status={getAgentStatus("TESTER", project)}
  description="Generates visible test cases, accepts custom tests, executes them, and reports failures."
/>
<AgentCard
  icon={<SearchCheck size={21} />}
  name="Reviewer"
  role="Quality & security"
  status={getAgentStatus("REVIEWER", project)}
  description="Reviews quality, security, maintainability, and architecture compliance."
/>
        </div>
      </section>

      {/* WORKFLOW */}
      <section className="section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              HUMAN-IN-THE-LOOP
            </span>

            <h2>Controlled workflow</h2>
          </div>
        </div>

        <div className="workflow-strip">
          {[
            "Requirements",
            "Developer opinion",
            "Architecture",
            "Developer opinion",
            "Code",
            "Testing",
            "Review",
          ].map((item, index) => (
            <div
              className="workflow-step"
              key={`${index}-${item}`}
            >
              <span>
                {String(index + 1).padStart(2, "0")}
              </span>

              <strong>{item}</strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}