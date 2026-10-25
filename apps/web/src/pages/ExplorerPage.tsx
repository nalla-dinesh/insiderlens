/** Explorer — on-demand ego-graph forensics (account-anchored, §7.2).
 * Stats strip is derived client-side from the cited node/edge payloads only —
 * every number on screen maps to data the engine actually returned. */
import { useCallback, useState } from 'react';

import { getEgoGraph } from '../lib/api/graph';
import { inrFmt } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { EgoGraphResponse } from '../lib/types';
import ExplorerCanvas from '../components/graph/ExplorerCanvas';
import { EmptyState, ErrorState } from '../components/ui/States';
import { InlineSkeleton, CardSkeleton } from '../components/ui/States';

export default function ExplorerPage({ reloadSignal }: { reloadSignal: number }) {
  const [input, setInput] = useState('');
  const [depth, setDepth] = useState<1 | 2>(1);
  const [req, setReq] = useState<{ acc: number; depth: 1 | 2 } | null>(null);

  const fetcher = useCallback(
    (signal: AbortSignal) => {
      if (!req) {
        // pre-submit: resolve to null cleanly (no toast, no spinner jail)
        return Promise.resolve(null as unknown as EgoGraphResponse);
      }
      return getEgoGraph(req.acc, req.depth, signal);
    },
    [req],
  );
  const { data, loading, error, reload } = useApi<EgoGraphResponse>(fetcher, [req, reloadSignal]);

  const submit = () => {
    const acc = Number.parseInt(input, 10);
    if (Number.isFinite(acc)) setReq({ acc, depth });
  };

  // stats strip — every number derived from cited payloads (no backend fiction)
  const stats = data
    ? {
        neighbours: data.nodes.length - 1,
        legs: data.edges.length,
        volume: data.edges.reduce((s, e) => s + e.amount, 0),
        types: [...new Set(data.nodes.map((n) => n.group))],
        branches: null as null, // ego payload exposes no branch — don't fabricate
      }
    : null;

  return (
    <div className="max-w-[96rem] space-y-4">
      <div>
        <h1 className="text-lg font-bold text-primary">Money-flow explorer</h1>
        <p className="text-xs text-slate-500">
          Ego-transaction subgraph around one account, one hop out (depth 2 when a second shell ring
          is suspected). Every edge shown is a cited money leg — size and width reflect amounts.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Account id
          </span>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="e.g. 200072"
            inputMode="numeric"
            className="w-44 rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm text-primary focus:border-accent focus:outline-none"
          />
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">Depth</span>
          <div className="flex overflow-hidden rounded-lg border border-slate-200">
            {([1, 2] as const).map((d) => (
              <button
                key={d}
                onClick={() => {
                  setDepth(d);
                  if (req) setReq({ acc: req.acc, depth: d });
                }}
                className={`px-4 py-2 font-mono text-xs font-semibold transition-colors ${
                  depth === d ? 'bg-accent text-white' : 'bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={submit}
          disabled={loading || input.trim() === ''}
          className="mt-4 rounded-lg bg-accent px-6 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Tracing…' : 'Investigate'}
        </button>
        {loading && <InlineSkeleton lines={1} />}
      </div>

      {!req && (
        <EmptyState
          title="Enter an account to trace one hop out."
          hint="Accounts file in from the engineer's accounts.csv (ids start at 200071). Try the S5-documented wash account 200072 to see a shell ring first-hand."
        />
      )}

      {req && loading && <CardSkeleton rows={8} />}
      {req && error && !loading && <ErrorState message={error} onRetry={reload} />}

      {req && !loading && !error && data && stats && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat k="Direct neighbours" v={stats.neighbours} />
            <Stat k="Cited legs" v={stats.legs} />
            <Stat k="Cited volume" v={inrFmt(stats.volume)} />
            <Stat k="Account types" v={stats.types.join(' · ') || '—'} wide />
            <Stat k="Truncated" v={data.truncated ? 'YES — cap hit' : 'no'} />
          </div>

          {data.nodes.length === 0 ? (
            <EmptyState
              title={`No transactions touch account ${data.center} in the loaded window.`}
              hint="This account may exist with zero legs in the current batch — load a data batch with jobs touching it first (seed.py), then re-run analysis."
            />
          ) : (
            <ExplorerCanvas ego={data} />
          )}
        </>
      )}
    </div>
  );
}

function Stat({ k, v, wide }: { k: string; v: string | number; wide?: boolean }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm ${wide ? 'col-span-2' : ''}`}>
      <dt className="text-[9px] font-semibold tracking-wider text-slate-400 uppercase">{k}</dt>
      <dd className="mt-0.5 truncate font-mono text-sm font-semibold tabular-nums text-primary">{v}</dd>
    </div>
  );
}
