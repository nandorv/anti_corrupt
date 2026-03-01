import './Legend.css';

const items = [
  { label: 'Data Source', bg: 'var(--source-bg)', border: 'var(--source-border)' },
  { label: 'External API', bg: 'var(--api-bg)', border: 'var(--api-border)' },
  { label: 'Script / Pipeline', bg: 'var(--script-bg)', border: 'var(--script-border)' },
  { label: 'Storage', bg: 'var(--store-bg)', border: 'var(--store-border)' },
  { label: 'Model', bg: 'var(--model-bg)', border: 'var(--model-border)' },
  { label: 'Output / Analysis', bg: 'var(--output-bg)', border: 'var(--output-border)' },
];

export default function Legend() {
  return (
    <div className="legend">
      {items.map((item) => (
        <div key={item.label} className="legend-item">
          <div
            className="legend-dot"
            style={{ background: item.bg, borderColor: item.border }}
          />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}
