# Bulkrr declarative extensions

Bulkrr 2.0 supports **data-only** extensions, not executable plugins. An extension
can suggest titles for the existing manual-review workflow. It cannot run Python,
install packages, read API keys, or bypass the import confirmation screen.

Create `%APPDATA%\\Bulkrr\\extensions\\my-list.json` on Windows, or
`~/Bulkrr/extensions/my-list.json` when APPDATA is not defined.

Example:

```json
{
  "schema": 1,
  "name": "Favorite Sci-Fi",
  "description": "A short collection of movies and shows",
  "titles": [
    "movie: Arrival (2016)",
    "tv: The Expanse"
  ]
}
```

Select **Load title-list extension** in Bulkrr. Choose a manifest, review the
resulting titles, and analyze against your connected servers before importing.

Limits: JSON only, 200 KB per file, 500 titles per manifest, 100 manifests
scanned, and no unknown fields. Invalid manifests are ignored. Extension
manifests are untrusted input; do not include passwords, keys or tokens.

## Security and compatibility

- Extensions do not run code, access the network, or have filesystem privileges.
- Import operations remain subject to normal review and confirmation.
- The manifest schema is versioned; schema 1 is supported in Bulkrr 2.0.
- Import titles use the same text format as the manual title input.
