# Genre Classification Validation Corpus

## Ground Truth Definitions

### Track 1: DJ Metatron - "U'll Be The King Of The Stars"
- **File**: `/Users/christiansmith/Music/Library/Dj Metatron/A1. DJ Metatron - U'll Be The King Of The Stars.mp3`
- **Expected**: ACID / PSYCHEDELIC ELECTRONICA or PURE AMBIENT
- **Why**: DJ Metatron/Traumprinz style - very slow, emotional, ambient techno. Minimal drums, ethereal pads, slow BPM (~90-100). Should have low kickSwing, low inharmonicity.

### Track 2: Floorplan - "We Magnify His Name"
- **File**: `/Users/christiansmith/Music/Library/Floorplan - Sanctified EP/01-floorplan-we_magnify_his_name.mp3`
- **Expected**: HOUSE / ELECTRO (Gospel House)
- **Why**: Robert Hood's gospel house project. Tight 4/4 grid, organ stabs, vocals. BPM around 125, low swing, sub-bass mono. Should match HOUSE/ELECTRO with odd/even ratio from organ chords.

### Track 3: Blawan - "Getting Me Down"
- **File**: `/Users/christiansmith/Music/Library/Blawan - Getting Me Down (2011)/Blawan - Getting Me Down.flac`
- **Expected**: ACID TECHNO / TECHNO or ACID RAVE
- **Why**: Industrial UK techno, distorted kick, metallic percussion. High energy, BPM around 130-135. High inharmonicity from distortion.

### Track 4: Prince of Denmark - "Cut 02"
- **File**: `/Users/christiansmith/Music/Library/Prince of Denmark - 2013 - The Body/01 - Cut 02.flac`
- **Expected**: DARK ELECTRONICA / DEEP TECHNO
- **Why**: Giegling-style deep techno, muffled, underwater aesthetic. Low spectral centroid, moderate inharmonicity. Dark and atmospheric.

### Track 5: Nu Guinea - "Je Vulesse"
- **File**: `/Users/christiansmith/Music/Library/Nu Guinea   Nuova Napoli/02 Je Vulesse.mp3`
- **Expected**: HOUSE / ELECTRO (Disco/Nu-Disco)
- **Why**: Italian disco/funk revival, live instrumentation feel. BPM around 110-120, groovy but tight. Organic drums but quantized.

### Track 6: Sylvester - "Won't You Let Me Love You"
- **File**: `/Users/christiansmith/Music/Library/1982 sylvester - all i need (do ya wanna funk)/07 - Sylvester - Won't You Let Me Love You.mp3`
- **Expected**: HIP-HOP / SOUL (Classic Disco/Soul)
- **Why**: Classic disco/soul from 1982. Live drums, orchestral elements. BPM around 110-120, but with human swing and high accent variance from live playing.

### Track 7: DMX Krew - "Come To Me"
- **File**: `/Users/christiansmith/Music/Library/(2010) Selected Label Works 2/10 DMX Krew - Come To Me.mp3`
- **Expected**: HOUSE / ELECTRO (Electro/Electro-Funk)
- **Why**: Ed DMX electro style. 808 drums, synth bass, robotic. Tight grid, low swing, but electro-funk character with odd harmonics.

### Track 8: Old School Belgian Club Classics - "Echo Drop (Hard)"
- **File**: `/Users/christiansmith/Music/Library/Old School Belgian Clubs Classics/Echo Drop - A - Taiko - Echo Drop (Hard).flac`
- **Expected**: ACID TECHNO / TECHNO (New Beat/Early Techno)
- **Why**: Belgian new beat - slow techno around 110-120 BPM but with industrial character. Heavy distorted kick, aggressive.

### Track 9: Squarepusher - "Terminal Slam"
- **File**: `/Users/christiansmith/Music/Library/Be Up A Hello/07 Terminal Slam.mp3`
- **Expected**: DRUM & BASS/BREAKBEAT (Jungle/Drumfunk)
- **Why**: Squarepusher's jungle revival track. Fast breakbeats, amen chops, sub-bass. BPM around 160-170, complex rhythms.

### Track 10: DJ Metatron - "A Rave Loveletter"
- **File**: `/Users/christiansmith/Music/Library/Dj Metatron/C1. A Rave Loveletter.flac`
- **Expected**: ACID RAVE / HIGH-ENERGY ELECTRONIC
- **Why**: Already validated - fast (130 BPM), euphoric, high inharmonicity from distorted synths.

## Classification Criteria Reference

### Step 1 - Rhythm Profile
- **ELECTRONIC DANCE**: kickSwing < 0.15 AND kickAccentVariance < 0.15
- **HIP-HOP/FUNK**: kickSwing > 0.35 AND kickAccentVariance > 0.20
- **AMBIENT/EXPERIMENTAL**: kickSwing < 0.12 AND kickAccentVariance < 0.05
- **DRUM & BASS/BREAKBEAT**: kickAccentVariance > 0.28 AND 0.15 <= kickSwing <= 0.35
- **LOOSE/PSYCHEDELIC**: kickSwing > 0.50 AND kickAccentVariance < 0.10
- **MIXED/AMBIGUOUS**: No clean match

### Step 2 - Synthesis Profile (Electronic Dance)
- **ACID RAVE**: BPM 125-150 AND inharmonicity 0.18-0.24
- **ACID TECHNO**: 2 of 3: inharmonicity > 0.22, BPM 128-150, subBassMono
- **ACID PSYCHEDELIC**: inharmonicity > 0.20 AND BPM 90-128
- **HOUSE/ELECTRO**: inharmonicity 0.05-0.18 AND oddToEvenRatio > 1.2 AND kickSwing < 0.30
- **EDM**: pumpingStrength > 0.4 AND pumpingConfidence > 0.35 AND segmentLufsRange > 5

### Step 2 - Synthesis Profile (Loose/Psychedelic)
- **ACID / PSYCHEDELIC ELECTRONICA**: inharmonicity > 0.10 AND BPM 85-125
- **DARK / EXPERIMENTAL ELECTRONICA**: inharmonicity <= 0.10 AND BPM 85-125

### Step 2 - Synthesis Profile (Ambient/Experimental)
- **DARK ELECTRONICA**: inharmonicity > 0.15 AND spectralCentroid < 4000
- **PURE AMBIENT**: inharmonicity < 0.10 AND kickAccentVariance < 0.05

### Step 2 - Synthesis Profile (Hip-Hop/Funk)
- **HIP-HOP / SOUL**: BPM 60-100
- **TRAP**: BPM 130-160 AND kickAccentVariance > 0.30

### Step 2 - Synthesis Profile (Drum & Bass/Breakbeat)
- **DRUM & BASS**: BPM 155-185
- **BREAKBEAT / UK GARAGE**: BPM 130-155
