const statusLabel = {
  completed: "Completed",
  active: "Working",
  waiting: "Waiting",
  blocked: "Needs attention",
};

export default function AgentCard({
  icon,
  name,
  role,
  status = "waiting",
  description,
}) {
  return (
    <div className={`agent-card ${status}`}>
      <div className="agent-card-top">
        <div className="agent-icon">{icon}</div>
        <span className={`status-pill ${status}`}>
          <span className="status-dot" />
          {statusLabel[status]}
        </span>
      </div>

      <div className="agent-card-body">
        <h3>{name}</h3>
        <p className="agent-role">{role}</p>
        <p>{description}</p>
      </div>
    </div>
  );
}
