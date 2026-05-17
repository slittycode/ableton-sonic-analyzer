import {
  buildArrangementViewModel,
  buildMelodyInsights,
  buildMixChainGroups,
  buildPatchCards,
  buildPatchGroups,
  buildSonicElementCards,
  toConfidenceBadges,
  truncateAtSentenceBoundary,
  truncateBySentenceCount,
} from '../../src/components/analysisResultsViewModel';
import { MeasurementResult, Phase2Result, TranscriptionDetail } from '../../src/types';

const measurement: MeasurementResult = {
  bpm: 126,
  bpmConfidence: 0.93,
  key: 'F minor',
  keyConfidence: 0.88,
  timeSignature: '4/4',
  durationSeconds: 210.6,
  lufsIntegrated: -7.9,
  truePeak: -0.2,
  stereoWidth: 0.09,
  stereoCorrelation: 0.84,
  spectralBalance: {
    subBass: -0.7,
    lowBass: 1.2,
    lowMids: 0.0,
    mids: -0.3,
    upperMids: 0.4,
    highs: 1,
    brilliance: 0.8,
  },
  melodyDetail: {
    noteCount: 4,
    notes: [
      { midi: 60, onset: 0.2, duration: 0.3 },
      { midi: 64, onset: 0.8, duration: 0.2 },
      { midi: 67, onset: 1.2, duration: 0.4 },
      { midi: 72, onset: 1.9, duration: 0.3 },
    ],
    dominantNotes: [60, 64, 67],
    pitchRange: { min: 60, max: 72 },
    pitchConfidence: 0.72,
    midiFile: '/tmp/example.mid',
    sourceSeparated: true,
    vibratoPresent: false,
    vibratoExtent: 0,
    vibratoRate: 0,
    vibratoConfidence: 0.1,
  },
};

const pitchNote: TranscriptionDetail = {
  transcriptionMethod: 'torchcrepe-viterbi',
  noteCount: 6,
  averageConfidence: 0.83,
  stemSeparationUsed: true,
  fullMixFallback: false,
  stemsTranscribed: ['bass', 'other'],
  dominantPitches: [
    { pitchMidi: 48, pitchName: 'C3', count: 4 },
    { pitchMidi: 55, pitchName: 'G3', count: 3 },
  ],
  pitchRange: {
    minMidi: 48,
    maxMidi: 79,
    minName: 'C3',
    maxName: 'G5',
  },
  notes: [
    {
      pitchMidi: 48,
      pitchName: 'C3',
      onsetSeconds: 0.2,
      durationSeconds: 0.3,
      confidence: 0.81,
      stemSource: 'bass',
    },
    {
      pitchMidi: 79,
      pitchName: 'G5',
      onsetSeconds: 0.8,
      durationSeconds: 0.2,
      confidence: 0.85,
      stemSource: 'other',
    },
  ],
};

