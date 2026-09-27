export default function StatusBadge({ tone = "neutral", children }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
