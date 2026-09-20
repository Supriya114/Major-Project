import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Boxes,
  Database,
  GitBranch,
  Layers,
  Network,
  Server,
  Sparkles,
} from "lucide-react";
import {
  generateArchitecture,
  getArchitecture,
  getArchitectureVersions,
  getArchitectureVersion,
  requestArchitectureRevision,
  restoreArchitectureVersion,
  approveArchitecture,
} from "../services/api";
import { useProject } from "../context/ProjectContext";
 


export default function Architect() {

  const { project, setProject } = useProject();
const navigate = useNavigate();

const [requestingRevision, setRequestingRevision] = useState(false);
const [architecture, setArchitecture] = useState(null);
const [loading, setLoading] = useState(false);
const [error, setError] = useState("");
const [architectureVersions, setArchitectureVersions] = useState([]);
const [selectedVersion, setSelectedVersion] = useState(null);
const [loadingVersions, setLoadingVersions] = useState(false);
const [restoringVersion, setRestoringVersion] = useState(false);

const [showRevisionModal, setShowRevisionModal] = useState(false);
const [revisionFeedback, setRevisionFeedback] = useState("");
const [approvingArchitecture, setApprovingArchitecture] =
  useState(false);
  async function loadArchitecture() {

    if (!project?.id) return;

    try {

      const data = await getArchitecture(project.id);

      if (data?.status !== "NOT_GENERATED") {
        setArchitecture(data);
      }

    } catch (err) {
      console.error(err);
    }
  }

  async function loadArchitectureVersions() {
    if (!project?.id) return;
  
    setLoadingVersions(true);
  
    try {
      const result = await getArchitectureVersions(project.id);
  
      setArchitectureVersions(result.versions || []);
    } catch (err) {
      console.error("Failed to load architecture versions:", err);
    } finally {
      setLoadingVersions(false);
    }
  }
  async function handleViewVersion(version) {
    if (!project?.id) return;
  
    try {
      setError("");
  
      const result = await getArchitectureVersion(
        project.id,
        version
      );
  
      setSelectedVersion(result);
    } catch (err) {
      setError(err.message);
    }
  }
  
  async function handleRestoreVersion(version) {
    if (!project?.id) return;
  
    const confirmed = window.confirm(
      `Restore Architecture Version ${version}?\n\n` +
        `This will create a new version based on Version ${version}. ` +
        `Your existing versions will remain unchanged.`
    );
  
    if (!confirmed) return;
  
    setRestoringVersion(true);
    setError("");
  
    try {
      const result = await restoreArchitectureVersion(
        project.id,
        version
      );
  
      setArchitecture(result);
  
      await loadArchitectureVersions();
  
      setSelectedVersion(null);
  
      setProject((current) => ({
        ...current,
        status: "ARCHITECTURE_READY",
        currentAgent: "ARCHITECT",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setRestoringVersion(false);
    }
  }
  useEffect(() => {
    loadArchitecture();
    loadArchitectureVersions();
  }, [project?.id]);

  async function handleGenerate() {

    if (!project?.id) {
      setError("Select or create a project first.");
      return;
    }

    setLoading(true);
    setError("");

    try {

      const result = await generateArchitecture(project.id);

      setArchitecture(result);

    } catch (err) {

      setError(err.message);

    } finally {

      setLoading(false);

    }
  }


  if (!project?.id) {

    return (
      <div className="agent-page">

        <section className="page-title">
          <span className="eyebrow">AGENT 02</span>

          <h1>Architect Agent</h1>

          <p>
            Select a project from the Dashboard before running
            the Architect Agent.
          </p>
        </section>

      </div>
    );
  }
  
  function openRevisionModal() {
    setRevisionFeedback("");
    setError("");
    setShowRevisionModal(true);
  }
  
  function closeRevisionModal() {
    if (requestingRevision) return;
  
    setShowRevisionModal(false);
  }
  
  async function handleRequestRevision() {
    if (!project?.id) return;
  
    const feedback = revisionFeedback.trim();
  
    if (!feedback) {
      setError("Please describe what you want the Architect to change.");
      return;
    }
  
    setRequestingRevision(true);
    setError("");
  
    try {
      const result = await requestArchitectureRevision(
        project.id,
        feedback
      );
  
      // Show the newly generated architecture immediately
      setArchitecture(result);
  
      // Close modal
      setShowRevisionModal(false);
      setRevisionFeedback("");
  
      // Update project workflow state
      setProject((current) => ({
        ...current,
        status: "ARCHITECTURE_READY",
        currentAgent: "ARCHITECT",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setRequestingRevision(false);
    }
  }

  async function handleApproveArchitecture() {
    if (!project?.id) return;
  
    setApprovingArchitecture(true);
    setError("");
  
    try {
      const result = await approveArchitecture(project.id);
  
      setProject((current) => ({
        ...current,
        status: result.status,
        currentAgent: result.current_agent,
      }));
      navigate("/developer");
    } catch (err) {
      setError(err.message);
    } finally {
      setApprovingArchitecture(false);
    }
  }
   
  return (

    <div className="agent-page">

      <section className="page-title">

        <span className="eyebrow">
          AGENT 02 · ARCHITECT
        </span>

        <h1>Architect Agent</h1>

        <p>
          Converts approved requirements into a practical
          technical architecture for the Developer Agent.
        </p>

      </section>


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
            onClick={handleGenerate}
            disabled={loading}
          >

            <Sparkles size={18} />

            {loading
              ? "Designing architecture..."
              : "Generate Architecture"}

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


      {!architecture && !loading && (

        <section className="panel">

          <div className="empty-state">

            <Network size={30} />

            <h3>Architecture not generated yet</h3>

            <p>
              The Architect Agent will use the Product Manager
              requirements and Developer feasibility opinion
              to design the system.
            </p>

          </div>

        </section>

      )}


      {architecture && (

        <>
        {architectureVersions.length > 0 && (
  <section className="panel">
    <div className="panel-header">
      <div>
        <span className="panel-kicker">
          VERSION HISTORY
        </span>

        <h2>Architecture Versions</h2>

        <p className="muted">
          View previous architectures or restore an earlier
          version without deleting your history.
        </p>
      </div>
    </div>

    {loadingVersions ? (
      <p className="muted">
        Loading versions...
      </p>
    ) : (
      <div className="version-history">
        {architectureVersions.map((version) => {
          const isCurrent =
            architecture?.version === version.version;

          return (
            <div
              className={`version-card ${
                isCurrent ? "current" : ""
              }`}
              key={version._id || version.version}
            >
              <div className="version-card-main">
                <div>
                  <div className="version-title">
                    <strong>
                      Version {version.version}
                    </strong>

                    {isCurrent && (
                      <span className="status-badge">
                        CURRENT
                      </span>
                    )}
                  </div>

                  <p className="muted">
                    {version.restored_from_version
                      ? `Restored from Version ${version.restored_from_version}`
                      : version.version === 1
                      ? "Original architecture"
                      : "Revised architecture"}
                  </p>
                </div>

                <div className="version-actions">
                  <button
                    className="secondary-button"
                    onClick={() =>
                      handleViewVersion(version.version)
                    }
                  >
                    View
                  </button>

                  {!isCurrent && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        handleRestoreVersion(version.version)
                      }
                      disabled={restoringVersion}
                    >
                      {restoringVersion
                        ? "Restoring..."
                        : "Restore"}
                    </button>
                  )}
                </div>
              </div>

              {version.changes_made?.length > 0 && (
                <div className="version-changes">
                  <span className="panel-kicker">
                    CHANGES
                  </span>

                  <ul>
                    {version.changes_made.map(
                      (change, index) => (
                        <li key={index}>
                          {change}
                        </li>
                      )
                    )}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    )}
  </section>
)}
                  {architecture.version > 1 && (
            <section className="panel revision-summary">
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">
                    ARCHITECTURE REVISED
                  </span>

                  <h2>
                    ✨ Version {architecture.version} changes
                  </h2>
                </div>
              </div>

              {architecture.revision_feedback && (
                <div className="revision-feedback">
                  <strong>Human feedback</strong>
                  <p>
                    {architecture.revision_feedback}
                  </p>
                </div>
              )}

              <div>
                <span className="panel-kicker">
                  CHANGES MADE
                </span>

                <ul className="artifact-list">
                  {(architecture.changes_made || []).map(
                    (change, index) => (
                      <li key={`${index}-${change}`}>
                        {change}
                      </li>
                    )
                  )}
                </ul>
              </div>
            </section>
          )}

          <section className="artifact-grid">

            <Artifact
              icon={<Server size={20} />}
              title="Frontend"
              value={
                architecture.technology_stack?.frontend
              }
            />

            <Artifact
              icon={<Layers size={20} />}
              title="Backend"
              value={
                architecture.technology_stack?.backend
              }
            />

            <Artifact
              icon={<Database size={20} />}
              title="Database"
              value={
                architecture.technology_stack?.database
              }
            />

            <Artifact
              icon={<GitBranch size={20} />}
              title="Deployment"
              value={
                architecture.technology_stack?.deployment
              }
            />

          </section>


          <section className="panel">

            <div className="panel-header">

              <div>

                <span className="panel-kicker">
                  SYSTEM DESIGN
                </span>

                <h2>System Architecture</h2>

              </div>

            </div>

            <div className="architecture-description">
              {architecture.system_architecture}
            </div>

          </section>


          <section className="panel">

            <div className="panel-header">

              <div>

                <span className="panel-kicker">
                  MODULES
                </span>

                <h2>System Modules</h2>

              </div>

            </div>

            <div className="module-grid">

              {(architecture.modules || []).map(
                (module, index) => (

                  <div
                    className="module-card"
                    key={`${module.name}-${index}`}
                  >

                    <div className="module-icon">
                      <Boxes size={18} />
                    </div>

                    <h3>{module.name}</h3>

                    <p>
                      {module.responsibility}
                    </p>

                    {module.dependencies?.length > 0 && (

                      <div className="tag-row">

                        {module.dependencies.map(
                          (dependency) => (

                            <span
                              className="tag"
                              key={dependency}
                            >
                              {dependency}
                            </span>

                          )
                        )}

                      </div>

                    )}

                  </div>

                )
              )}

            </div>

          </section>


          <section className="panel">

            <div className="panel-header">

              <div>

                <span className="panel-kicker">
                  DATABASE
                </span>

                <h2>Database Design</h2>

              </div>

            </div>

            <div className="table-like">

              {(architecture.database_design || []).map(
                (collection, index) => (

                  <div
                    className="data-row"
                    key={`${collection.collection}-${index}`}
                  >

                    <strong>
                      {collection.collection}
                    </strong>

                    <span>
                      {collection.purpose}
                    </span>

                    <small>
                      {collection.fields?.join(", ")}
                    </small>

                  </div>

                )
              )}

            </div>

          </section>


          <section className="panel">

            <div className="panel-header">

              <div>

                <span className="panel-kicker">
                  API
                </span>

                <h2>API Design</h2>

              </div>

            </div>

            <div className="api-list">

              {(architecture.api_design || []).map(
                (api, index) => (

                  <div
                    className="api-row"
                    key={`${api.method}-${api.endpoint}-${index}`}
                  >

                    <span className="method-badge">
                      {api.method}
                    </span>

                    <code>
                      {api.endpoint}
                    </code>

                    <span>
                      {api.purpose}
                    </span>

                  </div>

                )
              )}

            </div>

          </section>


          <section className="panel">

            <div className="panel-header">

              <div>

                <span className="panel-kicker">
                  PROJECT STRUCTURE
                </span>

                <h2>Folder Structure</h2>

              </div>

            </div>

            <pre className="code-preview">
{(architecture.folder_structure || []).join("\n")}
            </pre>

          </section>


          <section className="detail-grid">

            <section className="panel">

              <span className="panel-kicker">
                ASSUMPTIONS
              </span>

              <h2>Architecture assumptions</h2>

              <ul className="artifact-list">

                {(architecture.assumptions || []).map(
                  (item, index) => (
                    <li key={`${index}-${item}`}>
                      {item}
                    </li>
                  )
                )}

              </ul>

            </section>


            <section className="panel">

              <span className="panel-kicker">
                OPEN QUESTIONS
              </span>

              <h2>Needs clarification</h2>

              <ul className="artifact-list">

                {(architecture.open_questions || []).map(
                  (item, index) => (
                    <li key={`${index}-${item}`}>
                      {item}
                    </li>
                  )
                )}

              </ul>

            </section>

          </section>


          <section className="panel approval-panel">

            <div>

              <span className="panel-kicker">
                HUMAN-IN-THE-LOOP
              </span>

              <h2>Architecture approval</h2>

              <p className="muted">
                Review the architecture before allowing
                the Developer Agent to generate source code.
              </p>

            </div>

            <div className="button-stack">
            <button
  className="secondary-button"
  onClick={openRevisionModal}
  disabled={
    requestingRevision ||
    approvingArchitecture
  }
>
  Request Revision
</button>

  <button
    className="primary-button"
    onClick={handleApproveArchitecture}
    disabled={
      approvingArchitecture ||
      requestingRevision
    }
  >
    {approvingArchitecture
      ? "Approving..."
      : "Approve Architecture"}
  </button>
</div>

          </section>

        </>

      )}
            {showRevisionModal && (
        <div
          className="modal-backdrop"
          onClick={closeRevisionModal}
        >
          <div
            className="modal-card"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="panel-kicker">
                  ARCHITECT REVISION
                </span>

                <h2>What should the Architect change?</h2>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="revision-feedback">
                Revision feedback
              </label>

              <textarea
                id="revision-feedback"
                rows={6}
                value={revisionFeedback}
                onChange={(event) =>
                  setRevisionFeedback(event.target.value)
                }
                placeholder="Example: Simplify the architecture, remove unnecessary services, and keep MongoDB as the database."
                disabled={requestingRevision}
              />
            </div>

            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={closeRevisionModal}
                disabled={requestingRevision}
              >
                Cancel
              </button>

              <button
                className="primary-button"
                onClick={handleRequestRevision}
                disabled={
                  requestingRevision ||
                  !revisionFeedback.trim()
                }
              >
                {requestingRevision
                  ? "Architect is revising..."
                  : "Revise Architecture"}
              </button>
            </div>
          </div>
        </div>
      )}
      {selectedVersion && (
  <div
    className="modal-backdrop"
    onClick={() => setSelectedVersion(null)}
  >
    <div
      className="modal-card"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="modal-header">
        <div>
          <span className="panel-kicker">
            ARCHITECTURE VERSION
          </span>

          <h2>
            Version {selectedVersion.version}
          </h2>
        </div>
      </div>

      {selectedVersion.revision_feedback && (
        <div className="revision-feedback">
          <strong>Revision feedback</strong>

          <p>
            {selectedVersion.revision_feedback}
          </p>
        </div>
      )}

      {selectedVersion.changes_made?.length > 0 && (
        <div className="version-changes">
          <span className="panel-kicker">
            CHANGES MADE
          </span>

          <ul>
            {selectedVersion.changes_made.map(
              (change, index) => (
                <li key={index}>
                  {change}
                </li>
              )
            )}
          </ul>
        </div>
      )}

      <div className="modal-actions">
        <button
          className="secondary-button"
          onClick={() => setSelectedVersion(null)}
        >
          Close
        </button>

        {selectedVersion.version !==
          architecture?.version && (
          <button
            className="primary-button"
            onClick={() => {
              setSelectedVersion(null);
              handleRestoreVersion(
                selectedVersion.version
              );
            }}
          >
            Restore This Version
          </button>
        )}
      </div>
    </div>
  </div>
)}

    </div>
  );
}

function Artifact({ icon, title, value }) {

  return (

    <div className="panel artifact-card">

      <div className="artifact-icon">
        {icon}
      </div>

      <span className="panel-kicker">
        {title}
      </span>

      <strong>
        {value || "Not specified"}
      </strong>

    </div>

  );
}