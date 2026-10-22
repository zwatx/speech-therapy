"""Reviewed CMU source notices and predeclared engineering sample profiles."""
import re

LICENSE_HASHES = {
    "bdl": "469adc0262e10d84fb9658fa6181c883586415b5692f6bfbc2fde65dfc63f5c5",
    "rms": "8f31f65865b28dbd5e6a424af4a3ce6b6833b1aab14e531c272248e34917acf4",
    "slt": "469adc0262e10d84fb9658fa6181c883586415b5692f6bfbc2fde65dfc63f5c5",
    "awb": "469adc0262e10d84fb9658fa6181c883586415b5692f6bfbc2fde65dfc63f5c5",
    "clb": "e9cd64052c3dc9d2331682b929697b8f20c9d4595b43ebbadbd828535a104a77",
    "jmk": "469adc0262e10d84fb9658fa6181c883586415b5692f6bfbc2fde65dfc63f5c5",
}

# (split, first prompt, last candidate prompt, accepted clip count).
PROFILES = {
    "single-speaker-v1": {
        "bdl": ("train", 1, 80, 32), "rms": ("calibration", 101, 160, 12), "slt": ("test", 201, 260, 12),
    },
    "four-speaker-v1": {
        "bdl": ("train", 1, 80, 48), "awb": ("train", 1, 80, 48),
        "clb": ("train", 1, 80, 48), "jmk": ("train", 1, 80, 48),
        "rms": ("calibration", 101, 160, 12), "slt": ("test", 201, 260, 12),
    },
}


def validate_profile_selection(selected: list[dict], profile: str) -> None:
    if profile not in PROFILES:
        raise ValueError("Unsupported corpus profile")
    if not isinstance(selected, list) or any(not isinstance(item, dict) for item in selected):
        raise ValueError("Source selection must be a list of records")
    speakers = PROFILES[profile]
    counts = {speaker: 0 for speaker in speakers}
    used = set()
    for item in selected:
        speaker = item.get("speaker")
        if speaker not in speakers:
            raise ValueError("Source selection contains an unexpected speaker")
        split, first, last, _ = speakers[speaker]
        utterance = item.get("utterance", "")
        if (not isinstance(utterance, str) or not re.fullmatch(r"arctic_a\d{4}", utterance)
                or not first <= int(utterance[-4:]) <= last or item.get("split") != split
                or (speaker, utterance) in used):
            raise ValueError("Source selection changes a predefined speaker/prompt partition")
        used.add((speaker, utterance))
        counts[speaker] += 1
    if any(counts[s] != speakers[s][3] for s in speakers):
        raise ValueError("Source selection does not contain the profile's exact clip counts")
