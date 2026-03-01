import { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import PipelineNode from './components/PipelineNode';
import TitleBar from './components/TitleBar';
import Legend from './components/Legend';
import initialNodes from './data/nodes';
import initialEdges from './data/edges';

const nodeColor = (node) => {
  const map = {
    source: '#4a9eff',
    api: '#ff6b6b',
    script: '#b380ff',
    store: '#4ecdc4',
    output: '#ffa726',
    model: '#45b7d1',
  };
  return map[node.data?.category] || '#30363d';
};

function App() {
  const nodeTypes = useMemo(() => ({ pipeline: PipelineNode }), []);

  return (
    <div style={{ width: '100vw', height: '100vh', paddingTop: 52 }}>
      <TitleBar />
      <Legend />
      <ReactFlow
        nodes={initialNodes}
        edges={initialEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.15}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Background variant="dots" gap={20} size={1} color="#21262d" />
        <Controls position="top-right" showInteractive={false} />
        <MiniMap
          position="bottom-right"
          nodeColor={nodeColor}
          maskColor="rgba(13,17,23,0.8)"
          style={{ width: 200, height: 130 }}
        />
      </ReactFlow>
    </div>
  );
}

export default App;
