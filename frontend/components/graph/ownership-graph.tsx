"use client";

import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GitBranch } from "lucide-react";
import { EntityNode } from "./entity-node";
import { TrustNode } from "./trust-node";
import { UboNode } from "./ubo-node";
import { CitedEdge } from "./cited-edge";
import type { GraphNode, GraphEdge } from "@/types/edd";

const nodeTypes = {
  company: EntityNode,
  individual: EntityNode,
  trust: TrustNode,
  ubo: UboNode,
};

const edgeTypes = {
  cited: CitedEdge,
};

interface OwnershipGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  isLoading: boolean;
}

function toFlowNodes(nodes: GraphNode[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    type: n.node_type,
    position: n.position,
    data: {
      label: n.label,
      entity_type: n.entity_type,
      jurisdiction: n.jurisdiction,
      is_ubo: n.is_ubo,
      risk_flags: n.risk_flags,
      ofac_status: n.ofac_status,
    },
  }));
}

function toFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "cited",
    data: {
      ownership_pct: e.ownership_pct,
      citations: e.citations,
      edge_type: e.edge_type,
    },
    animated: e.edge_type === "look_through",
  }));
}

export function OwnershipGraph({ nodes, edges, isLoading }: OwnershipGraphProps) {
  const flowNodes = toFlowNodes(nodes);
  const flowEdges = toFlowEdges(edges);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/20">
        <div className="text-center space-y-2">
          <GitBranch className="size-10 text-muted-foreground/40 mx-auto animate-pulse" />
          <p className="text-sm text-muted-foreground">Building ownership graph…</p>
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/20">
        <div className="text-center space-y-2">
          <GitBranch className="size-10 text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">Load a scenario to view the ownership graph</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} className="!bg-muted/10" />
        <Controls className="!bg-card !border-border !shadow-sm" />

        {/* Legend */}
        <div className="absolute top-3 left-3 z-10 bg-card/90 backdrop-blur-sm border border-border rounded-lg p-2.5 text-xs space-y-1.5 shadow-sm">
          <p className="font-semibold text-foreground mb-1">Legend</p>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-muted-foreground bg-card" />
            <span className="text-muted-foreground">Company / LLC</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-dashed border-blue-400" />
            <span className="text-muted-foreground">Revocable Trust</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-dashed border-orange-400" />
            <span className="text-muted-foreground">Irrevocable Trust</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-emerald-400 bg-emerald-50" />
            <span className="text-muted-foreground">UBO (clean)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded border-2 border-red-400 bg-red-50" />
            <span className="text-muted-foreground">UBO (risk flag)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-5 h-0.5 border-t-2 border-dashed border-slate-400" />
            <span className="text-muted-foreground">Look-through edge</span>
          </div>
        </div>

        {/* Arrow marker definition */}
        <svg style={{ position: "absolute", width: 0, height: 0 }}>
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#94a3b8" />
            </marker>
          </defs>
        </svg>
      </ReactFlow>
    </div>
  );
}
