/** Tiny resize observer — feeds container size back into Cytoscape so the
 * layout never smears on sidebar/grid breakpoints (resize-safe spec). */
import type { Core } from 'cytoscape';
import { useEffect } from 'react';

export function useCyResize(containerRef: React.RefObject<HTMLDivElement>, cy: Core | null) {
  useEffect(() => {
    const el = containerRef.current;
    if (!cy || !el) return;
    const ro = new ResizeObserver(() => {
      cy.resize();
      cy.fit(undefined, 40);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [cy, containerRef]);
}
