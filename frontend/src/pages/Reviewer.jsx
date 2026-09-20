import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { useProject } from "../context/ProjectContext";
import {
  generateReview,
  getReview,
  approveReview,
  requestDeveloperFixes,
} from "../services/api";


export default function Reviewer() {
  const { project, setProject } = useProject();
  const navigate = useNavigate();

  const projectId = project?.id || project?._id;
 

  const [reviewRun, setReviewRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showReview, setShowReview] = useState(false);

  async function loadReview() {
    if (!projectId) return;

    setError("");
    try {
      const result = await getReview(projectId);
      setReviewRun(result.status !== "NOT_GENERATED" ? result : null);
    } catch (err) {
      setError(err.message || "Could not load the Reviewer Agent.");
    }
  }

  useEffect(() => {
    loadReview();
  }, [projectId]);

  async function handleGenerateReview() {
    if (!projectId) return;

    setLoading(true);
    setError("");

    try {
      const result = await generateReview(projectId);

      setReviewRun(result);

      setProject((current) => ({
        ...current,
        status: "REVIEW_READY",
        currentAgent: "REVIEWER",
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    if (!projectId || !reviewRun) return;

    setLoading(true);
    setError("");

    try {
      await approveReview(projectId);
      setProject((current) => ({
        ...current,
        status: "PROJECT_COMPLETED",
        currentAgent: "HUMAN_APPROVAL",
      }));
      navigate("/generated-project");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }
  const handleDeveloperFixes = async () => {
    if (!reviewRun) return;
  
    try {
      setLoading(true);
      setError("");
  
      await requestDeveloperFixes(projectId);
  
      alert("Developer fixes requested successfully.");
    } catch (err) {
      setError(
        err.response?.data?.message ||
        err.message ||
        "Failed to request Developer fixes."
      );
    } finally {
      setLoading(false);
    }
  };

  if (!projectId) {
    return (
      <div className="agent-page">
        <section className="panel">
          <div className="empty-state">
            <h3>No project selected</h3>
            <p>Select a project before using the Reviewer Agent.</p>
          </div>
        </section>
      </div>
    );
  }

  const review = reviewRun?.review;

  return (
    <div className="agent-page">

      <section className="page-title">
        <span className="eyebrow">AGENT 05</span>
        <h1>Reviewer Agent</h1>
        <p>
          Reviews generated code for quality, security,
          maintainability, and architecture compliance.
        </p>
      </section>

      <div className="detail-grid">

        <section className="panel large-panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">AGENT OUTPUT</span>
              <h2>Code review</h2>
            </div>

            <span className="status-pill active">
              <span className="status-dot" />
              {reviewRun ? "Completed" : "Ready"}
            </span>
          </div>

          {review ? (
            <div className="artifact-list">

              <li>
                Code quality score:{" "}
                <strong>{review.quality_score}/10</strong>
              </li>

              <li>
                Security score:{" "}
                <strong>{review.security_score}/10</strong>
              </li>

              <li>
                Maintainability score:{" "}
                <strong>{review.maintainability_score}/10</strong>
              </li>

              <li>
                Architecture:{" "}
                <strong>{review.architecture_compliance}</strong>
              </li>

              <li>
                Recommendation:{" "}
                <strong>{review.recommendation}</strong>
              </li>

            </div>
          ) : (
            <ul className="artifact-list">
              <li>Code quality score</li>
              <li>Security findings</li>
              <li>Maintainability findings</li>
              <li>Architecture compliance</li>
              <li>Severity-based issues</li>
              <li>Improvement suggestions</li>
              <li>Final approval/rejection</li>
            </ul>
          )}
        </section>


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
            Review the generated software before final approval.
          </p>

          {error && (
            <div className="error-box">
              <p className="error-text">{error}</p>
              <button className="secondary-button" onClick={loadReview} disabled={loading}>
                <RefreshCw size={16} /> Retry connection
              </button>
            </div>
          )}

          <div className="button-stack">

            <button
              className="secondary-button"
              disabled={!reviewRun}
              onClick={() => setShowReview(!showReview)}
            >
              {showReview ? "Hide review" : "View review"}
            </button>

            <button
  className="secondary-button"
  disabled={!reviewRun || loading}
  onClick={handleDeveloperFixes}
>
  {loading ? "Requesting fixes..." : "Request Developer fixes"}
</button>

            <button
              className="secondary-button"
              disabled={!reviewRun || loading}
              onClick={handleApprove}
            >
              {loading ? "Saving approval..." : "Approve project"}
            </button>

          </div>

        </section>

      </div>


      {!reviewRun && (
        <section className="panel">
          <div className="button-stack">

            <button
              className="primary-button"
              onClick={handleGenerateReview}
              disabled={loading}
            >
              <RefreshCw size={16} />

              {loading
                ? "Reviewer is analyzing..."
                : "Run Reviewer Agent"}
            </button>

          </div>
        </section>
      )}


      {showReview && review && (
        <section className="panel">

          <div className="panel-header">
            <div>
              <span className="panel-kicker">
                REVIEW RESULTS
              </span>
              <h2>{review.summary}</h2>
            </div>
          </div>

          <h3>Findings</h3>

          <div className="artifact-list">
            {review.findings?.map((finding, index) => (
              <li key={index}>
                <strong>
                  [{finding.severity}] {finding.title}
                </strong>

                <p className="muted">
                  {finding.description}
                </p>

                <p>
                  <strong>Suggestion:</strong>{" "}
                  {finding.suggestion}
                </p>
              </li>
            ))}
          </div>

          <h3>Improvement suggestions</h3>

          <ul className="artifact-list">
            {review.improvement_suggestions?.map(
              (suggestion, index) => (
                <li key={index}>
                  {suggestion}
                </li>
              )
            )}
          </ul>

        </section>
      )}


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
          <p>
            {reviewRun
              ? "Reviewer Agent completed a code review."
              : "No agent runs yet."}
          </p>
        </div>

      </section>

    </div>
  );
}
