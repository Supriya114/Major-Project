import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, LoaderCircle, RefreshCw, Send, Sparkles } from "lucide-react";
import {
  generateDeveloperOpinion,
  generateRequirements,
  getDeveloperOpinion,
  getRequirements,
  updateRequirements,
  approveRequirements,
} from "../services/api";
import { useProject } from "../context/ProjectContext";

export default function ProductManager() {
  const { project, setProject } = useProject();
  const navigate = useNavigate();
  const [requirements, setRequirements] = useState(null);
  const [opinion, setOpinion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [opinionLoading, setOpinionLoading] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [editedRequirements, setEditedRequirements] = useState(null);
  const [savingRevision, setSavingRevision] = useState(false);


  async function loadArtifacts() {
    if (!project?.id) return;
    try {
      const [req, dev] = await Promise.all([
        getRequirements(project?.id),
        getDeveloperOpinion(project?.id),
      ]);
      if (req.status !== "NOT_GENERATED") setRequirements(req);
      if (dev.opinions?.length) setOpinion(dev.opinions[0]);
    } catch {
      // Backend may not be running yet.
    }
  }

  useEffect(() => {
    loadArtifacts();
  }, [project?.id]);

  async function runPM() {
    if (!project?.id) {
      setError("Create a project from the Dashboard first.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const result = await generateRequirements(project?.id);
      setRequirements(result);
      setProject((current) => ({
        ...current,
        status: "REQUIREMENTS_READY",
        currentAgent: "DEVELOPER",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runDeveloperOpinion() {
    if (!project?.id) {
      setError("Create a project from the Dashboard first.");
      return;
    }

    setOpinionLoading(true);
    setError("");

    try {
      const result = await generateDeveloperOpinion(project?.id);
      setOpinion(result);
      setProject((current) => ({
        ...current,
        status: "DEVELOPER_REVIEWED_REQUIREMENTS",
        currentAgent: "HUMAN_APPROVAL",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setOpinionLoading(false);
    }
  }
  function openEditor() {
    if (!requirements) return;
  
    setEditedRequirements(
      JSON.parse(
        JSON.stringify({
          project_summary: requirements.project_summary || "",
          functional_requirements:
            requirements.functional_requirements || [],
          non_functional_requirements:
            requirements.non_functional_requirements || [],
          user_stories: requirements.user_stories || [],
          acceptance_criteria:
            requirements.acceptance_criteria || [],
          assumptions: requirements.assumptions || [],
          clarification_questions:
            requirements.clarification_questions || [],
        })
      )
    );
  
    setEditing(true);
  }
  
  function closeEditor() {
    if (savingRevision) return;
  
    setEditing(false);
    setEditedRequirements(null);
  }
  
  async function saveRevision() {
    if (!project?.id || !editedRequirements) return;
  
    setSavingRevision(true);
    setError("");
  
    try {
      const updated = await updateRequirements(
        project.id,
        editedRequirements
      );
  
      setRequirements(updated);
      setEditing(false);
  
      // Automatically send the revised requirements
      // back to the Developer Agent.
      const developerResult =
        await generateDeveloperOpinion(project.id);
  
      setOpinion(developerResult);
  
      setProject((current) => ({
        ...current,
        status: "DEVELOPER_REVIEWED_REQUIREMENTS",
        currentAgent: "HUMAN_APPROVAL",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingRevision(false);
    }
  }
  const hasProject = Boolean(project?.id);

  return (
    <div className="agent-page">
      <section className="page-title">
        <span className="eyebrow">AGENT 01 · REQUIREMENTS</span>
        <h1>Product Manager Agent</h1>
        <p>
          Converts the user's idea into a structured requirements specification,
          then hands it to the Developer Agent for a feasibility review.
        </p>
      </section>

      {!hasProject && (
        <div className="notice-box">
          <strong>No project selected.</strong> Go to Dashboard → New Project
          first.
        </div>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">INPUT</span>
            <h2>User project requirement</h2>
          </div>
          <button className="primary-button" onClick={runPM} disabled={loading || !hasProject}>
            {loading ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
            {loading ? "Analyzing..." : requirements ? "Regenerate requirements" : "Analyze requirements"}
          </button>
        </div>

        <div className="input-preview">
          <strong>{project.name}</strong>
          <p>{project.description}</p>
        </div>

        {error && <div className="error-box">{error}</div>}
      </section>

      {requirements && (
        <>
          <section className="panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">OUTPUT</span>
                <h2>Requirement specification</h2>
              </div>
              <span className="status-pill completed">
                <span className="status-dot" /> Generated
              </span>
            </div>

            <div className="summary-box">
              <span>PROJECT SUMMARY</span>
              <p>{requirements.project_summary}</p>
            </div>

            <div className="artifact-section">
              <h3>Functional requirements</h3>
              <div className="artifact-grid">
                {requirements.functional_requirements?.map((item) => (
                  <div className="artifact-card" key={item.id}>
                    <div className="artifact-card-title">
                      <strong>{item.id}</strong>
                      <span className={`priority ${item.priority?.toLowerCase()}`}>
                        {item.priority}
                      </span>
                    </div>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="artifact-section">
              <h3>Non-functional requirements</h3>
              <div className="artifact-grid">
                {requirements.non_functional_requirements?.map((item) => (
                  <div className="artifact-card" key={item.id}>
                    <strong>{item.id}</strong>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="artifact-section">
              <h3>User stories</h3>
              <div className="stack-list">
                {requirements.user_stories?.map((item) => (
                  <div className="list-row" key={item.id}>
                    <strong>{item.id}</strong>
                    <span>{item.story}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="two-column-artifacts">
              <div>
                <h3>Acceptance criteria</h3>
                <ul className="check-list">
                  {requirements.acceptance_criteria?.map((item, i) => (
                    <li key={i}><Check size={15} />{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>Assumptions</h3>
                <ul className="plain-list">
                  {requirements.assumptions?.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              </div>
            </div>

            <div className="artifact-section">
              <h3>Clarification questions</h3>
              {requirements.clarification_questions?.length ? (
                <ul className="plain-list">
                  {requirements.clarification_questions.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              ) : (
                <div className="success-box">No clarification questions were identified.</div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <span className="panel-kicker">DEVELOPER GATE</span>
                <h2>Developer feasibility opinion</h2>
              </div>
              <button
                className="secondary-button"
                onClick={runDeveloperOpinion}
                disabled={opinionLoading}
              >
                {opinionLoading ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}
                {opinionLoading ? "Reviewing..." : opinion ? "Run review again" : "Ask Developer"}
              </button>
            </div>

            {!opinion && (
              <div className="empty-state">
                <p>The Developer has not reviewed these requirements yet.</p>
                <small>
                  This is the first agent-to-agent handoff in the workflow.
                </small>
              </div>
            )}

            {opinion && (
              <div className="developer-opinion">
                <div className="opinion-header">
                  <span className={`decision-badge ${opinion.decision === "APPROVED" ? "approved" : "revision"}`}>
                    {opinion.decision}
                  </span>
                  <span className={`feasibility ${opinion.feasibility?.toLowerCase()}`}>
                    Feasibility: {opinion.feasibility}
                  </span>
                </div>
                <p>{opinion.summary}</p>

                <div className="opinion-columns">
                  <div>
                    <h3>Issues</h3>
                    <ul className="plain-list">
                      {(opinion.issues || []).map((item, i) => (
                        <li key={item.id || i}>
                          {typeof item === "string"
                            ? item
                            : `${item.description || "Issue identified"}${item.resolution ? ` - ${item.resolution}` : ""}`}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3>Recommendations</h3>
                    <ul className="plain-list">
                      {(opinion.recommendations || []).map((item, i) => (
                        <li key={item.id || i}>
                          {typeof item === "string"
                            ? item
                            : item.description || item.resolution || "Recommendation provided"}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </section>
        </>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">NEXT STEP</span>
            <h2>Human approval</h2>
          </div>
        </div>
        <p className="muted">
          Approval controls will become active after the Developer review is
          complete. The approved requirement artifact will then be passed to
          the Architect Agent.
        </p>
        <div className="button-row">
        <button
          className="secondary-button"
          onClick={openEditor}
          disabled={!opinion || savingRevision}>
          Edit / Send back
        </button>
          <button
            className="primary-button"
            disabled={!opinion || opinion.decision !== "APPROVED" || loading}
            onClick={async () => {
              try {
                setLoading(true);
                setError("");
                const result = await approveRequirements(project.id);
                setProject((current) => ({ ...current, status: result.status, currentAgent: result.current_agent }));
                navigate("/architect");
              } catch (err) {
                setError(err.message);
              } finally {
                setLoading(false);
              }
            }}
          >
            <Check size={16} /> {loading ? "Continuing..." : "Approve & continue to Architect"}
          </button>
        </div>
      </section>
      {editing && editedRequirements && (
  <div className="modal-backdrop">
    <div className="modal-card" style={{ maxWidth: "900px" }}>
      <div className="modal-header">
        <div>
          <span className="panel-kicker">HUMAN REVISION</span>
          <h2>Edit Requirements</h2>
        </div>

        <button
          className="icon-button"
          onClick={closeEditor}
          disabled={savingRevision}
        >
          ×
        </button>
      </div>

      <p className="muted">
        Review the Product Manager output, make corrections,
        and send the revised requirements back to the Developer Agent.
      </p>

      <div className="form-group">
        <label>Project Summary</label>

        <textarea
          rows={5}
          value={editedRequirements.project_summary}
          onChange={(e) =>
            setEditedRequirements((current) => ({
              ...current,
              project_summary: e.target.value,
            }))
          }
        />
      </div>

      <div className="form-group">
        <label>Acceptance Criteria</label>

        <textarea
          rows={7}
          value={editedRequirements.acceptance_criteria.join("\n")}
          onChange={(e) =>
            setEditedRequirements((current) => ({
              ...current,
              acceptance_criteria: e.target.value
                .split("\n")
                .map((item) => item.trim())
                .filter(Boolean),
            }))
          }
        />

        <small className="muted">
          Put one acceptance criterion per line.
        </small>
      </div>

      <div className="form-group">
        <label>Assumptions</label>

        <textarea
          rows={5}
          value={editedRequirements.assumptions.join("\n")}
          onChange={(e) =>
            setEditedRequirements((current) => ({
              ...current,
              assumptions: e.target.value
                .split("\n")
                .map((item) => item.trim())
                .filter(Boolean),
            }))
          }
        />

        <small className="muted">
          Put one assumption per line.
        </small>
      </div>

      <div className="form-group">
        <label>Clarification Questions</label>

        <textarea
          rows={5}
          value={editedRequirements.clarification_questions.join("\n")}
          onChange={(e) =>
            setEditedRequirements((current) => ({
              ...current,
              clarification_questions: e.target.value
                .split("\n")
                .map((item) => item.trim())
                .filter(Boolean),
            }))
          }
        />

        <small className="muted">
          Put one question per line.
        </small>
      </div>

      <div className="modal-actions">
        <button
          className="secondary-button"
          onClick={closeEditor}
          disabled={savingRevision}
        >
          Cancel
        </button>

        <button
          className="primary-button"
          onClick={saveRevision}
          disabled={savingRevision}
        >
          {savingRevision ? (
            <>
              <LoaderCircle className="spin" size={16} />
              Sending back...
            </>
          ) : (
            <>
              <Send size={16} />
              Save & Send to Developer
            </>
          )}
        </button>
      </div>
    </div>
  </div>
)}

    </div>
  );
}
