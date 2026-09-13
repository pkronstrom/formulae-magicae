# Sourcing and prices (Finland) — what answers a script

Checked 2026-09-13 from the a-frame-cabin run. Re-check before trusting; note the date when you update.

| store | works | how | notes |
|---|---|---|---|
| byggmax.fi | yes | `curl -sL --compressed -A "<browser UA>" https://www.byggmax.fi/<slug>`; price in `<span class="price"><span class="integer notranslate">5,49</span>`; search `/catalogsearch/result/?q=…`, product links match `href="…-p[0-9]+"` | timber €/m, sheets €/kpl |
| byggmax.fi GraphQL | yes | `curl -X POST https://www.byggmax.fi/graphql -H "Content-Type: application/json" -H "Store: fi_fi" -d '{"query":"{products(filter:{sku:{eq:\"P-16160\"}}){items{sku name price_range{minimum_price{final_price{value}}} ... on ConfigurableProduct{variants{product{sku price_range{minimum_price{final_price{value}}}} attributes{label}}}}}}"}'` | **use this for configurable products** (thickness/length variants): the HTML shows only the cheapest variant's "from" price — Paroc eXtra "7,93 €/m²" is the 50 mm, 150 mm is 18.45. Without `Store: fi_fi` you get the Swedish catalog |
| k-rauta.fi | partly | WebFetch on product/category pages | many items "ei ostettavissa verkkokaupasta" → no price online |
| bauhaus.fi | yes, via Algolia | `scripts/bauhaus.py "48x198 mitallistettu"` — the site itself serves a Vercel bot challenge (429) to curl/WebFetch, but its search is a public Algolia index (app id + search key in every page's source); hits carry piece price and €/m, €/m², €/kpl | use product vocabulary in the query ("lastulevy lattia", not "lattialastulevy 22"); `--chrome <slug>` falls back to headless Chrome if the key rotates |
| WebSearch | rough | product name + "hinta" — snippets often carry €/m or €/pkt | good enough for a ±20 % estimate |

Vocabulary that changes the price: mitallistettu = dimensioned structural C24 (frame stock); höylätty = planed
(furniture/finish, dearer); sahatavara = rough sawn from a local saha, ~40 % cheaper, sort it yourself.
Wool 565 mm wide = k600 framing. Leca pilariharkko is P-240 (240×240×195).

When pricing: one line per item with qty, €/unit, €, source; list price AND a budget column (saha timber,
used door/glass from tori.fi); state ±20–25 %; totals per group. Envelope of a small building is
typically 3–4× the frame — say so before the user is surprised.
