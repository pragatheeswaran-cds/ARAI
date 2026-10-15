# Demo deck

The slide deck built from `docs/demo-script.md`: 20 slides, one HTML file per slide under `slides/`, in the order
`deck.json` lists. Each slide is a single `<section>` on a 1920 by 1080 canvas with inline styles and, as its last
child, an `<aside>` holding the speaker notes. The typefaces named in `deck.json` are Google Fonts (Source Serif 4
for headings, IBM Plex Sans for text); without them the slides fall back to Georgia and Arial.

Every number on the slides is what the workbench shows for the demonstration world W5401 scored on experiment 4
(run `run-ed95a0e2fd3e49a69d4d`, 15 Oct 2026). If the run is re-scored or the world changes, re-read the numbers from
the screens before presenting. Slide 4 is the optional cold open on the baseline rehearsal instance (`arai
baseline-rehearsal`, demo script section 1d); skip it if that instance is not running.

The deck is presented from the hosted page (Claude Artifacts, "ARAI Demo Deck"), which also exports it as
PowerPoint or PDF. These files are the source of that page, kept here so the deck is versioned with the script.