describe('analysisResultsViewModel helpers', () => {
  it('truncates long text at sentence boundaries', () => {
    const long = `${'A'.repeat(610)}. Final sentence should not be included.`;
    const output = truncateAtSentenceBoundary(long, 600);

    expect(output.endsWith('...')).toBe(true);
    expect(output.length).toBeLessThanOrEqual(603);
  });

  it('caps sentence count while preserving sentence boundaries', () => {
    const input = 'One sentence. Two sentence. Three sentence. Four sentence.';
    const output = truncateBySentenceCount(input, 3);

    expect(output).toBe('One sentence. Two sentence. Three sentence....');
  });

  // Audit Finding #4: confidence badges now return a canonical ConfidenceBand
  // (Solid / Workable / Rough / Unreliable) instead of the legacy three-level
  // enum. The 3-level → 4-band mismatch surfaces here: scalar 0.5-0.79 maps
  // to "workable" (used to be "Moderate"), scalar 0.25-0.49 maps to "rough"
  // (used to be "Low") — an intentional refinement.
  it('normalizes confidence badges to friendly labels and canonical bands', () => {
    const badges = toConfidenceBadges([
      { field: 'Key Signature', value: '0.62', reason: 'Measured confidence' },
      { field: 'Melody Transcription', value: 'LOW', reason: 'Weak melodic signal' },
      { field: 'True Peak', value: 'HIGH', reason: 'Stable result' },
    ]);

    expect(badges).toHaveLength(3);
    expect(badges[0].label).toBe('Key');
    expect(badges[0].band?.id).toBe('workable');
    expect(badges[1].label).toBe('Melody');
    expect(badges[1].band?.id).toBe('rough');
    expect(badges[2].label).toBe('Peak');
    expect(badges[2].band?.id).toBe('solid');
  });

  // Audit Finding #4: unparseable values produce `band: null` so the render
  // site can filter them rather than show a misleading default band.
  it('returns band: null entries for unparseable confidence values', () => {
    const badges = toConfidenceBadges([
      { field: 'Key Signature', value: 'completely unparseable', reason: 'whatever' },
      { field: 'True Peak', value: '0.95', reason: 'real value' },
    ]);

    expect(badges).toHaveLength(2);
    expect(badges[0].band).toBeNull();
    expect(badges[1].band?.id).toBe('solid');
  });

  it('builds arrangement timeline segments and novelty markers', () => {
    const arrangement = buildArrangementViewModel(measurement, {
      summary: 'Intro to drop transition.',
      segments: [
        { index: 1, startTime: 0, endTime: 32, lufs: -9.2, description: 'Intro: low energy opener' },
        { index: 2, startTime: 32, endTime: 96, lufs: -7.6, description: 'Drop: full range impact' },
      ],
      noveltyNotes: 'Events at 12.5s and 74.0s indicate transitions.',
    });

    expect(arrangement).not.toBeNull();
    expect(arrangement?.segments[0].name).toBe('INTRO');
    expect(arrangement?.segments[1].name).toBe('DROP');
    expect(arrangement?.segments[0].lufs).toBe(-9.2);
    expect(arrangement?.segments[1].lufs).toBe(-7.6);
    expect(arrangement?.noveltyNotes).toContain('12.5s');
    expect(arrangement?.noveltyMarkers.length).toBe(2);
  });

  it('caps width & stereo card content at six sentences', () => {
    const sonicCards = buildSonicElementCards(measurement, {
      kick: 'Kick sentence.',
      bass: 'Bass sentence.',
      melodicArp: 'Arp sentence.',
      grooveAndTiming: 'Groove sentence.',
      effectsAndTexture: 'Fx sentence.',
      widthAndStereo:
        'One sentence. Two sentence. Three sentence. Four sentence. Five sentence. Six sentence. Seven sentence.',
      harmonicContent: 'Harmony sentence.',
    });

    const widthCard = sonicCards.find((card) => card.id === 'widthAndStereo');
    const melodicCard = sonicCards.find((card) => card.id === 'melodicArp');
    expect(widthCard).toBeDefined();
    expect(melodicCard?.transcriptionDerived).toBe(true);
    // The fixture has melodyDetail but no transcriptionDetail, so the label
    // is the full-mix-draft variant rather than "Transcribed Notes". When a
    // run actually has transcriptionDetail.noteCount > 0, the label becomes
    // "Transcribed Notes" instead — see analysisResultsViewModel.ts.
    expect(
      melodicCard?.measurements.some((m) => m.label === 'Melody Notes (full-mix draft)'),
    ).toBe(true);
    expect(widthCard?.description.includes('Seven sentence.')).toBe(false);
  });

  it('keeps protected singleton mix groups visually separate', () => {
    const groups = buildMixChainGroups(
      measurement,
      [
        {
          order: 1,
          device: 'Drum Buss',
          deviceFamily: 'NATIVE',
          trackContext: 'Drum Group',
          workflowStage: 'MIX',
          parameter: 'Drive',
          value: '6 dB',
          reason: 'Adds drum bite and transient character.',
        },
        {
          order: 2,
          device: 'EQ Eight',
          deviceFamily: 'NATIVE',
          trackContext: 'Bass Group',
          workflowStage: 'MIX',
          parameter: 'Low Cut',
          value: '30 Hz',
          reason: 'Cleans up sub energy in bass layers.',
        },
        {
          order: 3,
          device: 'Auto Filter',
          deviceFamily: 'NATIVE',
          trackContext: 'Return:Return A',
          workflowStage: 'ARRANGEMENT',
          parameter: 'High Shelf',
          value: '+2.0 dB @ 10 kHz',
          reason: 'Adds sparkle to hi-hats and vocal chops in the top end.',
        },
      ],
      {
        kick: 'Kick sentence.',
        bass: 'Bass sentence.',
        melodicArp: 'Arp sentence.',
        grooveAndTiming: 'Groove sentence.',
        effectsAndTexture: 'Top end details from hi-hats and synth sweeps.',
        widthAndStereo: 'Stereo widening on high hats only.',
      },
    );

    expect(groups).toEqual([
      expect.objectContaining({
        name: 'DRUM PROCESSING',
        cards: [expect.objectContaining({ device: 'Drum Buss' })],
      }),
      expect.objectContaining({
        name: 'BASS PROCESSING',
        cards: [expect.objectContaining({ device: 'EQ Eight' })],
      }),
      expect.objectContaining({
        name: 'HIGH-END DETAIL',
        cards: [expect.objectContaining({ device: 'Auto Filter' })],
      }),
      expect.objectContaining({
        name: 'MASTER BUS',
        cards: [expect.objectContaining({ device: 'Limiter' })],
      }),
    ]);
    expect(groups[2]?.annotation).toContain('Annotated high-end focus');
    expect(groups.some((group) => group.name.includes('DRUM PROCESSING /'))).toBe(false);
    expect(groups.some((group) => group.name.includes('HIGH-END DETAIL /'))).toBe(false);
    // Audit N3/N8: workflowStage values are prettified at the view-model
    // layer so producers see "Mix" / "Arrangement" instead of the raw
    // Phase 2 enum `MIX` / `ARRANGEMENT`.
    expect(groups[0]?.cards[0]).toMatchObject({
      deviceFamily: 'NATIVE',
      trackContext: 'Drum Group',
      workflowStage: 'Mix',
    });
    expect(groups[2]?.cards[0]).toMatchObject({
      trackContext: 'Return:Return A',
      workflowStage: 'Arrangement',
    });
  });

  it('merges only adjacent unprotected singleton groups and caps merges at two groups', () => {
    const groups = buildMixChainGroups(
      measurement,
      [
        {
          order: 1,
          device: 'Operator',
          parameter: 'Detune',
          value: '0.08',
          reason: 'Shapes synth lead tone and melodic movement.',
        },
        {
          order: 2,
          device: 'Saturator',
          parameter: 'Drive',
          value: '2.5 dB',
          reason: 'Adds mid body and clarity to the center image.',
        },
      ],
      {
        kick: 'Kick sentence.',
        bass: 'Bass sentence.',
        melodicArp: 'Arp sentence.',
        grooveAndTiming: 'Groove sentence.',
        effectsAndTexture: 'FX sentence.',
      },
    );

    expect(groups).toEqual([
      expect.objectContaining({
        name: 'SYNTH / MELODIC / MID PROCESSING',
        cards: expect.arrayContaining([
          expect.objectContaining({ device: 'Operator' }),
          expect.objectContaining({ device: 'Saturator' }),
        ]),
      }),
      expect.objectContaining({
        name: 'MASTER BUS',
        cards: [expect.objectContaining({ device: 'Limiter' })],
      }),
    ]);
    expect(groups.every((group) => group.name.split(' / ').length <= 3)).toBe(true);
  });

  // Audit Finding #1A: buildRoleSentence used to fabricate "{stage phrase} by
  // {verb}" by lowercasing the first letter of Gemini's reason and prepending a
  // category label. Because Gemini's `reason` is a present-tense clause, this
  // produced ungrammatical splices ("Controls bass energy by ensures..."). The
  // current behavior renders the reason verbatim with a capitalized first letter
  // and trailing period; only the HIGH-END cue suffix survives.
  it('capitalizes Gemini reason without prepending a category label', () => {
    const groups = buildMixChainGroups(
      measurement,
      [
        {
          order: 1,
          device: 'EQ Eight',
          trackContext: 'Bass Group',
          workflowStage: 'MIX',
          parameter: 'Low Cut',
          value: '30 Hz',
          reason: 'ensures the extreme low-end mono envelope stays tight under the kick.',
        },
      ],
      {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
    );

    const card = groups.flatMap((g) => g.cards).find((c) => c.device === 'EQ Eight');
    expect(card).toBeDefined();
    expect(card?.role).toBe('Ensures the extreme low-end mono envelope stays tight under the kick.');
    expect(card?.role).not.toContain(' by ');
    // The old prefix labels — none of them should appear inside the role text now.
    expect(card?.role).not.toContain('Controls bass energy');
    expect(card?.role).not.toContain('Shapes drum impact');
    expect(card?.role).not.toContain('Supports melodic clarity');
  });

  it('appends high-end cue suffix when group is HIGH-END DETAIL and cues are present', () => {
    const groups = buildMixChainGroups(
      measurement,
      [
        {
          order: 1,
          device: 'Auto Filter',
          parameter: 'High Shelf',
          value: '+2.0 dB @ 10 kHz',
          reason: 'Adds sparkle to the hi-hats and synth sweeps in the top end.',
        },
      ],
      {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'Top-end details from hi-hats and synth sweeps.',
      },
    );

    const card = groups.find((g) => g.name === 'HIGH-END DETAIL')?.cards[0];
    expect(card).toBeDefined();
    expect(card?.role).toMatch(/^Adds sparkle to the hi-hats and synth sweeps in the top end \(for .+\)\.$/);
    expect(card?.role).not.toContain(' by ');
  });

  it('omits high-end cue suffix when no cues are present', () => {
    const groups = buildMixChainGroups(
      measurement,
      [
        {
          order: 1,
          device: 'Drum Buss',
          parameter: 'Drive',
          value: '6 dB',
          reason: 'Adds bite and transient character to the drum bus.',
        },
      ],
      {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
    );

    const card = groups.find((g) => g.name === 'DRUM PROCESSING')?.cards[0];
    expect(card).toBeDefined();
    expect(card?.role).toBe('Adds bite and transient character to the drum bus.');
    expect(card?.role).not.toMatch(/\(for /);
  });

  it('builds expanded patch cards with at least three parameters', () => {
    const phase2 = {
      trackCharacter: 'Character sentence.',
      detectedCharacteristics: [{ name: 'Dynamics', confidence: 'HIGH', explanation: 'Strong profile' }],
      arrangementOverview: {
        summary: 'Summary',
        segments: [{ index: 1, startTime: 0, endTime: 20, description: 'Intro segment' }],
      },
      sonicElements: {
        kick: 'Kick',
        bass: 'Bass',
        melodicArp: 'Arp',
        grooveAndTiming: 'Groove',
        effectsAndTexture: 'FX',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [{ field: 'Key Signature', value: '0.7', reason: 'Reason' }],
      abletonRecommendations: [
        {
          device: 'Operator',
          deviceFamily: 'NATIVE',
          trackContext: 'Bass Group',
          workflowStage: 'SOUND_DESIGN',
          category: 'Synth',
          parameter: 'Coarse',
          value: '1.00',
          reason: 'Matches tonal center.',
          advancedTip: 'Modulate coarse slowly.',
        },
      ],
    } as Phase2Result;

    const cards = buildPatchCards(
      {
        ...measurement,
        transcriptionDetail: pitchNote,
      },
      phase2,
    );

    expect(cards.length).toBeGreaterThan(0);
    expect(cards[0].parameters.length).toBeGreaterThanOrEqual(3);
    expect(cards[0].whyThisWorks.length).toBeGreaterThan(10);
    expect(cards.some((card) => /stereo|width/i.test(card.device))).toBe(true);
    expect(cards.some((card) => card.transcriptionDerived)).toBe(true);
    // Audit N3/N8: workflowStage prettified at the view-model layer.
    expect(cards[0]).toMatchObject({
      deviceFamily: 'NATIVE',
      trackContext: 'Bass Group',
      workflowStage: 'Sound design',
    });
  });

  it('groups patch cards into Mix Chain processing-stage buckets', () => {
    // Audit follow-up: buildPatchGroups buckets cards by Drum / Bass / Synth /
    // Mid / High-end / Master so the Patches section reads with the same
    // scannable structure as Mix Chain. Empty groups must be omitted; groups
    // must render in canonical GROUP_ORDER.
    const phase2 = {
      trackCharacter: 'Character sentence.',
      detectedCharacteristics: [{ name: 'Dynamics', confidence: 'HIGH', explanation: 'Strong profile' }],
      arrangementOverview: {
        summary: 'Summary',
        segments: [{ index: 1, startTime: 0, endTime: 20, description: 'Intro segment' }],
      },
      sonicElements: {
        kick: 'Kick',
        bass: 'Bass',
        melodicArp: 'Arp',
        grooveAndTiming: 'Groove',
        effectsAndTexture: 'FX',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [{ field: 'Key Signature', value: '0.7', reason: 'Reason' }],
      abletonRecommendations: [
        {
          device: 'Operator',
          deviceFamily: 'NATIVE',
          trackContext: 'Bass Group',
          workflowStage: 'SOUND_DESIGN',
          category: 'Synth',
          parameter: 'Coarse',
          value: '1.00',
          reason: 'Subby bass synth for the low end.',
        },
        {
          device: 'Drum Buss',
          deviceFamily: 'NATIVE',
          trackContext: 'Drum Group',
          workflowStage: 'MIX',
          category: 'Dynamics',
          parameter: 'Drive',
          value: '25%',
          reason: 'Adds punch to kick transients.',
        },
      ],
    } as Phase2Result;

    const groups = buildPatchGroups(
      {
        ...measurement,
        transcriptionDetail: pitchNote,
      },
      phase2,
    );

    expect(groups.length).toBeGreaterThanOrEqual(1);
    // Empty groups omitted.
    expect(groups.every((group) => group.cards.length > 0)).toBe(true);
    // Returns null phase2 → empty list (defensive — Phase 2 not produced this run).
    expect(buildPatchGroups(measurement, null)).toEqual([]);
    // Cross-check: flattening the groups yields the same cards as buildPatchCards.
    const flatFromGroups = groups.flatMap((group) => group.cards);
    const flatFromCards = buildPatchCards(
      {
        ...measurement,
        transcriptionDetail: pitchNote,
      },
      phase2,
    );
    expect(flatFromGroups.length).toBe(flatFromCards.length);
  });

  // Audit Finding #1B: PatchCardViewModel.patchRole was deleted in favor of
  // letting the category chip + per-card whyThisWorks carry the bucket label
  // and the actionable explanation. The category chip lives in the rendered
  // card; whyThisWorks now provides the per-card uniqueness that mapPatchRole
  // (a 7-key fallback) couldn't.
  it('PatchCardViewModel no longer carries a patchRole field', () => {
    const phase2: Phase2Result = {
      trackCharacter: 'Character.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Summary', segments: [] },
      sonicElements: {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [],
      abletonRecommendations: [
        {
          device: 'Wavetable',
          deviceFamily: 'NATIVE',
          trackContext: 'Synth Group',
          workflowStage: 'SOUND_DESIGN',
          category: 'SYNTHESIS',
          parameter: 'Position',
          value: '0.42',
          reason: 'Dialed for the supersaw character with high-pass at 120 Hz.',
        },
      ],
    } as Phase2Result;

    const cards = buildPatchCards(measurement, phase2);
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      expect('patchRole' in card).toBe(false);
    }
  });

  // Audit Finding #1B: removing card.patchRole from the buildPatchGroups
  // text-concat shrinks the keyword surface for inferProcessingGroup. This
  // test guards the SYNTH / MELODIC routing for a representative synth card.
  it('buildPatchGroups still routes a synth card into SYNTH / MELODIC after dropping patchRole', () => {
    const phase2: Phase2Result = {
      trackCharacter: 'Character.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Summary', segments: [] },
      sonicElements: {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
      mixAndMasterChain: [],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [],
      abletonRecommendations: [
        {
          device: 'Wavetable',
          deviceFamily: 'NATIVE',
          trackContext: 'Synth Group',
          workflowStage: 'SOUND_DESIGN',
          category: 'SYNTHESIS',
          parameter: 'Position',
          value: '0.42',
          reason: 'Builds the supersaw lead character with detune across voices.',
        },
      ],
    } as Phase2Result;

    const groups = buildPatchGroups(measurement, phase2);
    const synthGroup = groups.find((g) => g.name === 'SYNTH / MELODIC');
    expect(synthGroup).toBeDefined();
    expect(synthGroup?.cards.some((c) => c.device === 'Wavetable')).toBe(true);
  });

  // Audit Finding #1B (overlap): when Gemini emits the same device in both
  // mixAndMasterChain and abletonRecommendations, the Patches section used to
  // re-list Mix Chain devices verbatim. buildPatchCards now filters case-
  // insensitively against the chain. Synthetic fallbacks (stereo width, MIDI
  // Clip Guide) are built from Phase 1 only and bypass the filter.
  it('buildPatchCards drops recommendations whose device also appears in mixAndMasterChain', () => {
    const phase2: Phase2Result = {
      trackCharacter: 'Character.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Summary', segments: [] },
      sonicElements: {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
      mixAndMasterChain: [
        {
          order: 1,
          device: 'Glue Compressor',
          deviceFamily: 'NATIVE',
          trackContext: 'Master',
          workflowStage: 'MASTER',
          parameter: 'Threshold',
          value: '-2 dB',
          reason: 'Cohesive master bus glue.',
        },
      ],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [],
      abletonRecommendations: [
        {
          device: 'Glue Compressor',
          deviceFamily: 'NATIVE',
          trackContext: 'Master',
          workflowStage: 'MASTER',
          category: 'DYNAMICS',
          parameter: 'Ratio',
          value: '2:1',
          reason: 'Redundant with the chain — should not surface as a patch.',
        },
        {
          device: 'Wavetable',
          deviceFamily: 'NATIVE',
          trackContext: 'Synth Group',
          workflowStage: 'SOUND_DESIGN',
          category: 'SYNTHESIS',
          parameter: 'Position',
          value: '0.5',
          reason: 'Builds the lead supersaw character.',
        },
      ],
    } as Phase2Result;

    const cards = buildPatchCards(measurement, phase2);
    expect(cards.some((c) => c.device === 'Glue Compressor')).toBe(false);
    expect(cards.some((c) => c.device === 'Wavetable')).toBe(true);
  });

  it('buildPatchCards is case-insensitive against chain device names', () => {
    const phase2: Phase2Result = {
      trackCharacter: 'Character.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Summary', segments: [] },
      sonicElements: {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
      },
      mixAndMasterChain: [
        {
          order: 1,
          device: 'AUTO FILTER',
          parameter: 'Cutoff',
          value: '2 kHz',
          reason: 'Mixchain filter sweep.',
        },
      ],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [],
      abletonRecommendations: [
        {
          device: 'auto filter',
          category: 'EFFECTS',
          parameter: 'Resonance',
          value: '0.4',
          reason: 'Lowercased device name — still a duplicate.',
        },
      ],
    } as Phase2Result;

    const cards = buildPatchCards(measurement, phase2);
    expect(cards.some((c) => /auto filter/i.test(c.device))).toBe(false);
  });

  it('synthetic stereo-width fallback card still appears even if Utility is in the chain', () => {
    const phase2: Phase2Result = {
      trackCharacter: 'Character.',
      detectedCharacteristics: [],
      arrangementOverview: { summary: 'Summary', segments: [] },
      sonicElements: {
        kick: 'Kick.',
        bass: 'Bass.',
        melodicArp: 'Arp.',
        grooveAndTiming: 'Groove.',
        effectsAndTexture: 'FX.',
        widthAndStereo: 'Tight low end, controlled high-end width on hi-hats.',
      },
      mixAndMasterChain: [
        {
          order: 1,
          device: 'Utility',
          parameter: 'Bass mono',
          value: '120 Hz',
          reason: 'Stereo discipline on the low end.',
        },
      ],
      secretSauce: { title: 'Sauce', explanation: 'Explain', implementationSteps: ['Step'] },
      confidenceNotes: [],
      abletonRecommendations: [],
    } as Phase2Result;

    const cards = buildPatchCards(measurement, phase2);
    // The synthetic Utility / Stereo Imager card is built from Phase 1 only
    // and must survive the chain dedup. Its device label intentionally
    // includes both names so a strict equality with chain "Utility" doesn't
    // match — that's the point of bypassing the filter.
    expect(cards.some((c) => c.id.endsWith('stereo-width'))).toBe(true);
  });

  it('builds melody insights from phase1 transcription payload', () => {
    const insights = buildMelodyInsights({
      ...measurement,
      transcriptionDetail: pitchNote,
    });

    expect(insights).not.toBeNull();
    expect(insights?.noteCount).toBe(6);
    expect(insights?.rangeLabel).toBe('C3 - G5');
    expect(insights?.dominantNotes).toEqual(['C3', 'G3']);
    expect(insights?.confidenceLabel).toBe('High');
    expect(insights?.isDraft).toBe(false);
  });
});
