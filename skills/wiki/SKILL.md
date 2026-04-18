---
name: wiki
description: Persistent wiki store for long-lived project knowledge, with query, graph, and CLI validation surfaces.
triggers: ["wiki", "wiki this", "wiki add", "wiki query", "wiki graph", "wiki validate"]
---

# Wiki

Persistent project knowledge base stored in the Omni SQLite state store.

Use the MCP tools for writes and structured reads. Use the `omni wiki ...` CLI for human-readable inspection and validation.

## Operations

### Ingest / write

Use `wiki_ingest` when you want SHA-256 de-duplication by body. Re-ingesting the same body is a no-op (`deduped: true`).

```
wiki_ingest({ title: "Auth Architecture", body: "...", tags: ["auth", "architecture"] })
```

Use `wiki_write` for direct upserts when de-duplication is not the point.

```
wiki_write({ slug: "auth-architecture", title: "Auth Architecture", body: "...", tags: ["auth"] })
```

The canonical content field is `body`.

### Query
Search across wiki pages by title, body, and tags.

```
wiki_query({ query: "authentication" })
```

### List / read

```
wiki_list()
wiki_read({ slug: "auth-architecture" })
```

### Graph

The MCP server exposes `wiki_graph`, which returns `{nodes, edges, dangling}` derived from wiki-link and local markdown-link references.

```
wiki_graph({})
```

### CLI inspection

Use the main CLI for read-only navigation with human-readable output by default and `--json` when you need machine-readable output.

```
omni wiki list
omni wiki show auth-architecture
omni wiki search authentication
omni wiki graph
omni wiki validate
```

`omni wiki validate` exits non-zero when dangling links are present, so it can be used as a lightweight integrity check.

## Cross-references

Use `[[slug]]`, `[[Title|slug]]`, or local markdown links like `[docs](./other-page.md)` to create wiki graph edges.

## Storage
- Backing store: `$OMNI_HOME/omni.db`
- Table: `wiki`
- Graph source: stored page bodies parsed for wiki/local markdown links

## Hard Constraints
- NO vector embeddings — query is keyword/tag matching over stored rows
- Validation today is bounded to graph integrity (dangling-link detection), not a full semantic linter
