#!/bin/sh
# Download the free Piper voices into voices/ (~60-120 MB each, from huggingface.co/rhasspy/piper-voices).
cd "$(dirname "$0")"
for v in ${@:-en_US-lessac-medium en_US-amy-medium en_US-hfc_female-medium en_GB-jenny_dioco-medium en_GB-cori-high en_US-ryan-high}; do
  .venv/bin/python -m piper.download_voices --download-dir voices "$v"
done
