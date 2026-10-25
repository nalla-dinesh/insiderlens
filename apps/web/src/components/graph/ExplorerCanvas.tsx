/** ExplorerCanvas — ego-subgraph renderer for EgoGraphResponse (verified live
 * contract: nodes {id,label,group}, edges {source,target,amount,ts,txn_id}).
 * Every leg is a cited-money edge: width ∝ amount, arrow = flow direction.
 * The center account is amber-ringed; node size ∝ its share of cited flow. */
import type { Core, ElementDefinition } from 'cytoscape';
import { useEffect, useMemo, useState } from 'react';

import { dtFmt, inrFmt } from '../../lib/format';
import type { EgoGraphResponse } from '../../lib/types';
import { useCyResize } from './useCyResize';
import { useCytoscape } from './useCytoscape';

interface Pop {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

export default function ExplorerCanvas({ ego }: { ego: EgoGraphResponse }) {
  const [layout, setLayout] = useState<'cose' | 'circle'>('cose');
  const [pop, setPop] = useState<Pop | null>(null);

  const elements = useMemo<ElementDefinition[]>(() => {
    const maxAmt = Math.max(1, ...ego.edges.map((e) => e.amount));
    const volume = Math.max(1, ego.edges.reduce((s, e) => s + e.amount, 0));

    const nodes: ElementDefinition[] = ego.nodes.map((n) => {
      const share =
        ego.edges
          .filter((e) => e.source === n.id || e.target === n.id)
          .reduce((s, e) => s + e.amount, 0) / volume;
      const isCenter = n.id === ego.center;
      return {
        data: {
          id: `n${n.id}`,
          label: n.label, // "200072 · SAVINGS" straight from the engine
          sub: `${n.group}${n.risk_hint ? ` · ⚠ ${n.risk_hint}` : ''} · share ${(share * 100).toFixed(0)}%`,
          center: isCenter,
        },
        style: {
          width: 30 + Math.min(share, 0.6) * 80,
          height: 30 + Math.min(share, 0.6) * 80,
          'border-color': isCenter ? '#f59e0b' : '#0284c7',
          'border-width': isCenter ? 4 : 2,
          ...(isCenter ? { 'background-color': '#b45309' } : {}),
        },
      };
    });
    const edges: ElementDefinition[] = ego.edges.map((e) => ({
      data: {
        id: `e${e.txn_id}`,
        source: `n${e.source}`,
        target: `n${e.target}`,
        amount: e.amount,
        ts: e.ts,
        channel: e.channel ?? '—',
      },
      style: { width: 1.4 + (e.amount / maxAmt) * 5.5 },
    }));
    return [...nodes, ...edges];
  }, [ego]);

  const { containerRef, cy } = useCytoscape(elements, layout);
  useCyResize(containerRef, cy);

  useEffect(() => {
    if (!cy) return;
    wire(cy, setPop, ego.center);
    cy.fit(undefined, 40);
  }, [cy, elements, ego.center]);

  const ctrl =
    'pointer-events-auto rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1.5 text-xs font-medium text-slate-600 shadow-sm hover:border-accent hover:text-accent';

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
          Ego graph — account {ego.center}, depth {ego.depth}
          {ego.truncated ? ' (truncated at cap)' : ''}
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
        <div ref={containerRef} className="rounded-xl bg-slate-50/60" style={{ height: 440 }} />
        {pop && (
          <div
            className="pointer-events-none absolute z-10 max-w-64 rounded-lg border border-slate-200 bg-white p-3 text-xs shadow-lg"
            style={{ left: Math.min(pop.x + 12, 420), top: pop.y + 12 }}
          >
            <p className="mb-1 font-mono font-semibold text-primary">{pop.title}</p>
            {pop.lines.map((l, i) => (
              <p key={i} className="text-[11px] leading-relaxed break-words text-slate-500">{l}</p>
            ))}
          </div>
        )}
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg border border-slate-200 bg-white/90 p-2 text-[10px] text-slate-500 shadow-sm">
          <p><span className="text-accent">●</span> account (size ∝ share of cited flow)</p>
          <p><span className="text-amber-500">●</span> focal account</p>
          <p>— width ∝ amount · click node/edge for totals · scroll zooms</p>
        </div>
      </div>
    </div>
  );
}

function wire(cy: Core, setPop: (p: Pop | null) => void, center: number) {
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
      },
    },
    {
      selector: `node[id = "n${center}"]`,
      style: { 'border-color': '#f59e0b', 'border-width': 4 },
    },
    {
      selector: 'edge',
      style: {
        'line-color': '#0284c7',
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'target-arrow-color': '#0284c7',
        'arrow-scale': 1.1,
        opacity: 0.85,
      },
    },
  ]);

  cy.removeAllListeners();
  cy.on('tap', 'node', (evt) => {
    const n = evt.target;
    const sum = (edges: cytoscape.EdgeCollection): number =>
      edges.reduce((acc: number, e) => acc + (Number(e.data('amount')) || 0), 0);
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
