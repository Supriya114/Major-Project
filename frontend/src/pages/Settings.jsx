import { useState } from "react";
import { checkHealth } from "../services/api";

export default function Settings() {
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);

  async function testBackend() {
    setChecking(true);
    try {
      setResult(await checkHealth());
    } catch (error) {
      setResult({ status: "error", detail: error.message });
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="agent-page">
      <section className="page-title">
        <span className="eyebrow">CONFIGURATION</span>
        <h1>Settings</h1>
        <p>
          Service configuration for the local development environment. Secrets
          stay in the backend <code>.env</code> file and are never stored in the
          frontend.
        </p>
      </section>

      <div className="settings-grid">
        <section className="panel">
          <span className="panel-kicker">DATABASE</span>
          <h2>MongoDB Atlas</h2>
          <p className="muted">
            Add your Atlas connection string in <strong>backend/.env</strong>.
          </p>
          <div className="config-row"><span>Variable</span><strong>MONGODB_URI</strong></div>
          <div className="config-row"><span>Database</span><strong>DATABASE_NAME=ai_software_team</strong></div>
        </section>

        <section className="panel">
          <span className="panel-kicker">AI PROVIDER</span>
          <h2>Gemini (recommended first)</h2>
          <p className="muted">
            Create an API key, then put it in backend/.env. The Product Manager
            Agent uses the configured provider.
          </p>
          <div className="config-row"><span>Provider</span><strong>AI_PROVIDER=gemini</strong></div>
          <div className="config-row"><span>Key</span><strong>GEMINI_API_KEY=...</strong></div>
          <div className="config-row"><span>Model</span><strong>GEMINI_MODEL=gemini-3.8-flash</strong></div>
        </section>

        <section className="panel">
          <span className="panel-kicker">ALTERNATIVE</span>
          <h2>OpenRouter</h2>
          <p className="muted">
            If you prefer OpenRouter, switch AI_PROVIDER to openrouter and add
            OPENROUTER_API_KEY. The default model is openrouter/free.
          </p>
          <div className="config-row"><span>Provider</span><strong>AI_PROVIDER=openrouter</strong></div>
          <div className="config-row"><span>Key</span><strong>OPENROUTER_API_KEY=...</strong></div>
          <div className="config-row"><span>Model</span><strong>OPENROUTER_MODEL=openrouter/free</strong></div>
        </section>

        <section className="panel">
          <span className="panel-kicker">CONNECTION TEST</span>
          <h2>Backend + database</h2>
          <p className="muted">
            Verify FastAPI can reach MongoDB Atlas. AI connection testing will
            be added with the provider settings flow.
          </p>
          <button className="primary-button" onClick={testBackend} disabled={checking}>
            {checking ? "Checking..." : "Test connection"}
          </button>
          {result && <pre className="json-result">{JSON.stringify(result, null, 2)}</pre>}
        </section>
      </div>
    </div>
  );
}
