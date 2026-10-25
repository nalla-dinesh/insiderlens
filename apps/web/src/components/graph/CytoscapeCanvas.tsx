/** CytoscapeCanvas — evidence money-flow renderer (EvidenceGraph).
 * accounts = circles sized by actor count share (degree) · edges ∝ amount with
 * arrows · band-colored pattern edges · legend + fit/zoom + layout toggle ·
 * click node/edge → evidence popover · tap blank clears · resize-safe. */
import type { Core, ElementDefinition } from 'cytoscape';
import { useEffect, useMemo, useState } from 'react';

import { inrFmt, dtFmt } from '../../lib/format';
import type { Band, EvidenceGraph } from '../../lib/types';
import { useCytoscape } from './useCytoscape';
import { useCyResize } from './useCyResize';

const BAND_EDGE: Record<Band, string> = {
  LOW: '#64748b',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  CRITICAL: '#dc2626',
};

interface Pop {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

export default function CytoscapeCanvas({
  graph,
  band,
  height = 480,
  onInit,
}: {
  graph: EvidenceGraph;
  band: Band;
  height?: number;
  /** hands the live Cytoscape Core up once mounted (export snapshot uses cy.png) */
  onInit?: (cy: Core) => void;
}) {
  const [layout, setLayout] = useState<'cose' | 'circle'>('cose');
  const [pop, setPop] = useState<Pop | null>(null);

  const elements = useMemo<ElementDefinition[]>(() => {
    // "size ∝ actor count share" — node's share of all touching cited legs
    const degree = new Map<number, number>();
    let degTotal = 0;
    for (const e of graph.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    for (const d of degree.values()) degTotal += d;
    const maxAmt = Math.max(1, ...graph.edges.map((e) => e.amount));
    const share = (id: number) => (degTotal === 0 ? 0 : (degree.get(id) ?? 0) / degTotal);

    const nodes: ElementDefinition[] = graph.nodes.map((n) => {
      const s = share(n.id);
      return {
        data: {
          id: `n${n.id}`,
          label: n.label,
          sub: `${n.branch ?? '—'} · ${n.type ?? ''} · ${n.status ?? ''} · share ${(s * 100).toFixed(0)}%`,
        },
        style: { width: 28 + Math.min(s, 0.5) * 70, height: 28 + Math.min(s, 0.5) * 70 },
      };
    });
    const edges: ElementDefinition[] = graph.edges.map((e) => ({
      data: {
        id: `e${e.id}`,
        source: `n${e.source}`,
        target: `n${e.target}`,
        amount: e.amount,
        ts: e.ts,
        channel: e.channel,
      },
      style: { width: 1.4 + (e.amount / maxAmt) * 5.5 },
    }));
    return [...nodes, ...edges];
  }, [graph]);

  const { containerRef, cy } = useCytoscape(elements, layout);
  useCyResize(containerRef, cy);

  useEffect(() => {
    if (!cy) return;
    wireCanvas(cy, band, setPop);
    cy.fit(undefined, 40);
  }, [cy, band, elements]);

  useEffect(() => {
    if (cy && onInit) onInit(cy);
  }, [cy, onInit]);

  const ctrl =
    'pointer-events-auto rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1.5 text-xs font-medium text-slate-600 shadow-sm hover:border-accent hover:text-accent';

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
          Money flow — cited evidence {graph.truncated ? '(truncated)' : ''}
        </h3>
        <div className="flex gap-1.5">
          <button className={ctrl} onClick={() => { setPop(null); cy?.fit(undefined, 40); }}>
            Fit
          </button>
          <button
            className={ctrl}
            onClick={() => {
              if (!cy) return;
              cy.zoom(cy.zoom() * 1.25);
              cy.center();
            }}
          >
            +
          </button>
          <button
            className={ctrl}
            onClick={() => {
              if (!cy) return;
              cy.zoom(cy.zoom() / 1.25);
              cy.center();
            }}
          >
            −
          </button>
          <button
            className={ctrl}
            onClick={() => setLayout((l) => (l === 'cose' ? 'circle' : 'cose'))}
          >
            Layout: {layout}
          </button>
        </div>
      </div>

      <div className="relative">
        <div ref={containerRef} className="rounded-lg bg-slate-50/60" style={{ height }} />
        {pop && (
          <div
            className="pointer-events-none absolute z-10 max-w-64 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg"
            style={{ left: Math.min(pop.x + 12, 400), top: pop.y + 12 }}
          >
            <p className="mb-1 font-mono font-semibold text-primary">{pop.title}</p>
            {pop.lines.map((l, i) => (
              <p key={i} className="text-[11px] leading-relaxed break-words text-slate-500">
                {l}
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-primary ring-2 ring-accent/60" /> account
          (size ∝ share of cited money)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="20" height="8" aria-hidden>
            <line x1="0" y1="4" x2="20" y2="4" stroke={BAND_EDGE[band]} strokeWidth="3" />
          </svg>
          cited legs · width ∝ amount · colored {band}
        </span>
        <span className="text-slate-400">click node/edge for totals · scroll zooms · drag pans</span>
      </div>
    </section>
  );
}

/** Imperative bits kept off-render: style sheet + tap wiring (re-applied
 * after every element swap / band change). */
function wireCanvas(cy: Core, band: Band, setPop: (p: Pop | null) => void) {
  cy.style([
    {
      selector: 'node',
      style: {
        'background-color': '#0e2a47',
        label: 'data(label)',
        'font-size': 10,
        'font-family': 'ui-monospace, "SF Mono", Menlo, monospace',
        color: '#334155',
        'text-valign': 'bottom',
        'text-margin-y': 4,
        'border-width': 2,
        'border-color': '#0284c7',
      },
    },
    {
      selector: 'edge',
      style: {
        'line-color': BAND_EDGE[band],
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'target-arrow-color': BAND_EDGE[band],
        'arrow-scale': 1.1,
        opacity: 0.85,
      },
    },
  ]);

  cy.removeAllListeners();
  cy.on('tap', 'node', (evt) => {
    const n = evt.target;
    const sum = (
      collection: cytoscape.EdgeCollection,
    ): number => collection.reduce((acc, e) => acc + (Number(e.data('amount')) || 0), 0);
    setPop({
      x: evt.renderedPosition.x,
      y: evt.renderedPosition.y,
      title: String(n.data('label')),
      lines: [
        String(n.data('sub') ?? ''),
        `in ▶ ${inrFmt(sum(n.incomers('edge')))} · out ▶ ${inrFmt(sum(n.outgoers('edge')))}`,
      ],
    });
  });
  cy.on('tap', 'edge', (evt) => {
    const e = evt.target.data() as { amount: number; ts: string; channel: string; id: string };
    setPop({
      x: evt.renderedPosition.x,
      y: evt.renderedPosition.y,
      title: `txn ${e.id.slice(1)}`,
      lines: [inrFmt(e.amount), `${e.channel} · ${dtFmt(e.ts)}`],
    });
  });
  cy.on('tap', (evt) => {
    if (evt.target === cy) setPop(null);
  });
}
