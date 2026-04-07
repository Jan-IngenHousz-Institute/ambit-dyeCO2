"""
protocol.py — Serial command strings and JSON response parsers for ambit dyeCO2.

Serial config: 115200 baud, 8N1, no parity.
All commands are plain text terminated with '\n'.
All responses are JSON lines (one JSON object per line).
"""

import json

# ---------------------------------------------------------------------------
# Command strings
# ---------------------------------------------------------------------------

CMD_HELLO = "hello"
CMD_STATUS = "status"
CMD_SPEC = "spec"
CMD_SPEC_FLASH = "spec_flash"
CMD_ENV = "env"


def cmd_set_gain(value: int) -> str:
    return f"spec_set_gain,{value}"


def cmd_set_atime(value: int) -> str:
    return f"spec_set_atime,{value}"


def cmd_set_astep(value: int) -> str:
    return f"spec_set_astep,{value}"


def cmd_set_led(value: int) -> str:
    return f"set_led,{value}"


# ---------------------------------------------------------------------------
# Gain label tables
# ---------------------------------------------------------------------------

AS7341_GAIN_LABELS = {
    0: "0.5x", 1: "1x", 2: "2x", 3: "4x", 4: "8x",
    5: "16x", 6: "32x", 7: "64x", 8: "128x", 9: "256x", 10: "512x",
}

AS7343_GAIN_LABELS = {
    0: "0.5x", 1: "1x", 2: "2x", 3: "4x", 4: "8x",
    5: "16x", 6: "32x", 7: "64x", 8: "128x", 9: "256x",
    10: "512x", 11: "1024x", 12: "2048x",
}


def gain_labels(model: str) -> dict:
    if model == "AS7343":
        return AS7343_GAIN_LABELS
    return AS7341_GAIN_LABELS


def gain_max(model: str) -> int:
    return 12 if model == "AS7343" else 10


# ---------------------------------------------------------------------------
# Channel ordering / display labels
# ---------------------------------------------------------------------------

AS7341_CHANNELS = [
    "f1_415", "f2_445", "f3_480", "f4_515", "f5_555",
    "f6_590", "f7_630", "f8_680", "clear", "nir",
]

AS7343_CHANNELS = [
    "f1_405", "f2_425", "fz_450", "f3_475", "f4_515", "f5_550",
    "fy_555", "fxl_600", "f6_640", "f7_690", "f8_745", "nir_855",
    "clear",
]

# Human-readable display names for legend
_CHANNEL_DISPLAY = {
    "f1_415": "F1 415nm", "f2_445": "F2 445nm", "f3_480": "F3 480nm",
    "f4_515": "F4 515nm", "f5_555": "F5 555nm", "f6_590": "F6 590nm",
    "f7_630": "F7 630nm", "f8_680": "F8 680nm",
    "clear": "Clear", "nir": "NIR",
    "f1_405": "F1 405nm", "f2_425": "F2 425nm", "fz_450": "FZ 450nm",
    "f3_475": "F3 475nm", "f4_515": "F4 515nm", "f5_550": "F5 550nm",
    "fy_555": "FY 555nm", "fxl_600": "FXL 600nm", "f6_640": "F6 640nm",
    "f7_690": "F7 690nm", "f8_745": "F8 745nm", "nir_855": "NIR 855nm",
}


def channel_display_name(ch: str) -> str:
    return _CHANNEL_DISPLAY.get(ch, ch)


def channels_for_model(model: str) -> list:
    if model == "AS7343":
        return AS7343_CHANNELS
    return AS7341_CHANNELS


# ---------------------------------------------------------------------------
# Default settings per model
# ---------------------------------------------------------------------------

MODEL_DEFAULTS = {
    "AS7341": {"atime": 100, "astep": 999, "gain": 5, "led": 10},
    "AS7343": {"atime": 29,  "astep": 599, "gain": 1, "led": 10},
}


def defaults_for_model(model: str) -> dict:
    return MODEL_DEFAULTS.get(model, MODEL_DEFAULTS["AS7341"])


# ---------------------------------------------------------------------------
# JSON parsers
# ---------------------------------------------------------------------------

