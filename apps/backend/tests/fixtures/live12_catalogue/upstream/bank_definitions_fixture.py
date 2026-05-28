# Test fixture mirroring the shape of the upstream
# `Push2/custom_bank_definitions.py` (gluon/AbletonLive12_MIDIRemoteScripts).
# This is a static-source fixture: the generator parses it via `ast` and
# never executes it, so the `IndexedDict`, `BANK_*_KEY`, and `use(...)`
# symbols are intentionally undefined here. The generator extracts the
# device/parameter metadata purely from the AST shape.
from __future__ import absolute_import

OPTIONS_KEY = "Options"

RACK_BANKS = IndexedDict((
    (
        "Macros",
        {BANK_PARAMETERS_KEY: ("Macro 1", "Macro 2", "Macro 3", "Macro 4")},
    ),
))

BANK_DEFINITIONS = {
    "AudioEffectGroupDevice": RACK_BANKS,
    "Saturator": IndexedDict((
        (
            BANK_MAIN_KEY,
            {
                BANK_PARAMETERS_KEY: ("Type", "Drive", "Base", "Frequency", "Width", "Depth", "Output", "Dry/Wet"),
                OPTIONS_KEY: ("", "Color", "", "", "", "Soft Clip", ""),
            },
        ),
        (
            "Waveshaper",
            {BANK_PARAMETERS_KEY: ("Type", "WS Drive", "WS Curve", "WS Depth", "WS Lin", "WS Damp", "WS Period", "Dry/Wet")},
        ),
    )),
    "Eq8": IndexedDict((
        (
            BANK_MAIN_KEY,
            {
                BANK_PARAMETERS_KEY: (
                    "1 Filter Type A",
                    "1 Frequency A",
                    "1 Gain A",
                    "1 Resonance A",
                    "Band",
                    "Eq Mode",
                    "Edit Mode",
                    "Oversampling",
                ),
            },
        ),
    )),
    "Operator": IndexedDict((
        (
            BANK_MAIN_KEY,
            {
                BANK_PARAMETERS_KEY: (
                    "Algorithm",
                    use("Osc A Wave").with_name("Wave").if_parameter("Oscillator").has_value("Osc A").else_use("Osc B Wave").with_name("Wave"),
                    use("Osc A Coarse").if_parameter("Oscillator").has_value("Osc A").else_use("Osc B Coarse"),
                    "Volume",
                ),
                OPTIONS_KEY: ("", "", "", ""),
            },
        ),
    )),
}
