# Song catalog

This directory is the repo home for songs and the project packs that drive them.

Each entry is a folder you can copy for the next song. Do not rediscover cast,
locations, cut, or audio-mode rules from chat history.

```
catalog/
  index.json              ← song list
  01-dont-freak/          ← first entry (SCHEMA pack + pipeline state)
  NN-next-song/           ← copy 01-dont-freak, then replace canon
```

A pack follows `docs/SCHEMA.md` (`project.json` + optional lyrics/overlays).
`pipeline/from_pack.py` turns `project.json` into the `state.json` that
`snap_beats.py`, `hone.py`, `run_chunk.py`, `redo.py`, and `stitch.py` consume.

Identity stills and the master wav live on the operator box, not in git.
See the song's `OPERATOR.md`.
