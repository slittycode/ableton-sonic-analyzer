import React, { useEffect, useState } from 'react';

export interface StickyNavSection {
  id: string;
  label: string;
  /**
   * Marks the pill as a section that exists in the IA but has no rendered
   * target yet (e.g. Phase 2 recommendations not produced for this run).
   * The pill renders in muted style, is not clickable, and surfaces
   * `disabledReason` as a tooltip so the user understands why the section
   * isn't reachable. Audit N1 sibling: replaces the previous behaviour of
   * silently dropping these pills from the nav on Phase 2 failure.
   */
  disabled?: boolean;
  disabledReason?: string;
}

interface StickyNavProps {
  sections: StickyNavSection[];
}

export function StickyNav({ sections }: StickyNavProps) {
  const [activeId, setActiveId] = useState(sections[0]?.id ?? '');

  useEffect(() => {
    if (sections.length === 0 || typeof window === 'undefined') return;

    const syncFromHash = () => {
      const nextHash = window.location.hash.replace(/^#/, '');
      if (sections.some((section) => section.id === nextHash)) {
        setActiveId(nextHash);
      }
    };

    syncFromHash();
    window.addEventListener('hashchange', syncFromHash);

    if (!('IntersectionObserver' in window)) {
      return () => window.removeEventListener('hashchange', syncFromHash);
    }

    const observer = new window.IntersectionObserver(
      (entries) => {
        const visibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];

        if (visibleEntry?.target.id) {
          setActiveId(visibleEntry.target.id);
        }
      },
      {
        rootMargin: '-20% 0px -55% 0px',
        threshold: [0.2, 0.4, 0.65],
      },
    );

    sections.forEach((section) => {
      if (section.disabled) return;
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    });

    return () => {
      observer.disconnect();
      window.removeEventListener('hashchange', syncFromHash);
    };
  }, [sections]);

  if (sections.length === 0) return null;

  return (
    <div className="sticky top-3 z-20 rounded-sm border border-border bg-bg-panel/95 px-3 py-3 shadow-[0_12px_30px_rgba(0,0,0,0.12)] backdrop-blur-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        {/* Audit N10: was "Device Chain" — confusing because "device chain" in
            Ableton means a track's effects routing, not section navigation. */}
        <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-text-secondary">Sections</p>
        <div className="overflow-x-auto">
          <div className="flex min-w-max items-center gap-2 pr-2">
            {sections.map((section) => {
              const isDisabled = section.disabled === true;
              const isActive = !isDisabled && section.id === activeId;
              return (
                <a
                  key={section.id}
                  href={isDisabled ? undefined : `#${section.id}`}
                  onClick={(event) => {
                    if (isDisabled) {
                      event.preventDefault();
                      return;
                    }
                    event.preventDefault();
                    setActiveId(section.id);

                    const element = document.getElementById(section.id);
                    if (element) {
                      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      window.history.replaceState(null, '', `#${section.id}`);
                    }
                  }}
                  title={isDisabled ? section.disabledReason : undefined}
                  aria-disabled={isDisabled || undefined}
                  data-disabled={isDisabled || undefined}
                  className={`rounded-sm border px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.16em] transition-colors ${
                    isDisabled
                      ? 'border-border/60 bg-bg-card/40 text-text-secondary/40 cursor-not-allowed'
                      : isActive
                        ? 'border-accent/50 bg-accent/10 text-accent'
                        : 'border-border bg-bg-card text-text-secondary hover:border-accent/30 hover:text-text-primary'
                  }`}
                >
                  {section.label}
                </a>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
