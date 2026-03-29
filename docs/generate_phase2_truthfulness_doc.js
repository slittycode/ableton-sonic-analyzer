const fs = require("fs");
const path = require("path");
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  LevelFormat,
  Packer,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} = require("docx");

const outputPath = path.resolve(
  process.argv[2] ?? path.join(__dirname, "PHASE2_TRUTHFULNESS_PHASES_A_B_C.docx"),
);

const tableBorder = { style: BorderStyle.SINGLE, size: 1, color: "D0D0D0" };
const cellBorders = {
  top: tableBorder,
  bottom: tableBorder,
  left: tableBorder,
  right: tableBorder,
};

function body(text) {
  return new Paragraph({
    spacing: { after: 120 },
    children: [new TextRun(text)],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullet-list", level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
  });
}

function numbered(text) {
  return new Paragraph({
    numbering: { reference: "numbered-list", level: 0 },
    spacing: { after: 80 },
    children: [new TextRun(text)],
  });
}

function sectionHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun(text)],
  });
}

function subHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun(text)],
  });
}

function fileBullet(filePath) {
  return bullet(filePath);
}

function summaryTable() {
  return new Table({
    columnWidths: [1560, 3900, 3900],
    margins: { top: 100, bottom: 100, left: 160, right: 160 },
    rows: [
      new TableRow({
        tableHeader: true,
        children: [
          new TableCell({
            borders: cellBorders,
            width: { size: 1560, type: WidthType.DXA },
            shading: { fill: "EAEAEA", type: ShadingType.CLEAR },
            children: [
              new Paragraph({
                children: [new TextRun({ text: "Phase", bold: true })],
              }),
            ],
          }),
          new TableCell({
            borders: cellBorders,
            width: { size: 3900, type: WidthType.DXA },
            shading: { fill: "EAEAEA", type: ShadingType.CLEAR },
            children: [
              new Paragraph({
                children: [new TextRun({ text: "Plain-English Outcome", bold: true })],
              }),
            ],
          }),
          new TableCell({
            borders: cellBorders,
            width: { size: 3900, type: WidthType.DXA },
            shading: { fill: "EAEAEA", type: ShadingType.CLEAR },
            children: [
              new Paragraph({
                children: [new TextRun({ text: "Technical Outcome", bold: true })],
              }),
            ],
          }),
        ],
      }),
      ...[
        [
          "A",
          "The producer summary stopped sounding made up and started using approved Ableton device names, session scaffolding, and safe warning behavior.",
          "Introduced interpretation.v2 producer-summary contract, Live 12 catalog injection, semantic warnings, routing/layout/setup fields, and stronger prompt grounding.",
        ],
        [
          "B",
          "The UI began showing the new setup and workflow guidance instead of burying it in raw JSON or not rendering it at all.",
          "Rendered v2-only setup/layout/routing/warp panels, workflow metadata, arrangement actions, and caution banners while preserving v1 compatibility.",
        ],
        [
          "C",
          "Gemini gained a real job for the attached audio: describe what it hears without overruling the measurements.",
          "Added optional audioObservations, explicit listening tasks in the prompt, UI paneling for perceptual notes, and sanitizer logic that drops malformed perceptual payloads without nulling phase2.",
        ],
      ].map(
        ([phase, plainEnglish, technical]) =>
          new TableRow({
            children: [
              new TableCell({
                borders: cellBorders,
                width: { size: 1560, type: WidthType.DXA },
                children: [body(phase)],
              }),
              new TableCell({
                borders: cellBorders,
                width: { size: 3900, type: WidthType.DXA },
                children: [body(plainEnglish)],
              }),
              new TableCell({
                borders: cellBorders,
                width: { size: 3900, type: WidthType.DXA },
                children: [body(technical)],
              }),
            ],
          }),
      ),
    ],
  });
}