def _try_parse(line: str):
    """Return parsed JSON object or None."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def parse_status(line: str) -> dict | None:
    """
    Parse a 'status' response containing spectrometer_status and/or bme_status.
    Returns a dict with keys 'spectrometer' and/or 'bme', or None if not a
    status line.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    result = {}
    if "spectrometer_status" in obj:
        result["spectrometer"] = obj["spectrometer_status"]
    if "bme_status" in obj:
        result["bme"] = obj["bme_status"]
    return result if result else None


def parse_spec(line: str) -> dict | None:
    """
    Parse an ambient 'spec' response.
    Returns {"model": str, "channels": dict} or None.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    spec = obj.get("spectrometer")
    if not isinstance(spec, dict):
        return None
    if "error" in spec:
        return None
    channels = spec.get("channels")
    model = spec.get("model", "")
    if isinstance(channels, dict) and model:
        return {"model": model, "channels": channels}
    return None


def parse_spec_flash(line: str) -> dict | None:
    """
    Parse a 'spec_flash' response — we use the diff reading.
    Returns {"model": str, "channels": dict} or None.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    # spec_flash produces three top-level keys; we want the diff
    diff = obj.get("spectrometer_diff")
    if isinstance(diff, dict) and "channels" in diff and "model" in diff:
        if "error" not in diff:
            return {"model": diff["model"], "channels": diff["channels"]}
    return None


def parse_bme(line: str) -> dict | None:
    """
    Parse an 'env' response.
    Returns {"T": float, "P": float, "RH": float, "Gas": int} or None.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    bme = obj.get("bme_read")
    if not isinstance(bme, dict):
        return None
    if all(k in bme for k in ("T", "P", "RH", "Gas")):
        return {
            "T":   float(bme["T"]),
            "P":   float(bme["P"]),
            "RH":  float(bme["RH"]),
            "Gas": int(bme["Gas"]),
        }
    return None


def parse_spec_config(line: str) -> dict | None:
    """
    Parse a spectrometer_config response (after set_gain / set_atime / set_astep).
    Returns {"atime": int, "astep": int, "gain": int} or None.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    cfg = obj.get("spectrometer_config")
    if isinstance(cfg, dict) and "error" not in cfg:
        return cfg
    return None


def parse_error(line: str) -> str | None:
    """
    Return a human-readable error string if the line contains a firmware error,
    otherwise None.
    """
    obj = _try_parse(line)
    if obj is None:
        return None
    # Check common error locations
    for key in ("spectrometer", "spectrometer_config", "bme_status"):
        sub = obj.get(key)
        if isinstance(sub, dict) and "error" in sub:
            return f"{key}: {sub['error']}"
    return None


def classify_line(line: str) -> tuple[str, object]:
    """
    Classify an incoming serial line and return (kind, parsed) where kind is
    one of: 'hello', 'status', 'spec', 'spec_flash', 'bme', 'spec_config',
    'error', 'unknown'.
    """
    stripped = line.strip()
    if "Hello CO2 meter ready" in stripped:
        return ("hello", stripped)

    obj = _try_parse(stripped)
    if obj is None:
        return ("unknown", stripped)

    # Status
    if "spectrometer_status" in obj or "bme_status" in obj:
        return ("status", parse_status(stripped))

    # Spec flash (check before ambient because both have 'spectrometer' key)
    if "spectrometer_diff" in obj:
        parsed = parse_spec_flash(stripped)
        if parsed:
            return ("spec_flash", parsed)

    # Ambient spec
    if "spectrometer" in obj:
        parsed = parse_spec(stripped)
        if parsed:
            return ("spec", parsed)
        err = parse_error(stripped)
        if err:
            return ("error", err)

    # BME
    if "bme_read" in obj:
        parsed = parse_bme(stripped)
        if parsed:
            return ("bme", parsed)

    # Config ack
    if "spectrometer_config" in obj:
        parsed = parse_spec_config(stripped)
        if parsed:
            return ("spec_config", parsed)
        err = parse_error(stripped)
        if err:
            return ("error", err)

    return ("unknown", stripped)
