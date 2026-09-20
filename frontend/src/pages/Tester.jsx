import { useEffect, useState } from "react";
import {
  CheckCircle2,
  FlaskConical,
  Plus,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { useProject } from "../context/ProjectContext";

import {
  generateTests,
  getTests,
  addCustomTest,
  runTests,
  approveTests,
} from "../services/api";

export default function Tester() {
  const { project, setProject } = useProject();

  const [testerRun, setTesterRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [addingTest, setAddingTest] = useState(false);
  const [runningTests, setRunningTests] = useState(false);
  const [approvingTests, setApprovingTests] = useState(false);
  const [error, setError] = useState("");

  const [showTests, setShowTests] = useState(false);
  const [showCustomForm, setShowCustomForm] = useState(false);

  const [customTest, setCustomTest] = useState({
    title: "",
    description: "",
    test_type: "FUNCTIONAL",
    priority: "MEDIUM",
    steps: "",
    expected_result: "",
  });

  useEffect(() => {
    if (project?.id) {
      loadTests();
    }
  }, [project?.id]);

  async function loadTests() {
    if (!project?.id) return;

    try {
      setError("");

      const result = await getTests(project.id);

      if (result?.status === "NOT_GENERATED") {
        setTesterRun(null);
      } else {
        setTesterRun(result);
      }
    } catch (err) {
      setError(err.message || "Failed to load tester results.");
    }
  }

  async function handleGenerateTests() {
    if (!project?.id) return;

    setLoading(true);
    setError("");

    try {
      const result = await generateTests(project.id);

      console.log("[Tester UI] Generate response:", result);

      setTesterRun(result);

      setProject((current) => ({
        ...current,
        status: "TESTS_READY",
        currentAgent: "HUMAN_APPROVAL",
      }));
    } catch (err) {
      console.error("[Tester UI] Generate error:", err);
      setError(err.message || "Failed to generate tests.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAddCustomTest(event) {
    event.preventDefault();

    if (!project?.id) return;

    setAddingTest(true);
    setError("");

    try {
      const result = await addCustomTest(project.id, {
        ...customTest,
        steps: customTest.steps
          .split("\n")
          .map((step) => step.trim())
          .filter(Boolean),
      });

      console.log("[Tester UI] Custom test response:", result);

      setTesterRun(result);

      setCustomTest({
        title: "",
        description: "",
        test_type: "FUNCTIONAL",
        priority: "MEDIUM",
        steps: "",
        expected_result: "",
      });

      setShowCustomForm(false);
    } catch (err) {
      console.error("[Tester UI] Custom test error:", err);
      setError(err.message || "Failed to add custom test.");
    } finally {
      setAddingTest(false);
    }
  }

  async function handleRunTests() {
    if (!project?.id || !testerRun) return;

    setRunningTests(true);
    setError("");

    try {
      const result = await runTests(project.id);

      console.log("[Tester UI] Run response:", result);

      /*
       * IMPORTANT
       *
       * The backend should return the COMPLETE tester run.
       *
       * But this also protects the UI if an older backend returns
       * only execution information.
       */
      if (
        result &&
        Array.isArray(result.test_cases)
      ) {
        setTesterRun(result);
      } else {
        /*
         * Old backend response:
         *
         * {
         *   status,
         *   passed,
         *   failed,
         *   results
         * }
         *
         * Preserve the existing test plan and merge execution data.
         */
        setTesterRun((current) => ({
          ...current,
          status: result?.status || current?.status,
          results: result?.results || current?.results || [],
          passed_count:
            result?.passed_count ??
            result?.passed ??
            current?.passed_count ??
            0,
          failed_count:
            result?.failed_count ??
            result?.failed ??
            current?.failed_count ??
            0,
          error_count:
            result?.error_count ??
            current?.error_count ??
            0,
          not_executable_count:
            result?.not_executable_count ??
            current?.not_executable_count ??
            0,
          execution:
            result?.execution ??
            current?.execution ??
            null,
        }));
      }

      const failed =
        result?.failed_count ??
        result?.failed ??
        0;

      const errors =
        result?.error_count ??
        0;

      setProject((current) => ({
        ...current,
        status:
          failed > 0 || errors > 0
            ? "TESTS_FAILED"
            : "TESTS_COMPLETED",
        currentAgent:
          failed > 0 || errors > 0
            ? "DEVELOPER"
            : "HUMAN_APPROVAL",
      }));

      /*
       * Reload the complete tester run from MongoDB.
       *
       * This guarantees that the UI contains:
       * - test_cases
       * - version
       * - summary
       * - executable_test_files
       * - execution
       * - results
       * - counts
       */
      await loadTests();
    } catch (err) {
      console.error("[Tester UI] Run error:", err);
      setError(err.message || "Failed to execute tests.");
    } finally {
      setRunningTests(false);
    }
  }

  async function handleApproveTests() {
    if (!project?.id || !testerRun) return;
    setApprovingTests(true);
    setError("");
    try {
      const result = await approveTests(project.id);
      setProject((current) => ({
        ...current,
        status: result.status,
        currentAgent: result.current_agent,
      }));
    } catch (err) {
      setError(err.message || "Tests must pass before approval.");
    } finally {
      setApprovingTests(false);
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
              running the Tester Agent.
            </p>
          </div>
        </section>
      </div>
    );
  }

  const testCases = Array.isArray(testerRun?.test_cases)
    ? testerRun.test_cases
    : [];

  const aiTests = testCases.filter(
    (test) => test.source === "AI"
  );

  const customTests = testCases.filter(
    (test) => test.source === "USER"
  );

  const execution = testerRun?.execution || null;

  const passedCount =
    testerRun?.passed_count ??
    execution?.parsed_passed ??
    execution?.passed ??
    0;

  const failedCount =
    testerRun?.failed_count ??
    execution?.parsed_failed ??
    execution?.failed ??
    0;

  const errorCount =
    testerRun?.error_count ??
    execution?.parsed_errors ??
    execution?.errors ??
    0;

  const notExecutableCount =
    testerRun?.not_executable_count ??
    testCases.filter(
      (test) => test.status === "NOT_EXECUTABLE"
    ).length;

  return (
    <div className="agent-page">

      {/* ====================================================== */}
      {/* TITLE */}
      {/* ====================================================== */}

      <section className="page-title">
        <span className="eyebrow">
          AGENT 04
        </span>

        <h1>Tester Agent</h1>

        <p>
          Analyzes the generated software, creates meaningful
          test cases, and prepares the project for validation.
        </p>
      </section>

      {/* ====================================================== */}
      {/* PROJECT */}
      {/* ====================================================== */}

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">
              PROJECT
            </span>

            <h2>
              {project.name}
            </h2>
          </div>

          <button
            className="primary-button"
            onClick={handleGenerateTests}
            disabled={loading}
          >
            <FlaskConical size={18} />

            {loading
              ? "Tester is analyzing..."
              : testerRun
              ? "Regenerate Tests"
              : "Generate Tests"}
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

      {/* ====================================================== */}
      {/* OUTPUT */}
      {/* ====================================================== */}

      <div className="detail-grid">

        <section className="panel large-panel">

          <div className="panel-header">

            <div>
              <span className="panel-kicker">
                TESTER OUTPUT
              </span>

              <h2>
                Test plan
              </h2>
            </div>

            <span className="status-pill active">
              <span className="status-dot" />

              {testerRun
                ? testerRun.status || "Generated"
                : "Ready"}
            </span>

          </div>

          {!testerRun ? (

            <div className="empty-state">
              <p>
                No tests generated yet.
              </p>

              <small>
                Generate tests to have the Tester Agent
                analyze the Developer project.
              </small>
            </div>

          ) : (

            <>

              <p className="muted">
                {testerRun.summary ||
                  "Tester Agent generated test cases for the project."}
              </p>

              <div className="artifact-grid">

                <div className="panel artifact-card">

                  <span className="panel-kicker">
                    AI TESTS
                  </span>

                  <strong>
                    {aiTests.length}
                  </strong>

                </div>

                <div className="panel artifact-card">

                  <span className="panel-kicker">
                    CUSTOM TESTS
                  </span>

                  <strong>
                    {customTests.length}
                  </strong>

                </div>

                <div className="panel artifact-card">

                  <span className="panel-kicker">
                    TOTAL
                  </span>

                  <strong>
                    {testCases.length}
                  </strong>

                </div>

              </div>

            </>

          )}

        </section>

        {/* ================================================== */}
        {/* DECISION GATE */}
        {/* ================================================== */}

        <section className="panel">

          <div className="panel-header">

            <div>
              <span className="panel-kicker">
                DECISION GATE
              </span>

              <h2>
                Human review
              </h2>
            </div>

          </div>

          <p className="muted">
            Review the generated test cases before
            executing them against the project.
          </p>

          <div className="button-stack">

            <button
              className="secondary-button"
              disabled={!testerRun || testCases.length === 0}
              onClick={() => setShowTests(true)}
            >
              View all test cases
            </button>

            <button
              className="secondary-button"
              disabled={!testerRun}
              onClick={() => setShowCustomForm(true)}
            >
              <Plus size={16} />
              Add custom test case
            </button>

            <button
              className="secondary-button"
              disabled={
                !testerRun ||
                testCases.length === 0 ||
                runningTests
              }
              onClick={handleRunTests}
            >
              <RefreshCw size={16} />

              {runningTests
                ? "Running tests..."
                : "Run tests"}
            </button>

            <button
              className="primary-button"
              disabled={
                approvingTests ||
                !testerRun ||
                testerRun?.execution?.status !== "PASSED" ||
                Number(testerRun?.failed_count || 0) > 0 ||
                Number(testerRun?.error_count || 0) > 0 ||
                Number(testerRun?.not_executable_count || 0) > 0
              }
              onClick={handleApproveTests}
            >
              {approvingTests ? "Approving..." : "Approve & continue to Reviewer"}
            </button>

          </div>

        </section>

      </div>

      {/* ====================================================== */}
      {/* TEST CASE MODAL */}
      {/* ====================================================== */}

      {showTests && testerRun && (

        <div
          className="modal-backdrop"
          onClick={() => setShowTests(false)}
        >

          <div
            className="code-modal"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            <div className="modal-header">

              <div>

                <span className="panel-kicker">
                  TEST CASES
                </span>

                <h2>
                  Test Plan v{testerRun.version || "1"}
                </h2>

              </div>

              <button
                className="icon-button"
                onClick={() => setShowTests(false)}
              >
                ×
              </button>

            </div>

            <div className="test-case-list">

              {testCases.length === 0 ? (

                <div className="empty-state">
                  <p>
                    No test cases available.
                  </p>
                </div>

              ) : (

                testCases.map((test) => (

                  <article
                    className="panel test-case-card"
                    key={test.test_id}
                  >

                    <div className="test-case-header">

                      <div>

                        <span className="panel-kicker">
                          {test.test_id} · {test.source}
                        </span>

                        <h3>
                          {test.title}
                        </h3>

                      </div>

                      <span className="project-status-badge">
                        {test.priority}
                      </span>

                    </div>

                    <p className="muted">
                      {test.description}
                    </p>

                    <strong>
                      Steps
                    </strong>

                    <ol>

                      {(test.steps || []).map(
                        (step, index) => (
                          <li key={index}>
                            {step}
                          </li>
                        )
                      )}

                    </ol>

                    <div className="expected-result">

                      <strong>
                        Expected result
                      </strong>

                      <p>
                        {test.expected_result}
                      </p>

                    </div>

                    {test.status && (
                      <div style={{ marginTop: "12px" }}>
                        <strong>
                          Status:
                        </strong>{" "}
                        {test.status}
                      </div>
                    )}

                  </article>

                ))

              )}

            </div>

            <div className="modal-actions">

              <button
                className="secondary-button"
                onClick={() => setShowTests(false)}
              >
                Close
              </button>

            </div>

          </div>

        </div>

      )}

      {/* ====================================================== */}
      {/* CUSTOM TEST FORM */}
      {/* ====================================================== */}

      {showCustomForm && (

        <div
          className="modal-backdrop"
          onClick={() => setShowCustomForm(false)}
        >

          <form
            className="modal-card"
            onSubmit={handleAddCustomTest}
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            <div className="modal-header">

              <div>

                <span className="panel-kicker">
                  CUSTOM TEST
                </span>

                <h2>
                  Add test case
                </h2>

              </div>

              <button
                type="button"
                className="icon-button"
                onClick={() =>
                  setShowCustomForm(false)
                }
              >
                ×
              </button>

            </div>

            <label>
              Test title

              <input
                value={customTest.title}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    title: event.target.value,
                  })
                }
                required
              />
            </label>

            <label>
              Description

              <textarea
                value={customTest.description}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    description:
                      event.target.value,
                  })
                }
                rows={3}
                required
              />
            </label>

            <label>
              Test type

              <select
                value={customTest.test_type}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    test_type:
                      event.target.value,
                  })
                }
              >
                <option value="FUNCTIONAL">
                  Functional
                </option>

                <option value="API">
                  API
                </option>

                <option value="SECURITY">
                  Security
                </option>

                <option value="EDGE_CASE">
                  Edge Case
                </option>
              </select>
            </label>

            <label>
              Priority

              <select
                value={customTest.priority}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    priority:
                      event.target.value,
                  })
                }
              >
                <option value="HIGH">
                  High
                </option>

                <option value="MEDIUM">
                  Medium
                </option>

                <option value="LOW">
                  Low
                </option>
              </select>
            </label>

            <label>
              Steps

              <small>
                Enter one step per line.
              </small>

              <textarea
                value={customTest.steps}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    steps: event.target.value,
                  })
                }
                rows={6}
                required
              />
            </label>

            <label>
              Expected result

              <textarea
                value={customTest.expected_result}
                onChange={(event) =>
                  setCustomTest({
                    ...customTest,
                    expected_result:
                      event.target.value,
                  })
                }
                rows={4}
                required
              />
            </label>

            <div className="modal-actions">

              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setShowCustomForm(false)
                }
              >
                Cancel
              </button>

              <button
                className="primary-button"
                disabled={addingTest}
              >
                {addingTest
                  ? "Adding..."
                  : "Add Test Case"}
              </button>

            </div>

          </form>

        </div>

      )}

      {/* ====================================================== */}
      {/* TEST EXECUTION RESULTS */}
      {/* ====================================================== */}

      {execution && (

        <section
          className="panel"
          style={{ marginTop: "16px" }}
        >

          <div className="section-header">

            <div>

              <span className="eyebrow">
                TEST EXECUTION
              </span>

              <h2>
                Execution results
              </h2>

            </div>

            <span className="status-badge">
              {testerRun?.status ||
                execution.status ||
                "UNKNOWN"}
            </span>

          </div>

          <div className="stats-grid">

            <div className="stat-card">
              <span>Passed</span>
              <strong>
                {passedCount}
              </strong>
            </div>

            <div className="stat-card">
              <span>Failed</span>
              <strong>
                {failedCount}
              </strong>
            </div>

            <div className="stat-card">
              <span>Errors</span>
              <strong>
                {errorCount}
              </strong>
            </div>

            <div className="stat-card">
              <span>Not executable</span>
              <strong>
                {notExecutableCount}
              </strong>
            </div>

          </div>

          <div style={{ marginTop: "16px" }}>

            <p>
              <strong>
                Framework:
              </strong>{" "}
              {execution.framework || "N/A"}
            </p>

            <p>
              <strong>
                Command:
              </strong>{" "}
              {execution.command || "N/A"}
            </p>

            <p>
              <strong>
                Exit code:
              </strong>{" "}
              {execution.exit_code ?? "N/A"}
            </p>

          </div>

          {execution.output && (

            <details style={{ marginTop: "16px" }}>

              <summary>
                View test execution output
              </summary>

              <pre
                style={{
                  marginTop: "12px",
                  whiteSpace: "pre-wrap",
                  overflowX: "auto",
                }}
              >
                {execution.output}
              </pre>

            </details>

          )}

          {testerRun?.results?.length > 0 && (

            <div style={{ marginTop: "20px" }}>

              <h3>
                Test results
              </h3>

              {testerRun.results.map((result, index) => (

                <div
                  key={`${result.test_id || "result"}-${index}`}
                  style={{
                    padding: "12px 0",
                    borderBottom:
                      "1px solid rgba(255,255,255,0.08)",
                  }}
                >

                  <strong>
                    {result.test_id ||
                      result.path ||
                      `Result ${index + 1}`}
                  </strong>

                  {result.title && (
                    <div>
                      {result.title}
                    </div>
                  )}

                  <small>
                    {result.status}
                  </small>

                  {result.message && (
                    <div>
                      {result.message}
                    </div>
                  )}

                  {result.stdout && (
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        marginTop: "8px",
                      }}
                    >
                      {result.stdout}
                    </pre>
                  )}

                  {result.stderr && (
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        marginTop: "8px",
                      }}
                    >
                      {result.stderr}
                    </pre>
                  )}

                </div>

              ))}

            </div>

          )}

        </section>

      )}

      {/* ====================================================== */}
      {/* ACTIVITY */}
      {/* ====================================================== */}

      <section className="panel">

        <div className="panel-header">

          <div>

            <span className="panel-kicker">
              ACTIVITY
            </span>

            <h2>
              Agent history
            </h2>

          </div>

        </div>

        <div className="empty-state">

          {testerRun ? (

            <>
              <CheckCircle2 size={24} />

              <p>
                Tester Agent generated{" "}
                {testCases.length} test cases.
              </p>

              <small>
                Test plan version{" "}
                {testerRun.version || 1}
              </small>
            </>

          ) : (

            <>
              <XCircle size={24} />

              <p>
                No tester runs yet.
              </p>

              <small>
                Generate tests to start the
                Tester Agent.
              </small>
            </>

          )}

        </div>

      </section>

    </div>
  );
}