const children = [
  new Paragraph({
    heading: HeadingLevel.TITLE,
    alignment: AlignmentType.CENTER,
    children: [new TextRun("ASA Phase 2 Truthfulness Pass")],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "Documentation for Phases A, B, and C",
        size: 26,
        color: "444444",
      }),
    ],
  }),
  body(
    "This document records the three implementation phases that made the producer-summary path more trustworthy, more practical for Ableton users, and more honest about what is measured versus what is heard.",
  ),
  subHeading("Executive Summary"),
  body(
    "In plain English, Phase A fixed the backend contract and prompt so ASA stopped inventing Ableton details. Phase B put that new structure on screen in a usable way. Phase C made the attached audio file matter by giving Gemini a separate place to report perceptual observations without overriding DSP facts.",
  ),
  summaryTable(),

  sectionHeading("Phase A — Backend Contract, Prompting, and Validation"),
  subHeading("Plain-English Summary"),
  body(
    "Phase A is where the producer summary stopped acting like a vague music review and started acting like a rebuild brief. It taught the backend to ask for session setup, track layout, routing, warp choices, and catalog-approved Live device names, then keep the result even when some device details looked suspicious.",
  ),
  subHeading("Technical Changes"),
  bullet("Bumped producer-summary writes to interpretation.v2 while keeping old interpretation.v1 results readable."),
  bullet("Injected the curated Live 12 catalog into the producer-summary prompt at runtime instead of baking the catalog into the template."),
  bullet("Expanded the producer-summary schema with projectSetup, trackLayout, routingBlueprint, warpGuide, workflowStage, trackContext, and structured secretSauce.workflowSteps."),
  bullet("Added semantic validation for device, parameter, deviceFamily, and trackContext, but surfaced mismatches as diagnostics.validationWarnings instead of hard-failing the response."),
  bullet("Kept third-party plugins out of scope by policy so the model could only recommend Native or Max for Live devices from the approved catalog."),
  subHeading("Representative Files"),
  fileBullet("apps/backend/server.py"),
  fileBullet("apps/backend/prompts/phase2_system.txt"),
  fileBullet("apps/backend/prompts/live12_device_catalog.json"),
  fileBullet("apps/backend/tests/test_server.py"),
  fileBullet("apps/ui/src/types.ts"),
  subHeading("Why It Matters"),
  numbered("Ableton users immediately see familiar device names and parameter labels instead of hallucinated tools."),
  numbered("The output became usable as a session scaffold, not just a descriptive summary."),
  numbered("Backend truthfulness improved without making the whole response brittle."),

  sectionHeading("Phase B — Frontend Rendering and Workflow Context"),
  subHeading("Plain-English Summary"),
  body(
    "Phase B turned the new backend structure into something a producer can actually follow in the app. Instead of hiding the work in raw payloads, the UI now shows where tracks should go, how routing should work, what the warp strategy is, and where caution is needed.",
  ),
  subHeading("Technical Changes"),
  bullet("Used one superset Phase2Result type and schema-version gating so interpretation.v1 stays on the old UI path while interpretation.v2 unlocks the new sections."),
  bullet("Rendered new v2-only sections for Project Setup, Track Layout, Routing Blueprint, and Warp Guide."),
  bullet("Updated arrangement rendering to show sceneName, abletonAction, and automationFocus per segment."),
  bullet("Updated mix-chain and recommendation cards to show deviceFamily, trackContext, and workflowStage metadata."),
  bullet("Added a caution banner for validationWarnings so suspicious catalog mismatches are visible instead of silently trusted."),
  bullet("Preferred structured secretSauce.workflowSteps over legacy implementationSteps when available."),
  subHeading("Representative Files"),
  fileBullet("apps/ui/src/components/AnalysisResults.tsx"),
  fileBullet("apps/ui/src/components/analysisResultsViewModel.ts"),
  fileBullet("apps/ui/src/services/analysisRunsClient.ts"),
  fileBullet("apps/ui/src/App.tsx"),
  fileBullet("apps/ui/tests/services/analysisResultsUi.test.ts"),
  fileBullet("apps/ui/tests/smoke/ui-details.spec.ts"),
  subHeading("Why It Matters"),
  numbered("A non-technical user can now see the session plan directly in the interface instead of reading raw JSON."),
  numbered("Older runs still render normally, so the rollout did not strand existing analysis history."),
  numbered("Caution states are visible but not destructive, which keeps useful guidance on screen."),

  sectionHeading("Phase C — Optional Audio Observations"),
  subHeading("Plain-English Summary"),
  body(
    "Phase C gave Gemini a legitimate audio-listening job. The model can now describe what it hears that DSP does not measure well, such as timbral character, production signatures, and mix feel, but those observations are isolated so they do not contaminate the measured blueprint.",
  ),
  subHeading("Technical Changes"),
  bullet("Extended interpretation.v2 additively with optional audioObservations instead of creating interpretation.v3."),
  bullet("Defined audioObservations as soundDesignFingerprint, elementCharacter, productionSignatures, and mixContext."),
  bullet("Added explicit audio-listening tasks to the prompt for sound design fingerprinting, timbral character per element, arrangement energy feel, and production technique signatures."),
  bullet("Added a strict prompt boundary: audioObservations must hold audio-only findings and must not restate sonicElements, mixAndMasterChain, or abletonRecommendations."),
  bullet("Kept catalog validation out of audioObservations because it is perceptual rather than device-referenced."),
  bullet("Sanitized malformed audioObservations out of the payload so the rest of phase2 survives intact."),
  bullet("Rendered a clearly labeled perceptual panel only when audioObservations is present, with no empty fallback state."),
  subHeading("Representative Files"),
  fileBullet("apps/backend/server.py"),
  fileBullet("apps/backend/prompts/phase2_system.txt"),
  fileBullet("apps/ui/src/types.ts"),
  fileBullet("apps/ui/src/components/AnalysisResults.tsx"),
  fileBullet("apps/ui/tests/services/analysisRunsClient.test.ts"),
  subHeading("Why It Matters"),
  numbered("ASA now makes better use of the audio file already being sent to Gemini."),
  numbered("Perceptual notes are useful to producers without pretending to be measured truth."),
  numbered("A malformed optional field can no longer wipe out a valid producer-summary result."),

  sectionHeading("Cross-Phase Compatibility Rules"),
  bullet("interpretation.v1 remains readable in the UI for older producer-summary runs."),
  bullet("interpretation.v2 remains the active producer-summary schema for new runs."),
  bullet("audioObservations is optional because older interpretation.v2 runs predate Phase C."),
  bullet("validationWarnings remain non-fatal and are shown as caution, not as a blocking error state."),
  bullet("Third-party plugins remain out of scope across all three phases."),

  sectionHeading("Verification Completed"),
  body("The work across these phases was verified with backend unit tests, frontend unit tests, targeted browser smoke tests, and production builds."),
  bullet("cd apps/backend && ./venv/bin/python -m unittest tests.test_server"),
  bullet("cd apps/ui && npx vitest run tests/services/analysisResultsUi.test.ts tests/services/analysisRunsClient.test.ts"),
  bullet("cd apps/ui && npm run test:smoke -- tests/smoke/ui-details.spec.ts"),
  bullet("cd apps/ui && npm run build"),
  body(
    "Phase B also passed a broader smoke run earlier in the implementation cycle, which confirmed that the new rendering path did not break the normal app flow.",
  ),

  sectionHeading("Current Limits"),
  bullet("The curated Live 12 catalog is intentionally smaller than the full Ableton device universe because ASA only needs the supported recommendation surface."),
  bullet("audioObservations is descriptive and intentionally avoids plugin-brand guessing, exact device claims, or measured-value overrides."),
  bullet("The system is still local-development software, not a production-ready cloud service with authentication and multi-user storage."),
];

const doc = new Document({
  styles: {
    default: {
      document: {
        run: {
          font: "Arial",
          size: 22,
        },
      },
    },
    paragraphStyles: [
      {
        id: "Title",
        name: "Title",
        basedOn: "Normal",
        run: { size: 44, bold: true, color: "111111", font: "Arial" },
        paragraph: { spacing: { before: 120, after: 120 }, alignment: AlignmentType.CENTER },
      },
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 30, bold: true, color: "111111", font: "Arial" },
        paragraph: { spacing: { before: 220, after: 140 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 24, bold: true, color: "333333", font: "Arial" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullet-list",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
      {
        reference: "numbered-list",
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun("ASA Truthfulness Pass Documentation — Page "),
                new TextRun({ children: [PageNumber.CURRENT] }),
                new TextRun(" of "),
                new TextRun({ children: [PageNumber.TOTAL_PAGES] }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log(outputPath);
});
