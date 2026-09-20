import { useEffect, useState } from "react";
import { FileCode2, Play, RefreshCw, Square, Download } from "lucide-react";
import { useProject } from "../context/ProjectContext";
import { getDeveloperProject, startPreview, stopPreview, getExportProjectUrl } from "../services/api";

function Placeholder({ title, eyebrow, description, bullets }) {
  return <div className="agent-page"><section className="page-title"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></section><section className="panel"><div className="panel-header"><div><span className="panel-kicker">PLANNED CAPABILITY</span><h2>What this page will contain</h2></div></div><ul className="artifact-list">{bullets.map((item) => <li key={item}>{item}</li>)}</ul></section></div>;
}

export function Preview() {
  const { project } = useProject();
  const [developerProject, setDeveloperProject] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const projectId = project?.id || project?._id;

  async function loadProject() {
    if (!projectId) return;
    setLoading(true); setError(""); setPreview(null);
    try {
      const result = await getDeveloperProject(projectId);
      setDeveloperProject(result?.status === "NOT_GENERATED" ? null : result);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { loadProject(); }, [projectId]);

  async function handleStart() {
    if (!projectId) return;
    setLoading(true); setError("");
    try { setPreview(await startPreview(projectId)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }
  async function handleStop() {
    if (!projectId) return;
    setLoading(true); setError("");
    try { await stopPreview(projectId); setPreview(null); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  if (!projectId) return <Placeholder title="Project Preview" eyebrow="LIVE PREVIEW" description="Select a project to preview its generated application." bullets={["Complete generated frontend", "Detected backend", "Runtime status"]}/>;

  const files = developerProject?.files || [];
  return <div className="agent-page">
    <section className="page-title"><span className="eyebrow">LIVE PREVIEW</span><h1>Project Preview</h1><p>Runs the complete generated frontend from the latest Developer version and starts a detected local backend when available.</p></section>
    <section className="panel">
      <div className="panel-header"><div><span className="panel-kicker">GENERATED PROJECT</span><h2>{developerProject?.project_summary || project.name}</h2></div><div className="button-row">
        <button className="secondary-button" onClick={loadProject} disabled={loading}><RefreshCw size={16}/> Refresh</button>
        {developerProject && <a className="secondary-button" href={getExportProjectUrl(projectId)}><Download size={16}/> ZIP</a>}
        {preview ? <button className="secondary-button" onClick={handleStop} disabled={loading}><Square size={16}/> Stop</button> : <button className="primary-button" onClick={handleStart} disabled={loading || !developerProject}><Play size={16}/> {loading ? "Starting..." : "Start preview"}</button>}
      </div></div>
      {error && <div className="error-box">{error}</div>}
      {!developerProject && !loading && <div className="empty-state"><FileCode2 size={28}/><h3>No generated project yet</h3><p>Generate the project with the Developer Agent first.</p></div>}
      {preview && <>
        <div className="preview-frame-wrap"><div className="preview-frame-toolbar"><span className="status-pill active">Running</span><span className="muted">Version {preview.developer_version} · {preview.file_count} generated files</span>{preview.backend_url && <span className="muted">Backend: {preview.backend_url}</span>}<a href={preview.frontend_url} target="_blank" rel="noreferrer">Open in new tab</a></div><iframe className="preview-frame" src={preview.frontend_url} title="Generated project frontend preview" allow="geolocation; camera; microphone"/></div>
        <div className="notice-box" style={{ marginTop: 16 }}>Preview is serving the generated project itself. The source tree, backend detection, dependencies, and test suite remain available from Generated Project and Tester.</div>
      </>}
    </section>
  </div>;
}

export function Evaluation() { return <Placeholder title="Evaluation" eyebrow="METRICS" description="Measure development time, code quality, and test coverage." bullets={["Development time", "Code quality", "Test coverage", "Bugs detected"]}/>; }
export function ExportProject() {
  const { project } = useProject();
  const id = project?.id || project?._id;
  return <div className="agent-page"><section className="page-title"><span className="eyebrow">DELIVERY</span><h1>Export Project</h1><p>Download the complete latest generated project, including generated tests and setup metadata.</p></section><section className="panel"><div className="button-row"><a className="primary-button" href={id ? getExportProjectUrl(id) : "#"} onClick={(e) => { if (!id) e.preventDefault(); }}><Download size={16}/> Download complete ZIP</a></div>{!id && <p className="muted" style={{marginTop: 16}}>Select a project first.</p>}</section></div>;
}
export function GitHub() { return <Placeholder title="GitHub" eyebrow="VERSION CONTROL" description="Push the generated project to a GitHub repository." bullets={["Connect GitHub securely", "Create repository", "Initialize Git", "Commit generated files", "Push and show repository link"]}/>; }
