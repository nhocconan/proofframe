# Notices

- Demo footage: *Tears of Steel* © Blender Foundation | mango.blender.org, licensed CC-BY 3.0.
  Excerpts (source 0:15–1:15, 0:15–2:15, 0:15–5:15) and derived caption composites are kept outside Git in `../media/`.
  The Vietnamese lower-third captions overlaid on it are ProofFrame demo material, not part of the film.
- Fonts: DejaVu Sans (Debian `fonts-dejavu-core`) used by ffmpeg drawtext.
- New code in this build (2026-10-27): `src/proofframe/**`, `web/**`, `e2e/`, `docker/`, `docker-compose.yml`, tests other than
  `tests/test_policy.py`, `tests/test_repair_and_timeline.py`, `tests/factories.py` (seed). No third-party source code was copied.
- Runtime dependencies: see `requirements.lock` (Python) and `web/package-lock.json` (Node).
