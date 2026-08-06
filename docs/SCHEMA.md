# MCGrinder Project Pack — Schema v1

The Project Pack is the interchange format for a full sequence (music video, short,
whatever). It is a ZIP containing:

```
project.json      ← the entire project (schema below)
assets/           ← every image the project references (panels, character sheets, locations)
SCHEMA.md         ← this file
ENHANCE_SPEC.md   ← the prompt-enhancement spec (for external AIs)
```

An external AI (ChatGPT/Claude) can open the pack, SEE the assets (multimodal), edit
`project.json` (visuals, dialogue, prompts, settings), and return it. Pasting the
returned `project.json` back into the app pre-populates the whole editor.

## project.json

```json
{
  "project_schema": 1,
  "project": "BUSY V7",
  "song": "04 - BUSY V7.mp3",
  "song_duration_s": 264.1,
  "bpm": 172,
  "style_block": "Hand-drawn ink and watercolor animation style ...",
  "settings": {
    "width": 1344, "height": 768,
    "steps": 20, "scheduler": "beta", "tau": 1.3, "sol_attn": true,
    "audio_default": "raw"
  },
  "characters": [
    {"id": "CHAR1", "name": "singer clam", "sheet": "assets/characters/02_singer_clam.png",
     "description": "self-serious crooning clam, ink/watercolor, stage-lit"},
    {"id": "CHAR2", "name": "the senator", "sheet": "assets/characters/04_senator_and_old_guard.png",
     "description": "grand old-world senator predator"}
  ],
  "shots": [
    {"id": 1, "name": "P1 lonely procession", "start_s": 0.3, "duration_s": 13.75,
     "prompt": "The lonely procession ...",
     "prompt_override": null,
     "characters": ["CHAR1"],
     "refs": ["assets/panels/01_lonely_procession.png"],
     "audio_mode": "raw",
     "seam": "prev",
     "first_frame_img": null}
  ]
}
```

## Rules the app enforces on import

- `start_s` drives everything: each shot's duration is implied by the NEXT shot's
  start (last shot = song end). Set starts only; durations are computed.
- `seam`: "prev" = open on the previous shot's final frame (pixel-pinned);
  "none" + `first_frame_img` = open on that image; "none" alone = text-to-video.
- `audio_mode`: "raw" = full song window as audio ref (music + possible lip-sync);
  "pulse" = rhythm-only pulse (no vocals, no lip-sync).
- `characters`: `CHAR1` inside a prompt means the app attaches that character's
  sheet as a reference (and uses `description` when refs are off).
- `refs` are relative to the pack root (`assets/...`). Import copies them into the
  app's input dir and rewrites paths.
- Resolution: native canvas is a 768px short edge (1344x768 at 16:9). Don't exceed.
- Frames snap to H3's 17k+5 grid at 24fps; durations you set are exact cut times.
- Prompt format: see ENHANCE_SPEC.md — the app's enhancer follows the same spec.
