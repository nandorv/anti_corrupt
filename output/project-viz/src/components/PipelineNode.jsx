import { Handle, Position } from '@xyflow/react';
import './PipelineNode.css';

export default function PipelineNode({ data }) {
  const { label, icon, category, badge, stats, description } = data;

  return (
    <div className={`pipeline-node ${category}`}>
      <Handle
        type="target"
        position={Position.Left}
        className="handle"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="handle"
      />

      <div className="node-header">
        <span className="icon">{icon || '📦'}</span>
        <span className="label">{label}</span>
        {badge && (
          <span className={`node-badge badge-${category}`}>{badge}</span>
        )}
      </div>

      <div className="node-divider" />

      <div className="node-body">
        {description && <div className="node-desc">{description}</div>}
        {stats?.map((s, i) => (
          <div key={i} className="stat-row">
            <span className="stat-label">{s.label}</span>
            <span className="stat-value">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
