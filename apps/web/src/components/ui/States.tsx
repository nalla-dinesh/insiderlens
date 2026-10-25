/** Skeleton / empty / error states — every async view uses one of these,
 * never a bare spinner or blank screen (design system §2). */

export function CardSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="h-4 w-1/4 rounded bg-slate-200" />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-8 rounded bg-slate-100" style={{ width: `${95 - i * 9}%` }} />
      ))}
    </div>
  );
}

export function InlineSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3 rounded bg-slate-200" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white/60 px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-100 text-xl">
        ◎
      </div>
      <h3 className="text-sm font-semibold text-primary">{title}</h3>
      <p className="mt-1 max-w-sm text-xs text-slate-500">{hint}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-danger/30 bg-danger-100 p-5">
      <p className="text-sm font-semibold text-danger">Something went wrong</p>
      <p className="mt-1 font-mono text-xs break-all text-danger/80">{message}</p>
      <button
        onClick={onRetry}
        className="mt-3 rounded-lg bg-danger px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90"
      >
        Retry
      </button>
    </div>
  );
}
