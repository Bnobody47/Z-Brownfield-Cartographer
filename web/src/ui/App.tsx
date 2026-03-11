import React, { useMemo, useState } from "react";
import type { NodeLinkGraph } from "./types";
import { buildElements } from "./graph/buildElements";
import { GraphView } from "./graph/GraphView";

type SelectedNode = { id: string; raw: Record<string, unknown> } | null;

function isNodeLinkGraph(x: unknown): x is NodeLinkGraph {
  if (!x || typeof x !== "object") return false;
  const o = x as any;
  return Array.isArray(o.nodes) && Array.isArray(o.links);
}

async function readJsonFile(file: File): Promise<unknown> {
  const text = await file.text();
  return JSON.parse(text);
}

export function App() {
  const [graph, setGraph] = useState<NodeLinkGraph | null>(null);
  const [selected, setSelected] = useState<SelectedNode>(null);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);

  const elements = useMemo(() => (graph ? buildElements(graph) : []), [graph]);

  const stats = useMemo(() => {
    if (!graph) return null;
    return {
      nodes: graph.nodes.length,
      edges: graph.links.length,
      directed: graph.directed ?? true
    };
  }, [graph]);

  async function onPickFile(file: File) {
    setError(null);
    setSelected(null);
    setFilename(file.name);
    try {
      const parsed = await readJsonFile(file);
      if (!isNodeLinkGraph(parsed)) {
        throw new Error("That JSON doesn't look like a NetworkX node-link graph (missing nodes/links).");
      }
      setGraph(parsed);
    } catch (e: any) {
      setGraph(null);
      setError(e?.message ?? String(e));
    }
  }

  return (
    <div className="shell">
      <div className="topbar">
        <div className="title">
          <h1>Brownfield Cartographer — Graph Viewer</h1>
          <div className="sub">Upload `.cartography/module_graph.json` or `.cartography/lineage_graph.json`</div>
        </div>
        <div className="btnRow">
          <label className="btn btnPrimary">
            Upload JSON
            <input
              type="file"
              accept="application/json,.json"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onPickFile(f);
              }}
            />
          </label>
          <button className="btn" onClick={() => (setGraph(null), setSelected(null), setError(null), setFilename(null))}>
            Clear
          </button>
        </div>
      </div>

      <div className="content">
        <div className="panel left">
          <div className="small">
            <strong>Tip:</strong> run `cartographer analyze &lt;repo&gt;` then open the generated JSON from that repo’s
            `.cartography/` folder.
          </div>

          <div className="drop">
            <strong>Drag & drop</strong>
            <div className="hint">
              Drop a `module_graph.json` or `lineage_graph.json` here.
              <br />
              Nothing is uploaded anywhere—this runs fully in your browser.
            </div>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files?.[0];
                if (f) void onPickFile(f);
              }}
              style={{ marginTop: 10, padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.10)" }}
            >
              <div className="small">{filename ? `Loaded: ${filename}` : "No file loaded yet."}</div>
              {error ? (
                <div style={{ marginTop: 8, color: "rgba(248,113,113,0.95)", fontSize: 12 }}>{error}</div>
              ) : null}
            </div>
          </div>

          <div className="kv">
            <h3>Graph stats</h3>
            <div className="pre">{stats ? JSON.stringify(stats, null, 2) : "Load a graph to see stats."}</div>
          </div>

          <div className="kv">
            <h3>Selected node</h3>
            <div className="pre">
              {selected
                ? JSON.stringify({ id: selected.id, ...selected.raw }, null, 2)
                : "Click a node to inspect metadata."}
            </div>
          </div>
        </div>

        <div className="panel right">
          <div className="graphHeader">
            <div className="pill">{graph ? "Interactive graph" : "Waiting for JSON…"}</div>
            <div className="pill">
              Legend: <span style={{ color: "#6d28d9" }}>Module</span> ·{" "}
              <span style={{ color: "#22c55e" }}>Dataset</span> ·{" "}
              <span style={{ color: "#38bdf8" }}>Transformation</span>
            </div>
          </div>
          {graph ? <GraphView elements={elements} onSelectNode={setSelected} /> : <div className="graph" />}
        </div>
      </div>
    </div>
  );
}

