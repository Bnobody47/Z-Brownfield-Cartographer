export type NodeLinkGraph = {
  directed?: boolean;
  multigraph?: boolean;
  graph?: Record<string, unknown>;
  nodes: Array<Record<string, unknown> & { id: string }>;
  links: Array<
    Record<string, unknown> & {
      source: string;
      target: string;
      edge_type?: string;
    }
  >;
};

