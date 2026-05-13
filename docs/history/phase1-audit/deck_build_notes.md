# Deck Build Notes

- Authoring source: `build_phase1_executive_deck.js`
- Output deck: `phase1_executive_deck.pptx`
- Local JS dependency was installed only under `advisory/phase1_audit/.node/`
- Existing repo files were not modified

## Verification limits

- The deck was generated locally as a `.pptx`
- This machine does not currently have `soffice` / LibreOffice or `pdftoppm`, so I could not raster-render the deck to PNGs for a visual overflow pass
- The source was therefore verified by successful generation and file existence, not by slide-image rendering

## `.mmd` file

- `.mmd` is a Mermaid diagram source file
- It is plain text
- In this advisory package, `phase1_flow.mmd` is the diagram source for the pipeline map
- You can paste it into a Mermaid renderer, open it in tools that support Mermaid, or convert it to SVG/PNG later
