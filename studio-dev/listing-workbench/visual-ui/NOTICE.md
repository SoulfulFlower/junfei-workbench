# Third-party source notice

VisualStep.tsx, JobProgress.tsx, toast.tsx, types.ts, listing.css and visual-original.css are adapted/copied from Hector-xue/IvyeaOps, commit 51f5141b475e64b67638f396451d887531caa761, https://github.com/Hector-xue/IvyeaOps, licensed AGPL-3.0-only. Original copyright and license are retained. Local changes adapt models, products, accounts, task APIs, styles, exports, and evidence-based quality reporting. Single-image PSD export reuses the upstream writer and the account-local rendering records.

The combined deployed workbench is made available under AGPL-3.0-only; see root LICENSE-AGPL-3.0.txt. Authenticated users can download corresponding source through /api/studio/source. The source archive excludes credentials, user data, generated images, dependencies, and compiled bundles. Build: cd visual-ui; npm ci; npm run build. Start: Python 3.12 server.py. No upstream executable, private credentials or user database is included.

React, React DOM, lucide-react and JSZip retain their respective upstream licenses in node_modules. The package-lock.json records exact dependencies.
