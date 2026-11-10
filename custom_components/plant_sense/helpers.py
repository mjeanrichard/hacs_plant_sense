def build_unique_id(serial: str) -> str:
    """Build unique id for PlantSense device."""
    return f"PlantSense-{serial}"


def parse_firmware_version(version: str) -> tuple[int, ...] | None:
    """
    Parse a firmware version like ``1.2`` or ``v1.2-dev`` into a tuple of ints.

    Mirrors the comparison the device performs: numeric components only, any
    ``-suffix`` (e.g. ``-dev``) is ignored. Returns None if it cannot be parsed.
    """
    core = version.strip().removeprefix("v").split("-", 1)[0]
    try:
        parts = tuple(int(part) for part in core.split("."))
    except ValueError:
        return None
    return parts or None


def is_newer_firmware(candidate: str, installed: str) -> bool:
    """Return True if ``candidate`` is strictly newer than ``installed``."""
    candidate_parts = parse_firmware_version(candidate)
    installed_parts = parse_firmware_version(installed)
    if candidate_parts is None or installed_parts is None:
        return False
    length = max(len(candidate_parts), len(installed_parts))
    candidate_parts += (0,) * (length - len(candidate_parts))
    installed_parts += (0,) * (length - len(installed_parts))
    return candidate_parts > installed_parts
