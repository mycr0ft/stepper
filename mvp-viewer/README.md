# mvp-viewer — browse OSLC-linked STEP, render 3D in the browser

One static HTML page. No build step, no backend beyond pyoslc itself.

```
python3 -m http.server 8734            # serve THIS directory
cd ~/proj/pyoslc
STEP_FIXTURES=/path/to/model.stp .venv/bin/python -m flask \
    --app app.wsgi:app run --port 5055
# open http://localhost:8734 — left pane lists the OSLC resources,
# click through properties/links; click a StepFile resource and the
# right pane tessellates + renders the model IN THE BROWSER.
```

## What it demonstrates

1. **The Vee stack serves its data for humans, not just APIs** — the
   left pane is a mini OSLC-browser: fetch a resource URL (pyoslc's
   `/oslc/step/product`, `/file`, `/vee`, …), render its JSON-LD
   properties, follow resource-valued links by clicking.
2. **Local-only tessellation** — the 3D pane downloads the raw
   Part 21 bytes from pyoslc's `GET /oslc/step/file/<id>/model.stp`
   and tessellates with `occt-import-js` (a WebAssembly build of
   OpenCascade, MIT, from kovacsv's Online3DViewer). Geometry is
   processed **in your browser** — the file's contents never go
   anywhere besides the one fetch from your own server.
3. **CORS-friendly provider** — pyoslc `create_app` now stamps
   `Access-Control-Allow-Origin: *` (lock down with the
   `CORS_ORIGINS` config key) and answers OPTIONS on `/oslc/*`, so a
   static page can be its consumer. This is the first browser-native
   client of the STEP domain.

## Verified

Headless-chromium smoke (CDP): product cards render from the seeded
NIST fixtures; a StepFile card drives the pane; the .stp downloads
(1.9 MB FTC file); occt-import-js tessellates; a three.js canvas
renders (screenshot `screenshot-ctc01.png` — NIST CTC-01).

## MVP scope / known limits

- JSON-LD only (flask-restx serves it on `Accept: application/json`;
  RDF/XML needs a real RDF browser or a client-side parser — next step).
- The vee/obp/baseline endpoints are plain JSON (not JSON-LD) — the
  viewer tolerates that but does not render their shapes specially.
- No hover previews (OSLC Compact), no delegated-dialog integration.
- Camera is a hand-rolled orbit (drag/wheel) — good enough for the MVP.