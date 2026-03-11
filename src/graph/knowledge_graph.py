from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import networkx as nx


@dataclass
class KnowledgeGraph:
    """
    Thin wrapper around NetworkX graphs with consistent JSON serialization.
    """

    graph: nx.DiGraph

    @classmethod
    def empty(cls) -> "KnowledgeGraph":
        return cls(nx.DiGraph())

    def add_node(self, node_id: str, **attrs: Any) -> None:
        self.graph.add_node(node_id, **attrs)

    def add_edge(self, src: str, dst: str, edge_type: str, **attrs: Any) -> None:
        self.graph.add_edge(src, dst, edge_type=edge_type, **attrs)

    def nodes(self) -> Iterable[tuple[str, dict[str, Any]]]:
        return self.graph.nodes(data=True)

    def edges(self) -> Iterable[tuple[str, str, dict[str, Any]]]:
        return self.graph.edges(data=True)

    def pagerank(self) -> dict[str, float]:
        if self.graph.number_of_nodes() == 0:
            return {}
        # NetworkX's pagerank often routes through SciPy; keep this tool lightweight by
        # using a simple power-iteration implementation (good enough for hub ranking).
        alpha = 0.85
        max_iter = 100
        tol = 1.0e-6

        nodes = list(self.graph.nodes())
        n = len(nodes)
        if n == 0:
            return {}
        index = {node: i for i, node in enumerate(nodes)}

        out_neighbors = {u: list(self.graph.successors(u)) for u in nodes}
        out_degree = {u: len(out_neighbors[u]) for u in nodes}

        rank = [1.0 / n] * n
        teleport = (1.0 - alpha) / n

        for _ in range(max_iter):
            new_rank = [teleport] * n

            # distribute rank mass
            dangling_mass = 0.0
            for u in nodes:
                ru = rank[index[u]]
                deg = out_degree[u]
                if deg == 0:
                    dangling_mass += ru
                else:
                    share = alpha * ru / deg
                    for v in out_neighbors[u]:
                        new_rank[index[v]] += share

            # dangling nodes distribute uniformly
            if dangling_mass:
                share = alpha * dangling_mass / n
                for i in range(n):
                    new_rank[i] += share

            # convergence check (L1)
            err = sum(abs(new_rank[i] - rank[i]) for i in range(n))
            rank = new_rank
            if err < tol:
                break

        return {node: rank[index[node]] for node in nodes}

    def strongly_connected_components(self) -> list[list[str]]:
        return [list(c) for c in nx.strongly_connected_components(self.graph)]

    def to_node_link_json(self) -> dict[str, Any]:
        return nx.node_link_data(self.graph)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_node_link_json(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> "KnowledgeGraph":
        data = json.loads(path.read_text(encoding="utf-8"))
        g = nx.node_link_graph(data, directed=True)
        return cls(nx.DiGraph(g))

