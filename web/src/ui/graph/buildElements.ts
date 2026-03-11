import type { NodeLinkGraph } from "../types";

type CytoscapeNode = {
  data: {
    id: string;
    label: string;
    kind: string;
    raw: Record<string, unknown>;
  };
};

type CytoscapeEdge = {
  data: {
    id: string;
    source: string;
    target: string;
    edge_type: string;
    raw: Record<string, unknown>;
  };
};

export type CytoscapeElements = Array<CytoscapeNode | CytoscapeEdge>;

function nodeLabel(n: Record<string, unknown> & { id: string }): string {
  const path = typeof n.path === "string" ? n.path : undefined;
  const name = typeof n.name === "string" ? n.name : undefined;
  const qn = typeof n.qualified_name === "string" ? n.qualified_name : undefined;
  return path ?? name ?? qn ?? n.id;
}

function nodeKind(n: Record<string, unknown>): string {
  const t = typeof n.node_type === "string" ? n.node_type : undefined;
  if (t) return t;
  if (typeof n.language === "string") return "Module";
  if (typeof n.storage_type === "string") return "Dataset";
  if (typeof n.transformation_type === "string") return "Transformation";
  return "Node";
}

export function buildElements(g: NodeLinkGraph): CytoscapeElements {
  const nodes: CytoscapeNode[] = g.nodes.map((n) => ({
    data: {
      id: n.id,
      label: nodeLabel(n),
      kind: nodeKind(n),
      raw: n
    }
  }));

  const edges: CytoscapeEdge[] = g.links.map((e, idx) => {
    const edgeType =
      typeof (e as { edge_type?: unknown }).edge_type === "string"
        ? ((e as { edge_type: string }).edge_type as string)
        : "EDGE";
    const id = `${e.source}::${edgeType}::${e.target}::${idx}`;
    return {
      data: {
        id,
        source: e.source,
        target: e.target,
        edge_type: edgeType,
        raw: e
      }
    };
  });

  return [...nodes, ...edges];
}

