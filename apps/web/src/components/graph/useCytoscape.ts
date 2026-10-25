/** Thin hook over cytoscape — NO unmaintained react-cytoscape wrappers (spec §4).
 * StrictMode-safe: cy.destroy() always runs on unmount (pitfall P1). */
import cytoscape, { type Core, type ElementDefinition, type LayoutOptions } from 'cytoscape';
import { useEffect, useRef, useState } from 'react';

export function useCytoscape(
  elements: ElementDefinition[],
  layout: 'cose' | 'circle',
): {
  containerRef: React.RefObject<HTMLDivElement>;
  cy: Core | null;
} {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cy, setCy] = useState<Core | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const instance = cytoscape({
      container: el,
      elements: [],
      style: [],
      wheelSensitivity: 0.2,
    });
    setCy(instance);
    return () => {
      setCy(null);
      instance.destroy(); // P1: StrictMode double-mount leaks without this
    };
  }, []);

  useEffect(() => {
    if (!cy) return;
    cy.elements().remove();
    if (elements.length > 0) {
      cy.add(elements);
      const layoutOpts = {
        name: layout,
        animate: false,
        padding: 50,
        ...(layout === 'cose' ? { nodeRepulsion: 8000, idealEdgeLength: 90 } : {}),
      } as LayoutOptions;
      cy.layout(layoutOpts).run();
      cy.fit(undefined, 40);
    }
  }, [cy, elements, layout]);

  return { containerRef, cy };
}
