import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "src" / "generate_short.py"
SPEC = importlib.util.spec_from_file_location("generate_short", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def alignment(text: str):
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * 0.1 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * 0.1 for i in range(len(text))],
    }


def test_words_from_alignment_preserves_turkish_text():
    words = MODULE.words_from_alignment(alignment("Otonom araç güvenliği artırır."))
    assert [item[0] for item in words] == ["Otonom", "araç", "güvenliği", "artırır."]
    assert words[0][1] == 0
    assert words[-1][2] > words[-1][1]


def test_caption_groups_are_short_and_timed():
    captions = MODULE.captions_from_alignment(
        alignment("Bu sistem çevrim süresini ölçer ve riskli bölgelerde güvenliği artırır.")
    )
    assert captions
    assert all(item.start < item.end for item in captions)
    assert all(len(item.text.split()) <= 6 for item in captions)


def test_ass_time_rounding():
    assert MODULE.ass_time(61.237) == "0:01:01.24"
