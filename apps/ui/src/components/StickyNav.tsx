import React, { useEffect, useState } from 'react';

export interface StickyNavSection {
  id: string;
  label: string;
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
        <p className="text-[10px] font-mono uppercase tracking-[0.28em] text-text-secondary">Device Chain</p>
        <div className="overflow-x-auto">
          <div className="flex min-w-max items-center gap-2 pr-2">
            {sections.map((section) => {
              const isActive = section.id === activeId;
              return (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  onClick={(event) => {
                    event.preventDefault();
                    setActiveId(section.id);

                    const element = document.getElementById(section.id);
                    if (element) {
                      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                      window.history.replaceState(null, '', `#${section.id}`);
                    }
                  }}
                  className={`rounded-sm border px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.16em] transition-colors ${
                    isActive
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
