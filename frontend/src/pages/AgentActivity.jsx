import { AlertTriangle, CheckCircle2, GitBranch } from "lucide-react";
import { useProject } from "../context/ProjectContext";

const events = [
  ["PM", "Product Manager", "Waiting for a project to start.", "pending"],
  ["DEV", "Developer", "Will evaluate requirements for implementation feasibility.", "pending"],
  ["ARCH", "Architect", "Will design the technical architecture.", "pending"],
  ["DEV", "Developer", "Will evaluate architecture before implementation.", "pending"],
  ["CODE", "Developer", "Will generate the project files.", "pending"],
  ["TEST", "Tester", "Will generate and execute visible test cases.", "pending"],
  ["REVIEW", "Reviewer", "Will perform quality and security review.", "pending"],
];

const workflowNodes = [
  { id: "requirements", label: "Requirements", code: "PM" },
  { id: "feasibility", label: "Feasibility", code: "DEV" },
  { id: "architecture", label: "Architecture", code: "ARCH" },
  { id: "development", label: "Development", code: "CODE" },
  { id: "testing", label: "Testing", code: "TEST" },
  { id: "review", label: "Review", code: "QA" },
];

const workflowEdges = workflowNodes.slice(1).map((node, index) => ({
  source: workflowNodes[index].id,
  target: node.id,
}));

function analyzeGraph(nodes, edges) {
  const indegree = Object.fromEntries(nodes.map((node) => [node.id, 0]));
  const adjacency = Object.fromEntries(nodes.map((node) => [node.id, []]));

  edges.forEach(({ source, target }) => {
    adjacency[source].push(target);
    indegree[target] += 1;
  });

  const queue = nodes.filter((node) => indegree[node.id] === 0).map((node) => node.id);
  const order = [];
  while (queue.length) {
    const current = queue.shift();
    order.push(current);
    adjacency[current].forEach((neighbor) => {
      indegree[neighbor] -= 1;
      if (indegree[neighbor] === 0) queue.push(neighbor);
    });
  }

  return {
    order,
    hasCycle: order.length !== nodes.length,
    startNodes: nodes.filter((node) => !edges.some((edge) => edge.target === node.id)),
  };
}

function getNodeStatus(nodeId, currentAgent, projectStatus) {
  if (!currentAgent || projectStatus === "IDLE") return "pending";

  const currentIndex = {
    PRODUCT_MANAGER: 0,
    DEVELOPER: 1,
    ARCHITECT: 2,
    TESTER: 4,
    REVIEWER: 5,
  }[currentAgent];
  const nodeIndex = workflowNodes.findIndex((node) => node.id === nodeId);

  if (currentIndex === undefined) return "pending";
  if (nodeIndex < currentIndex) return "complete";
  if (nodeIndex === currentIndex) return "active";
  return "pending";
}

export default function AgentActivity() {
  const { project } = useProject();
  const graphAnalysis = analyzeGraph(workflowNodes, workflowEdges);

  return (
    <div className="agent-page">
      <section className="page-title">
        <span className="eyebrow">AUDIT TRAIL</span>
        <h1>Agent Activity</h1>
        <p>
          A chronological record of agent actions, decisions, human approvals,
          feedback, and workflow transitions.
        </p>
      </section>

      <section className="panel">
        <div className="activity-toolbar">
          <div>
            <span className="panel-kicker">DIRECTED WORKFLOW GRAPH</span>
            <h2>Agent dependency analysis</h2>
          </div>
          <div className="graph-health">
            {graphAnalysis.hasCycle ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
            {graphAnalysis.hasCycle ? "Cycle detected" : "Valid workflow"}
          </div>
        </div>

        <div className="graph-summary">
          <div><strong>{workflowNodes.length}</strong><span>Nodes</span></div>
          <div><strong>{workflowEdges.length}</strong><span>Dependencies</span></div>
          <div><strong>{graphAnalysis.order.length}</strong><span>Ordered stages</span></div>
          <div><strong>{graphAnalysis.startNodes.length}</strong><span>Entry points</span></div>
        </div>

        <div className="workflow-graph" aria-label="Agent dependency graph">
          {workflowNodes.map((node, index) => (
            <div className="workflow-graph-step" key={node.id}>
              <div className={`workflow-node ${getNodeStatus(node.id, project?.currentAgent, project?.status)}`}>
                <GitBranch size={15} />
                <strong>{node.label}</strong>
                <span>{node.code}</span>
              </div>
              {index < workflowNodes.length - 1 && <div className="workflow-edge" aria-hidden="true">-&gt;</div>}
            </div>
          ))}
        </div>

        <p className="graph-order">
          <strong>Topological order:</strong> {graphAnalysis.order.map((id) => workflowNodes.find((node) => node.id === id).label).join(" -> ")}
        </p>
      </section>

      <section className="panel">
        <div className="activity-toolbar">
          <div>
            <span className="panel-kicker">WORKFLOW TIMELINE</span>
            <h2>Everything the team does</h2>
          </div>
          <select className="select-control" defaultValue="all">
            <option value="all">All agents</option>
            <option value="pm">Product Manager</option>
            <option value="architect">Architect</option>
            <option value="developer">Developer</option>
            <option value="tester">Tester</option>
            <option value="reviewer">Reviewer</option>
            <option value="human">Human actions</option>
          </select>
        </div>

        <div className="timeline">
          {events.map(([code, name, text, status], index) => (
            <div className="timeline-item" key={`${code}-${index}`}>
              <div className={`timeline-node ${status}`}>{code}</div>
              <div className="timeline-content">
                <div className="timeline-meta">
                  <strong>{name}</strong>
                  <span>Stage {index + 1}</span>
                </div>
                <p>{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
