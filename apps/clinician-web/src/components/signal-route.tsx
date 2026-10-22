const stages = [
  {
    number: "1",
    title: "Listen",
    detail: "Constrained phone evidence",
    outcome: "Pass",
  },
  {
    number: "2",
    title: "Hold uncertainty",
    detail: "Retry or abstain",
    outcome: "Pause",
  },
  {
    number: "3",
    title: "Look selectively",
    detail: "Supported cues + consent",
    outcome: "Analyze",
  },
] as const;

export function SignalRoute() {
  return (
    <ol className="signal-route" aria-label="Attempt routing stages">
      {stages.map((stage) => (
        <li key={stage.number}>
          <span className="route-number">{stage.number}</span>
          <div>
            <strong>{stage.title}</strong>
            <p>{stage.detail}</p>
          </div>
          <span className="route-outcome">{stage.outcome}</span>
        </li>
      ))}
    </ol>
  );
}
