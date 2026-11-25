# Reproduce the oblique comparison

The paired scorer uses the Python standard library. It verifies the published baseline hashes, both original blinded manifests, the supplemental freeze, and a one-to-one ID join. It computes foreground name outcomes from the ordinary Python or browser product decision. The separate order column comes from strict Python or the browser optical order. For a timeout the scorer records a runtime error; the name and order are unknown. The legacy validation set has no frozen view annotations. [Scorer](../../../scripts/score_oblique_packages.py) · [Protocol](protocol.md)

From the repository root, run the following against the checked-in raw ledgers.

```sh
run=$(mktemp -d)
python scripts/score_oblique_packages.py --out "$run"
diff docs/experiments/oblique-packages/paired.csv "$run/paired.csv"
diff docs/experiments/oblique-packages/scores.json "$run/scores.json"
```

To rerun recognition, install the project catalogue dependencies, Tesseract English, Playwright and Chromium. Python uses pinned DINOv2 weights. Use the environment from the prior study and a checkout containing the candidate files whose hashes are recorded here. The earlier Python source is at commit `3f4fb51`; the baseline browser assets are available at `01f849bc`. The raw output includes visible browser text, Chromium version, both Python modes and image IDs. [Candidate model checksums](candidate-models.json) · [Prior runtime versions and optical dependencies](../registered-recall/environment.json) · [Prior complete baseline commands](../registered-recall/production.md)

```sh
old=docs/experiments/registered-recall
study=docs/experiments/oblique-packages
mkdir "$run/photos" "$run/replay"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
for cohort in archive public legacy-validation; do
    python scripts/evaluate_registered_production.py fetch --cohort "$cohort" --photos "$run/photos"
    PYTHONPATH=src python scripts/evaluate_registered_production.py infer --cohort "$cohort" --photos "$run/photos" --out "$run/replay/$cohort-python.jsonl"
    python scripts/evaluate_registered_browser.py "$old/$cohort-blind.csv" "$run/photos" --chromium /usr/bin/chromium --out "$run/replay/$cohort-browser.jsonl"
done
python "$study/replay_supplemental.py" fetch "$run/photos"
PYTHONPATH=src python "$study/replay_supplemental.py" infer "$run/photos" --out "$run/replay/supplemental-python.jsonl"
python scripts/evaluate_registered_browser.py "$study/supplemental-blind.csv" "$run/photos" --chromium /usr/bin/chromium --out "$run/replay/supplemental-browser.jsonl"
python scripts/score_oblique_packages.py --ledgers "$run/replay" --out "$run/replay"
```

If Chromium reports an application timeout the replay utility exits and retains all completed rows. Record that photo’s ID, source hash, Chromium version, returned status text and `"status": "timeout"` in the first-attempt JSONL. Keep any retry in a separate ledger. A timeout under contention can finish in a subsequent run. This can change reported completion counts even when the recognition source is byte-identical.

The timing script always selects the first side-visible photograph by original file ID from each of the three registered products and the first registered front. The Python benchmark warms the model on the front once, then measures ordinary RGB recognition, including the decision and any OCR. The browser benchmark uses a fresh local HTTP server, fresh Chromium process and file chooser per photograph; elapsed times include launch, upload, local assets, recognition, and browser/server shutdown. The two modes have different timed boundaries. Run each command sequentially in the corresponding checkout or with the frozen source paths selected.

```sh
PYTHONPATH=src python "$study/measure_latency.py" python "$run/photos" --out "$run/python-time.json"
python "$study/measure_latency.py" browser "$run/photos" --web web --chromium /usr/bin/chromium --out "$run/browser-time.json"
```
