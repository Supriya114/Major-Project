import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, FileCode2, RefreshCw, Play as PlayIcon } from "lucide-react";
import { useProject } from "../context/ProjectContext";
import { getDeveloperProject, getExportProjectUrl } from "../services/api";

export default function GeneratedProject() {
  const { project } = useProject();
  const navigate = useNavigate();
  const [developerProject, setDeveloperProject] = useState(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const projectId = project?.id || project?._id;

  async function load() {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const result = await getDeveloperProject(projectId);
      setDeveloperProject(result?.status === "NOT_GENERATED" ? null : result);
      setSelected(0);
    } catch (err) {
      setError(err.message || "Failed to load generated project.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [projectId]);

  const files = developerProject?.files || [];
  const folders = useMemo(() => {
    const result = {};
    for (const file of files) {
      const first = (file.path || "").split("/")[0] || "root";
      result[first] = (result[first] || 0) + 1;
    }
    return result;
  }, [files]);

  if (!projectId) return <div className="agent-page"><section className="panel"><div className="empty-state"><h3>No project selected</h3><p>Select a project from the Dashboard first.</p></div></section></div>;

  return (
    <div className="agent-page">
      <section className="page-title">
        <span className="eyebrow">PROJECT</span>
        <h1>Generated Project</h1>
        <p>Browse the complete Developer Agent output, inspect every generated file, and download the same project as a ZIP.</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="panel-kicker">GENERATED VERSION</span>
            <h2>{developerProject?.project_summary || project.name}</h2>
          </div>
          <div className="button-row">
            <button className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={16} /> Refresh</button>
            {developerProject && (
              <>
                <button className="secondary-button" onClick={() => navigate("/preview")}><PlayIcon /> Open Preview</button>
                <a className="primary-button" href={getExportProjectUrl(projectId)}><Download size={16} /> Download ZIP</a>
              </>
            )}
          </div>
        </div>
        {error && <div className="error-box">{error}</div>}
        {!developerProject && !loading && <div className="empty-state"><FileCode2 size={28}/><h3>No generated version</h3><p>Generate the project from the Developer Agent first.</p></div>}
        {developerProject && (
          <>
            <div className="artifact-grid">
              <div className="panel artifact-card"><span className="panel-kicker">VERSION</span><strong>{developerProject.version}</strong></div>
              <div className="panel artifact-card"><span className="panel-kicker">FILES</span><strong>{files.length}</strong></div>
              <div className="panel artifact-card"><span className="panel-kicker">FOLDERS</span><strong>{Object.keys(folders).length}</strong></div>
              <div className="panel artifact-card"><span className="panel-kicker">TEST SUGGESTIONS</span><strong>{developerProject.test_suggestions?.length || 0}</strong></div>
            </div>

            <div className="code-viewer" style={{ marginTop: 20 }}>
              <aside className="code-file-list">
                <div className="code-file-list-title"><span>FILES</span><strong>{files.length}</strong></div>
                {files.map((file, index) => (
                  <button key={`${file.path}-${index}`} className={`code-file-item ${selected === index ? "selected" : ""}`} onClick={() => setSelected(index)}>
                    <FileCode2 size={15}/><span>{file.path}</span>
                  </button>
                ))}
              </aside>
              <section className="code-content">
                {files[selected] ? (
                  <>
                    <div className="code-content-header"><div><strong>{files[selected].path}</strong><span>{files[selected].language}</span></div><small>File {selected + 1} of {files.length}</small></div>
                    <pre className="code-preview">{files[selected].content}</pre>
                  </>
                ) : <div className="empty-state"><p>No file selected.</p></div>}
              </section>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
