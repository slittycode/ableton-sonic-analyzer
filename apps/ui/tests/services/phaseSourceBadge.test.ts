import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PhaseSourceBadge } from "../../src/components/PhaseSourceBadge";

describe("PhaseSourceBadge", () => {
  it('renders "DSP" for measured sources', () => {
    const html = renderToStaticMarkup(React.createElement(PhaseSourceBadge, { source: "measured" }));
    expect(html).toContain(">DSP<");
  });

  it('renders "AI" for advisory sources', () => {
    const html = renderToStaticMarkup(React.createElement(PhaseSourceBadge, { source: "advisory" }));
    expect(html).toContain(">AI<");
  });
});
