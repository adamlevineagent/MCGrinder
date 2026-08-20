# Assets (not in git)

Pack `project.json` references these relative paths. The real binaries live on
Behem — see `OPERATOR.md` and `BEHEM_PATHS.json`.

```
assets/characters/singer_guitarist.png   ← 01-singer-guitarist.png
assets/characters/drummer.png            ← 02-drummer.png
assets/characters/bassist.png            ← 03-bassist.png
assets/characters/cat_violins.png        ← 06-cat-violins.png (gowned pair; not the retired unclothed standing-cats identity)
assets/locations/green_room.png          ← 04-green-room.png (EMPTY)
assets/locations/service_hall.png        ← 05-service-hall.png (EMPTY)
assets/locations/unplugged_stage.png     ← 07-unplugged-stage.png (EMPTY)
assets/locations/apartment_fire.png      ← 08-apartment-fire.png (EMPTY)
```

Inject stills (standing full-body / claws CU) also live only on Behem, same
junction, names `inject-01` … `inject-09`. See `BEHEM_PATHS.json` and
`edl.json`. Do **not** check those pngs into git — there is no LFS pattern
here. All nine injects are on Behem; `inject-07` is the black-lab take (do not
use the earlier yellow-lab generate). Faces accepted 2026-08-20.

Polygon cutout composites were unusable (forest fringe). The injects on disk
are in-room generates. `inject-02` drifted vs the locked 01 CU on the
camera-lock hone — that is a still problem, not a window problem.

Do not generate a "character in this room" still as a *new identity*. The
injects are layout plates; the locked CUs stay `<Picture N>` refs.
Do not use album art as identity.
