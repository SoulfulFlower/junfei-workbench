# Conservative variant-family evidence

This increment adds a local read-only assessment module and a fixed DOM observer. It does not navigate, click, save discovery products, submit a listing, evaluate qualification, or change a product or seller node. Browser capture, account binding and HTTP integration are owned by the existing discovery bridge; an assessment is never execution permission.

## Evidence and identity

`normalize_capture(raw, marketplace=..., asin=..., started_at=...)` validates fixed observer output against the server's target. It retains the canonical same-market source URL, actual observation time, selected ASIN, source selector, option labels, actual option ASINs, and the observed source type. Arbitrary query fields are removed so tracking or credentials are not retained. A twister reference suffix is not treated as a parent ID.

The observer supports two bounded layouts:

- Legacy `#twister` → `variation_*` → visible `li[data-asin] a[href]`. Actual href and data-ASIN must agree, and the selected swatch must match the current page ASIN. `source=visible_twister_anchor`; href is the sanitized actual anchor URL.
- Observed `#softlinesTwister_feature_div` inline color/size rows → visible `li[data-asin] input[role="radio"]`. Radio `aria-checked` and its visible button's `a-button-selected` class must agree. Each visible dimension needs exactly one selected option matching the page ASIN. `source=visible_inline_twister_radio`; href is null, because there is no observed anchor. Selected marker is `aria-checked+a-button-selected`.

Hidden fallback controls are excluded. For inline labels, a rendered image alt or label span associated with the visible radio is used. An `aria-hidden` label span can still be visually rendered; it is read only inside the radio's own visible button, with CSS visibility checks. Heading ARIA, `data-initiallyselected`, cachecolor, titles, brands, images, shared sellers and detail-bullet ASINs are never accepted as current selection or formal parent proof. Conflicting selected identities, current attributes, unsupported layouts, ambiguous controls, login/captcha and access errors fail closed. No live-page JavaScript payload or caller script is executed by the assessor.

Top-level raw schema remains version 1. Normalized evidence uses `kind=visible_variant_controls`, `collectorVersion=2` and a SHA-256 observation ID. Controls have exactly: `containerId`, `selector`, `source`, `asin`, `dataAsin`, `href`, `label`, `selectedMarker`.

## Assessment boundaries

`assess_graph(graph, evidence=None)` is pure and does not access files, databases or the network. It returns annotations and groups without altering the graph. Imported evidence always remains unauthenticated and cannot suppress work. A strictly bounded `legacy_detail_asin` hint can describe a shared displayed detail ASIN, but the resulting pair stays pending verification.

`assess_recorded(graph, receipts)` is an internal server-only path. The adapter must load receipts from the authenticated account's database, check database status against receipt status and current route, and never accept these receipts from an HTTP body or imported file. The function independently validates cycle, revision, graph parent membership, timestamps, observation hash, receipt IDs and fingerprints, and compares the collector SHA against the fixed local bundled source file. Receipts from obsolete collectors remain explicit nonauthorizing diagnostics and do not poison future current-collector captures. Corrupt current receipts still fail closed. All current receipts are checked, then the latest snapshot per source is selected, with at most 200 source snapshots and 2 MiB of serialized evidence in the working assessment. Individually valid captures excluded by either working limit remain explicit nonauthorizing diagnostics; omitted nodes remain independent pending branches. The byte budget uses the exact evidence-list JSON size, so a large valid history does not fail the whole plan. Recent contradictory membership sets are still detected across the full history rather than lost through truncation. That is its only file read. It does not establish account ownership by itself and cannot turn JSON into authenticated provenance.

For possible title-phrase suppression, both selected product pages must directly show the other ASIN in supported visible variant controls. Latest snapshots are used; old outgoing links cannot be combined with a later return link. Different membership sets for the same source are treated as ambiguous and prevent suppression. Captures must be no more than 24 hours old and no more than 15 minutes apart. These are technical freshness limits, not product-selection thresholds.

Groups require every pair in a connected component to have direct reciprocal support. A↔B and B↔C do not prove A↔C. Incomplete components stay pending and cannot suppress any title action. Imported, stale, one-sided, cross-market or conflicting evidence does not suppress work.

`title_dedup_key` is only an internal hint for freshly server-assessed title-phrase planning. It is never for Seller capture, supplier work, qualification, product import, or listing publication. All original nodes and seller evidence remain unchanged. Parent ASIN is always unknown in this version. Visible variant-control membership is not proof of an identical SKU, an independent EXACT same-product match, a shared purchasing seller, or transferable rank evidence.

## Verification

Run in `listing-workbench`:

- `python -B -X utf8 -m unittest test_discovery_family`
- `node --test test_discovery_family_collector.cjs`

Tests use synthetic fixtures and temporary SQLite for one real-ledger interface regression. They do not touch production databases or configuration. Additional local artifact regressions load saved real observations if the files are present; they skip when those artifacts are not included in another installation.

The old `outputs/next-search-20261106/source-chain.json` pair B0HJVJJP8T / B0HJVZ4GTH remains pending: shared detail ASIN B0HJVZHHTL alone does not establish its family. The new real saved inline-control HTML in `outputs/variant-evidence-20261106/12-candidate-fresh-load.json` and `15-bridge-fresh-controls.json` passes the offline observer fixture. The stale transition states in `08-green-medium-after-timeout.json` and `10-blue-medium-transition.json` are rejected. Parsing stored HTML is not a claim of a successful current-page browser capture or a complete automatic loop. The separately recorded navigation path can support a manually observed selection-family relation without satisfying this stricter direct-clique automatic-dedup criterion.

The portable bundle must include both `discovery_family.py` and `discovery-family-collector.js`. A missing collector fails closed. A changed collector makes old receipts diagnostic-only; it cannot silently reuse them as current proof, and new valid captures can recover without deleting history.
