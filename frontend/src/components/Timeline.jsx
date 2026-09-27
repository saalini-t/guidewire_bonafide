function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function Timeline({ entries }) {
  return (
    <section className="panel">
      <h2 className="panel__title">Preservation Timeline</h2>
      {entries.length === 0 ? (
        <p className="panel__empty">No preservation events recorded yet.</p>
      ) : (
        <ol className="timeline">
          {entries.map((entry) => (
            <li key={entry.id} className="timeline__item">
              <div className="timeline__row">
                <span className="timeline__event">{entry.event_type}</span>
                <span className="timeline__timestamp">{formatTimestamp(entry.timestamp)}</span>
              </div>
              <div className="timeline__meta">by {entry.user}</div>
              {entry.justification && <div className="timeline__justification">&ldquo;{entry.justification}&rdquo;</div>}
              {entry.detail && <pre className="timeline__detail">{JSON.stringify(entry.detail, null, 2)}</pre>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
