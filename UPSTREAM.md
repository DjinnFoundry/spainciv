# Upstream notes

Bugs found in Karpathy's original usaciv (tag `upstream-2026-11-26`) while porting it to Spain. Each one is fixed on
spainciv's `main` branch; this file keeps them together so they can be sent upstream.

## Share-image file names mangle accented letters

`web/js/main.js` (`slug`, inside the share-image file name) normalises to NFD and then replaces every character
outside `[a-z0-9]` with `-`, so the combining accent left by NFD becomes a hyphen: "Cañon City" → `can-on-city`,
"España" → `espan-a`. Fix: drop the combining marks (`/[̀-ͯ]/g`) after `normalize("NFD")`.

## A districts test mutates the module's catalog

`tests/test_districts.py` (`CheckTest.doc`) puts `D.CATALOG` itself into the test document, and the "catalog" case of
`test_violations` calls `d["catalog"].pop()`: it removes the Aqueduct from `pipeline.build.districts.CATALOG` for every
test that runs afterwards in the same process. It only passes because no later test looks at the Aqueduct. Fix: copy
it (`[dict(c) for c in D.CATALOG]`).
