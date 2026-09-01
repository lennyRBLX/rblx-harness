"""Final blocking disposition for harness rule identifiers.

Sections 17-23 of harness.plan.md are the authority. Callers may warn on an
advisory rule, but only ``hard`` findings can deny the current operation.
"""

HARD_RULE_IDS = frozenset(
    {
        "BC1",
        "BC7",
        "DATA1",
        "DATA5",
        "DATA8",
        "DATA17",
        "DATA21",
        "DATA23",
        "DATA29",
        "DATA30",
        "DATA31",
        "DATA32",
        "DATA33",
        "DATA35",
        "DATA36",
        "DATA37",
        "DEBUG2",
        "DEBUG11",
        "DES2",
        "GATE1",
        "GATE2",
        "GATE3",
        "GATE4",
        "GATE5",
        "GATE6",
        "GATE7",
        "OPT8",
        "OPT12",
        "OPT16",
        "OPT17",
        "OUT1",
        "REV4",
        "REV10",
        "TYPE1",
        "TYPE7",
        "TYPE8",
        "TYPE9",
        "WRIT8",
        "WRIT18",
        "WRIT23",
        "WRIT25",
        "WRIT29",
        "WRIT30",
        "WRIT31",
        "WRIT33",
    }
)

AUTO_FIX_RULE_IDS = frozenset(
    {
        "BC3",
        "TYPE3",
        "WRIT12",
        "WRIT14",
        "WRIT15",
        "WRIT22",
    }
)

CUT_RULE_IDS = frozenset({"TYPE10"})


def disposition(rule_id):
    """Return ``hard``, ``auto-fix``, ``advisory``, or ``cut``."""
    bare = str(rule_id or "").rstrip("!")
    if bare in CUT_RULE_IDS:
        return "cut"
    if bare in AUTO_FIX_RULE_IDS:
        return "auto-fix"
    if bare in HARD_RULE_IDS:
        return "hard"
    return "advisory"


def split_findings(findings, id_index=3):
    """Partition finding tuples without changing their public record shape."""
    grouped = {"hard": [], "auto-fix": [], "advisory": [], "cut": []}
    for finding in findings:
        grouped[disposition(finding[id_index])].append(finding)
    return grouped
