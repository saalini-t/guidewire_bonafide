// The backend's preservation analysis is authoritative — this component
// only renders what GET .../analysis returns, it never recalculates risk.
const TONE_BY_RISK = { HIGH: "danger", MEDIUM: "warning", LOW: "success" };

export default function RiskBanner({ analysis }) {
  if (!analysis) return null;
  const tone = TONE_BY_RISK[analysis.risk_level] ?? "neutral";

  return (
    <section className={`risk-banner risk-banner--${tone}`} data-testid="risk-banner">
      <div className="risk-banner__level">{analysis.risk_level} PRESERVATION RISK</div>
      <p className="risk-banner__explanation">{analysis.explanation}</p>
      {analysis.at_risk_evidence.length > 0 && (
        <ul className="risk-banner__list">
          {analysis.at_risk_evidence.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <p className="risk-banner__recommendation">{analysis.recommendation}</p>
    </section>
  );
}
