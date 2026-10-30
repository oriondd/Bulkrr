"""Pure presentation helpers for the import review workflow."""

from collections import Counter


STATUS_LABELS = {
    "working": "Processing",
    "ready": "Ready to import",
    "review": "Needs review",
    "duplicate": "Already in library",
    "skipped": "Skipped",
    "error": "Not found",
    "failed": "Failed",
    "done": "Added",
}


def review_counts(items):
    counts = Counter(item.get("status", "unknown") for item in items)
    return {
        "total": len(items),
        "ready": counts["ready"],
        "review": counts["review"],
        "duplicate": counts["duplicate"],
        "done": counts["done"],
        "failed": counts["failed"] + counts["error"],
        "skipped": counts["skipped"],
        "working": counts["working"],
    }


def review_summary(items):
    c = review_counts(items)
    if not c["total"]:
        return "No titles analyzed yet. Add titles or drop a TXT/CSV file to begin."
    return (
        f'{c["total"]} titles  |  {c["ready"]} ready  |  '
        f'{c["review"]} need review  |  {c["duplicate"]} duplicates  |  '
        f'{c["done"]} added  |  {c["failed"]} issues  |  {c["skipped"]} skipped'
    )
