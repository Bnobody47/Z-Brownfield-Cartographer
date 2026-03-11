import cytoscape, { type Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import React, { useEffect, useMemo, useRef } from "react";
import type { CytoscapeElements } from "./buildElements";

cytoscape.use(fcose);

export function GraphView(props: {
  elements: CytoscapeElements;
  onSelectNode: (node: { id: string; raw: Record<string, unknown> } | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const stylesheet = useMemo(
    () => [
      {
        selector: "node",
        style: {
          "background-color": "#6d28d9",
          label: "data(label)",
          color: "rgba(255,255,255,0.9)",
          "font-size": 9,
          "text-wrap": "wrap" as const,
          "text-max-width": 140,
          "text-outline-width": 2,
          "text-outline-color": "rgba(0,0,0,0.35)",
          width: 22,
          height: 22
        }
      },
      {
        selector: 'node[kind = "DatasetNode"], node[kind = "Dataset"]',
        style: { "background-color": "#22c55e", shape: "round-rectangle", width: 28, height: 18 }
      },
      {
        selector: 'node[kind = "TransformationNode"], node[kind = "Transformation"]',
        style: { "background-color": "#38bdf8", shape: "diamond", width: 22, height: 22 }
      },
      {
        selector: 'node[kind = "FunctionNode"]',
        style: { "background-color": "#f59e0b", shape: "ellipse", width: 20, height: 20 }
      },
      {
        selector: "edge",
        style: {
          width: 1.2,
          "curve-style": "bezier",
          "target-arrow-shape": "triangle",
          "line-color": "rgba(255,255,255,0.22)",
          "target-arrow-color": "rgba(255,255,255,0.22)"
        }
      },
      {
        selector: 'edge[edge_type = "IMPORTS"]',
        style: { "line-color": "rgba(124,58,237,0.45)", "target-arrow-color": "rgba(124,58,237,0.45)" }
      },
      {
        selector: 'edge[edge_type = "CONSUMES"]',
        style: { "line-color": "rgba(34,197,94,0.45)", "target-arrow-color": "rgba(34,197,94,0.45)" }
      },
      {
        selector: 'edge[edge_type = "PRODUCES"]',
        style: { "line-color": "rgba(56,189,248,0.55)", "target-arrow-color": "rgba(56,189,248,0.55)" }
      },
      {
        selector: ":selected",
        style: {
          "border-width": 2,
          "border-color": "rgba(255,255,255,0.8)",
          "line-color": "rgba(255,255,255,0.6)",
          "target-arrow-color": "rgba(255,255,255,0.6)"
        }
      }
    ],
    []
  );

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: props.elements,
      style: stylesheet as any,
      layout: { name: "fcose", quality: "default", animate: false, nodeSeparation: 80 } as any
    });

    cyRef.current = cy;

    cy.on("tap", "node", (evt) => {
      const n = evt.target;
      props.onSelectNode({ id: n.id(), raw: (n.data("raw") ?? {}) as Record<string, unknown> });
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) props.onSelectNode(null);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [props.elements, stylesheet]);

  return <div className="graph" ref={containerRef} />;
}

