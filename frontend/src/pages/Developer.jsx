import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Code2, FileCode2, Package, Play } from "lucide-react";

import { useProject } from "../context/ProjectContext";
import {
  generateDeveloperProject,
  getDeveloperProject,
  getDeveloperFixRequest,
  approveDeveloperProject,
  startPreview,
} from "../services/api";
export default function Developer() {
  const { project, setProject } = useProject();
  const navigate = useNavigate();

  const [developerProject, setDeveloperProject] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sendingToTester, setSendingToTester] = useState(false);  
  const [fixRequest, setFixRequest] = useState(null);
  const [error, setError] = useState("");

  const [showCode, setShowCode] = useState(false);
const [selectedFileIndex, setSelectedFileIndex] = useState(0);

  useEffect(() => {
    loadDeveloperProject();
  }, [project?.id]);

  async function loadDeveloperProject() {
    if (!project?.id) return;
  
    try {
      setError("");
  
      const result = await getDeveloperProject(project.id);
  
      if (result.status !== "NOT_GENERATED") {
        setDeveloperProject(result);
      } else {
        setDeveloperProject(null);
      }
  
      const fixRequestData = await getDeveloperFixRequest(project.id);
      setFixRequest(fixRequestData);
  
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleGenerateProject() {
    if (!project?.id) return;

    setLoading(true);
    setError("");

    try {
      const result = await generateDeveloperProject(project.id);

      setDeveloperProject(result);

      setProject((current) => ({
        ...current,
        status: result.status || "DEVELOPER_READY",
        currentAgent: result.current_agent || "HUMAN_APPROVAL",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }
  async function handleApproveDeveloper() {
    if (!project?.id || !developerProject) return;
    setLoading(true);
    setError("");
    try {
      const result = await approveDeveloperProject(project.id);
      setProject((current) => ({ ...current, status: result.status, currentAgent: result.current_agent }));
      navigate("/tester");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunProject() {
    if (!project?.id || !developerProject) return;
    setLoading(true);
    setError("");
    try {
      const result = await startPreview(project.id);
      window.open(result.frontend_url || result.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err.message || "Could not start the generated project preview.");
      navigate("/preview");
    } finally {
      setLoading(false);
    }
  }

  if (!project?.id) {
    return (
      <div className="agent-page">
        <section className="panel">
          <div className="empty-state">
            <h3>No project selected</h3>
            <p>
              Select a project from the Dashboard before
              running the Developer Agent.
            </p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="agent-page">

      {/* PAGE TITLE */}
      <section className="page-title">
        <span className="eyebrow">
          AGENT 03 · DEVELOPER
        </span>

        <h1>Developer Agent</h1>

        <p>
          Implements the approved requirements and
          architecture and generates the project source code.
        </p>
      </section>
      {fixRequest && (
      <div className="agent-card" style={{ marginBottom: "20px" }}>
        <span className="eyebrow">REVIEWER FEEDBACK</span>

        <h3>Developer fixes requested</h3>

        <p>
          The Reviewer has identified issues that should be addressed
          in the next Developer version.
        </p>

        <p>
          <strong>
            {fixRequest.findings?.length || 0} findings
          </strong>
        </p>

        {fixRequest.recommendation && (
          <p>
            Recommendation: {fixRequest.recommendation}
          </p>
        )}
      </div>
    )}


      {/* PROJECT */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">
              PROJECT
            </span>

            <h2>{project.name}</h2>
          </div>

          <button
            className="primary-button"
            onClick={handleGenerateProject}
            disabled={loading}
          >
            <Code2 size={18} />

            {loading
              ? "Developer is coding..."
              : developerProject
              ? "Regenerate Project"
              : "Generate Project"}
          </button>
        </div>

        <p className="muted">
          {project.description}
        </p>

        {error && (
          <div className="error-box">
            {error}
          </div>
        )}
      </section>


      {/* OUTPUT OVERVIEW */}
      <div className="detail-grid">

        <section className="panel large-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">
                AGENT OUTPUT
              </span>

              <h2>
                What this agent produces
              </h2>
            </div>

            <span className="status-pill active">
              <span className="status-dot" />

              {developerProject
                ? "Generated"
                : "Ready"}
            </span>
          </div>

          <ul className="artifact-list">
            <li>Project structure</li>
            <li>Frontend and backend source code</li>
            <li>Dependencies</li>
            <li>Developer test suggestions</li>
            <li>Implementation decisions</li>
            <li>Fixes from Tester/Reviewer feedback</li>
            <li>Version history</li>
          </ul>
        </section>


        {/* HUMAN APPROVAL */}
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">
                DECISION GATE
              </span>

              <h2>Human approval</h2>
            </div>
          </div>

          <p className="muted">
            Review the generated project before it moves
            to the testing stage.
          </p>

          <div className="button-stack">

            <button
              className="secondary-button"
              onClick={() => setShowCode(true)}
              disabled={!developerProject}
            >
              <FileCode2 size={17} />
              View generated code
            </button>

            <button
              className="secondary-button"
              onClick={handleApproveDeveloper}
              disabled={!developerProject || loading}
            >
              {loading ? "Approving..." : "Approve & continue to Tester"}
            </button>

            <button
              className="secondary-button"
              onClick={handleRunProject}
              disabled={!developerProject || loading}
            >
              <Play size={17} />
              {loading ? "Starting..." : "Run project"}
            </button>

          </div>
        </section>

      </div>


      {/* GENERATED PROJECT INFO */}
      {developerProject && (
        <section className="panel">

          <div className="panel-header">
            <div>
              <span className="panel-kicker">
                DEVELOPER OUTPUT
              </span>

              <h2>Generated Project</h2>
            </div>

            <span className="status-pill active">
              Version {developerProject.version}
            </span>
          </div>


          <div className="artifact-grid">

            <div className="panel artifact-card">
              <div className="artifact-icon">
                <Code2 size={20} />
              </div>

              <span className="panel-kicker">
                FILES
              </span>

              <strong>
                {developerProject.files?.length || 0}
              </strong>
            </div>


            <div className="panel artifact-card">
              <div className="artifact-icon">
                <Package size={20} />
              </div>

              <span className="panel-kicker">
                DEPENDENCIES
              </span>

              <strong>
                {developerProject.dependencies?.length || 0}
              </strong>
            </div>


            <div className="panel artifact-card">
              <div className="artifact-icon">
                <FileCode2 size={20} />
              </div>

              <span className="panel-kicker">
                TEST SUGGESTIONS
              </span>

              <strong>
                {developerProject.test_suggestions?.length || 0}
              </strong>
            </div>

          </div>

        </section>
      )}


      {/* IMPLEMENTATION DECISIONS */}
      {developerProject && (
        <section className="panel">

          <span className="panel-kicker">
            IMPLEMENTATION
          </span>

          <h2>Implementation decisions</h2>

          <ul className="artifact-list">
            {(developerProject.implementation_decisions || []).map(
              (item, index) => (
                <li key={index}>
                  {item}
                </li>
              )
            )}
          </ul>

        </section>
      )}


      {/* TEST SUGGESTIONS */}
      {developerProject && (
        <section className="panel">

          <span className="panel-kicker">
            TESTING
          </span>

          <h2>Developer test suggestions</h2>

          <ul className="artifact-list">
            {(developerProject.test_suggestions || []).map(
              (item, index) => (
                <li key={index}>
                  {item}
                </li>
              )
            )}
          </ul>

        </section>
      )}


      {/* ACTIVITY */}
      <section className="panel">

        <div className="panel-header">
          <div>
            <span className="panel-kicker">
              ACTIVITY
            </span>

            <h2>Agent history</h2>
          </div>
        </div>

        <div className="empty-state">

          {developerProject ? (
            <>
              <p>
                Developer Agent completed a project
                generation run.
              </p>

              <small>
                Generated project version{" "}
                {developerProject.version}.
              </small>
            </>
          ) : (
            <>
              <p>
                No developer runs yet.
              </p>

              <small>
                Generate the project to start the
                Developer Agent.
              </small>
            </>
          )}

        </div>

      </section>
          {/* CODE MODAL */}
{showCode && developerProject && (
  <div
    className="modal-backdrop"
    onClick={() => setShowCode(false)}
  >
    <div
      className="code-modal"
      onClick={(event) => event.stopPropagation()}
    >
      {/* HEADER */}
      <div className="modal-header">
        <div>
          <span className="panel-kicker">
            GENERATED SOURCE CODE
          </span>

          <h2>
            Project Version {developerProject.version}
          </h2>
        </div>

        <button
          className="icon-button"
          onClick={() => setShowCode(false)}
        >
          ×
        </button>
      </div>

      {/* CODE VIEWER */}
      <div className="code-viewer">

        {/* FILE LIST */}
        <aside className="code-file-list">
          <div className="code-file-list-title">
            <span>FILES</span>
            <strong>
              {developerProject.files?.length || 0}
            </strong>
          </div>

          {(developerProject.files || []).map(
            (file, index) => (
              <button
                key={`${file.path}-${index}`}
                className={`code-file-item ${
                  selectedFileIndex === index
                    ? "selected"
                    : ""
                }`}
                onClick={() =>
                  setSelectedFileIndex(index)
                }
              >
                <FileCode2 size={16} />

                <span>
                  {file.path}
                </span>
              </button>
            )
          )}
        </aside>

        {/* CODE */}
        <section className="code-content">

          {developerProject.files?.length > 0 && (
            <>
              <div className="code-content-header">
                <div>
                  <strong>
                    {
                      developerProject.files[
                        selectedFileIndex
                      ]?.path
                    }
                  </strong>

                  <span>
                    {
                      developerProject.files[
                        selectedFileIndex
                      ]?.language
                    }
                  </span>
                </div>

                <small>
                  File {selectedFileIndex + 1} of{" "}
                  {developerProject.files.length}
                </small>
              </div>

              <pre className="code-preview">
                {
                  developerProject.files[
                    selectedFileIndex
                  ]?.content
                }
              </pre>
            </>
          )}

        </section>
      </div>

      {/* FOOTER */}
      <div className="modal-actions">
        <button
          className="secondary-button"
          onClick={() => setShowCode(false)}
        >
          Close
        </button>
      </div>
    </div>
  </div>
)}

    </div>
  );
}
