"""CMU Arctic automatic alignment parsing; these are not expert production labels."""
from decimal import Decimal, InvalidOperation
import math

# Fixed Festival/CMU phone inventory, independent of the selected holdout labels.
ARCTIC_PHONES = "aa ae ah ao aw ax axr ay b ch d dh eh el em en er ey f g hh ih iy jh k l m n ng ow oy p pau r s sh t th uh uw v w y z zh".split()


def parse_timed_alignment(data: bytes, duration_seconds: float) -> list[tuple[Decimal, Decimal, str]]:
    """Preserve each automatic phone's exact decimal end times and inferred start."""
    if len(data) > 20_000:
        raise ValueError("Alignment exceeds size limit")
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Alignment must be UTF-8") from exc
    if not lines or lines[0].strip() != "#":
        raise ValueError("Unsupported Arctic label header")
    if (type(duration_seconds) not in (float, int) or not math.isfinite(duration_seconds)
            or not 0 < duration_seconds < 3600):
        raise ValueError("Invalid audio duration")
    duration = Decimal(str(duration_seconds))
    previous, phones = Decimal(0), []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3 or parts[1] != "125":
            raise ValueError("Invalid alignment row")
        try:
            end = Decimal(parts[0])
        except InvalidOperation as exc:
            raise ValueError("Invalid alignment time") from exc
        if not end.is_finite() or end <= previous or end > duration + Decimal("0.04"):
            raise ValueError("Alignment times are not increasing or exceed the waveform")
        if parts[2] not in ARCTIC_PHONES:
            raise ValueError("Unsupported aligned phone")
        phones.append((previous, end, parts[2]))
        previous = end
    if not phones or len(phones) > 100 or abs(previous - duration) > Decimal("0.05"):
        raise ValueError("Alignment must cover the complete waveform")
    return phones


def parse_alignment(data: bytes, duration_seconds: float) -> list[str]:
    """Return automatic phone tokens using the same timed-source validation."""
    return [phone for _, _, phone in parse_timed_alignment(data, duration_seconds)]
