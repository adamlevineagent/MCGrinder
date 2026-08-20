# Don't Freak — locked canon (Adam ears, 2026-08-20)

Spine: a calm felt-animal band in classic "you should be screaming" set pieces.
They do not freak. They are having a good time. Disasters escalate. IM stays
casual. The quill / letter is the LATE tell — do not show it early.

Do not use album art as identity. Do not regenerate faces. Composite the locked
portraits into empty location stills at grind time. A new "sloth in the fire"
still drifts the face; that already burned.

## Cast (never humans; never extra members except the cats)

| id | Role | Locked still on Behem |
|---|---|---|
| CHAR_SLOTH | Singer-guitarist. Needle-felt sloth, dark dreadlocks, charcoal jacket, droopy calm face. | `01-singer-guitarist.png` |
| CHAR_GRIZZLY | Drummer. Green baseball cap, green hoodie, purple pants, felt grizzly. | `02-drummer.png` (confirm filename; sits between 01 and 03) |
| CHAR_LAB | Bassist. Black lab, charcoal jacket, cream bass, reddish-brown paw "gloves". | `03-bassist.png` |
| CHAR_CATS | Twin black-cat violinists, **always a pair**. From **1:35 only**. | `06-cat-violins.png` |

## Empty locations (no character in the still)

| id | Location | Behem still |
|---|---|---|
| LOC_GREEN_ROOM | Backstage green room | `04-green-room.png` |
| LOC_SERVICE_HALL | Service hall | `05-service-hall.png` |
| LOC_CATS | (identity pair, not a room) | `06-cat-violins.png` |
| LOC_STAGE | 1990s MTV Unplugged stage | `07-unplugged-stage.png` |
| LOC_APARTMENT_FIRE | Apartment hallway on fire | `08-apartment-fire.png` |

Generated disaster worlds (quicksand, elevator, ice, airlock, flooded subway,
volcano, burning roof, plane down, tornado, collapse) have no locked plate.
Keep puppet identity from the character stills. Do not invent readable text.

Green-room hone invented extra planet-toys on the flight case. Prompts must say
the room is empty of extra props; the case lid stays clear.

## Lyric rule

Whenever there are sung words on screen: **only the sloth**, side or tight,
pressed into a mic, in whatever environment that line lives in. Never a
band-wide lyric tableau. Raw vocal (not BeatPulse) on those CUs.

Instrumentals and guitar-tight sections: mux and condition on the **real wav**,
not a click / pulse track. Every shot in this pack sets `audio_mode: "raw"` so
`config.audio_mode_default: pulse` cannot override it.

Do not bake lyrics or IM copy into H3 prompts as something the model should
write. Overlay after concat.

## Cut

- **0:00** fade up from black, tight on sloth claws, 1990s MTV Unplugged VHS/CRT, real guitar, no lyrics.
- **0:11–0:12** jerky zoom-out; sloth AND lab jump-land as they play; dramatic lights; grizzly on kit. Hold Unplugged until the intro instrumental ends.
- **First lyrics** (after intro, before 0:46 — force-align from the wav; exact in was not stamped): lyric CU, then start disaster cutaways. They look unaware and like they are having fun.
- **0:46** first "So don't freak" — lyric CU, fire apartment.
- **1:04** chunka jam / "shit might look bad, but we'll dance our way out of this one" — medium disasters (quicksand, elevator, ice).
- **1:22–1:25** singer sustained ahhh; **1:24** long jump-around jam (burning roof OK), real wav.
- **1:35** twin black cats with violins, always together.
- **1:46** breakdown: violins + long slow bass/guitar; drums metronomic. Sparse world (airlock / ice).
- **1:55–2:00** "don't freak, don't freak, yeah we'll dance our way out of this one".
- **2:00–2:11** sustained "Thiiiiisssssss one"; "one" lands 2:10–2:11 as full band+violins return; jam to 2:26.
- **2:26** crescendo; everything drops **2:31**; **~2:33** "the future is cooooool / but the present sort of sucks" ×2 (flooded subway vs volcano ok); drums pound on the repeat then drop again.
- **Peak:** "Just don't freak! And we'll dance ouuuurr......." — craziest coherent MV worlds (plane down, tornado, collapse) without breaking puppet identity or adding readable fake text.
- **3:07** wind-down, slow intricate guitar, **quill letter** (page never readable) — this is the silliness tell.
- **3:10–3:20** "Have you forgiven yourself reeeeeeeeeecently....." (`recently` stretches here).
- **3:20–end** decelerating guitar, long last note, empty green room / empty stage, composure, hold.

## Overlays (after concat, never in the H3 prompt)

- Canon English SRT timed from the wav (not an even grid). Source: `lyrics.json` — a list of `{text, start, end}`, never a raw string.
- IM overlay on the laptop in the fire side-shot only: `r u ok?` / `its cool man`.

## Canon lyrics (quote, never invent)

Don't Freak

[Verse] Did you forgive yourself recently? / Are you taking it easy? / You know it doesn't have to be that way / I know that it's not easy / You know that it's not easy / But you know it doesn't have to be that way

[Chorus] So don't freak / don't freak / We'll just dance our way out of this one / don't freak / don't freak / We'll just dance our way right out of this one / Don't freak / don't you freak / We'll just dance our way out of this one / Yeah, Don't freak / We'll dance our way out of this one / Don't freak / Shit might look bad / But we'll dance our way out of this one / (repeat) / Don't freak / Don't freak / yeah we'll dance our way out of this one / (repeat)

[Verse 2] The future is cool / But the present sort of sucks / (repeat) / So just don't freak / An' we'll dance our.... / Don't freak / We'll dance our way out of this one / (repeat) / Have you forgiven yourself recently?

`(repeat)` means the preceding refrain is sung again — same words, later timestamps.
