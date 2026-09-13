# Signalbox control inventory (current iPhone page) — for the ChatGPT design brief

Every control that exists today, with type, range and behaviour. Nothing here is hypothetical.

## Global (always visible)
| Control | Type | Range / states | Behaviour |
|---|---|---|---|
| Status badge | indicator | green = Pi online, red = offline, blue = Mac dev server | Polls every 5 s; shows "Pi" / "Pi offline" |
| Atmosphere | segmented switch | Day / Night | Switches scene pool, ambient loop and lamp settings shown; does not itself stop playback |
| Master volume | slider | 0–100 % | Applies to everything |

## Transport and scheduler
| Control | Type | Range / states | Behaviour |
|---|---|---|---|
| Play | button | active when playing | Starts the ambient loop for the current atmosphere (or resumes after Pause) |
| Pause | button | active when paused | Pauses all audio, keeps position |
| Stop | button | — | Silences everything, stops the scene scheduler |
| Bring to Life / Stop | toggle button | off / on | Starts the scene scheduler (random pause, then next scene, repeat) — this is the normal "on" state of the box |
| Now playing | read-out | scene name; "Next m:ss · N left"; or elapsed / total while a scene plays | Live, updates every 0.6 s |
| Scene progress | bar | 0–100 % of current scene | Only while a scene plays |

## Utilities (rarely used)
| Control | Type | Range / states | Behaviour |
|---|---|---|---|
| LED test | toggle button | idle / running, with step label (each lamp in turn, All on, Stove flicker) | Cycles the four lamps so you can check wiring |
| Reboot Pi | button | — | Reboots the box; page shows "Rebooting…" |

## Lamps (4 objects: Upper ceiling, Lower ceiling, Stove, Exterior)
Per lamp, settings are stored per atmosphere (Day and Night each remember their own).
| Control | Type | Range / states | Behaviour |
|---|---|---|---|
| On / off | toggle | on / off | Immediate |
| Brightness | slider | 0–100 %, step 1 | Immediate, PWM |
| Flicker | toggle button | on / off (Stove calls it "Fire") | Adds random modulation on top of brightness |
| Flicker speed | slider | 1–5, step 0.5 | Higher = faster modulation |
| Flicker depth | slider | 10–90 %, step 5 | How deep the dips go |
| Fire sound volume | slider (Stove only) | 0–100 % | Volume of the crackling loop that plays while the stove lamp is on |
| Glow dot | indicator | brightness/flicker preview | Shows the current lamp state |

## Scenes (13 Day, 4 Night)
Each scene has: name, min pause and max pause before it (minutes), and a timeline of sound events (each event: sound, start time, duration, volume, pan, filter, reverb).
| Control | Type | Range / states | Behaviour |
|---|---|---|---|
| Scene button (one per scene, horizontal strip) | button | idle / firing (highlighted while it plays) | Fires the scene immediately, outside the schedule |
| Min / max pause | numeric (currently editor-only) | minutes; today 2–4 by day, 2–10 by night, one rare scene 15–40 | Random wait before this scene when the scheduler picks it |
| Timeline | read-out (currently editor-only) | list of sound events on a time axis | Could be shown as a strip on the scene page |

## Feedback and sound
- Every tap plays a short UI click on the box (not on the phone).
- The page must survive the box being offline: greyed controls, "Pi offline" badge, auto-reconnect.

## Data the page can read (for status displays)
Atmosphere, playing/stopped, master volume, stove volume, uptime, audio available, GPIO available, scheduler mode (idle / waiting / playing), current scene, seconds to next scene, scenes left in the shuffle, scene elapsed / total.

---

# Nederlandse versie — overzicht van bedieningselementen

Alles wat vandaag bestaat, met type, bereik en gedrag. Niets hier is hypothetisch.

## Globaal (altijd zichtbaar)
| Element | Type | Bereik / standen | Gedrag |
|---|---|---|---|
| Statusbadge | indicator | groen = Pi online, rood = offline, blauw = Mac-ontwikkelserver | Peilt elke 5 s; toont "Pi" / "Pi offline" |
| Atmosfeer | segmentschakelaar | Dag / Nacht | Wisselt scènepool, sfeerloop en getoonde lampinstellingen; stopt zelf het afspelen niet |
| Hoofdvolume | schuif | 0–100 % | Geldt voor alles |

## Transport en planner
| Element | Type | Bereik / standen | Gedrag |
|---|---|---|---|
| Play | knop | actief tijdens afspelen | Start de sfeerloop van de huidige atmosfeer (of hervat na Pauze) |
| Pauze | knop | actief bij pauze | Pauzeert alle audio, behoudt positie |
| Stop | knop | — | Maakt alles stil, stopt de scèneplanner |
| Tot leven brengen / Stop | schakelknop | uit / aan | Start de scèneplanner (willekeurige pauze, dan volgende scène, herhalen) — de normale "aan"-stand van de kast |
| Nu speelt | uitlezing | scènenaam; "Volgende m:ss · N over"; of verstreken / totaal tijdens een scène | Live, ververst elke 0,6 s |
| Scènevoortgang | balk | 0–100 % van huidige scène | Alleen tijdens een scène |

## Hulpmiddelen (zelden gebruikt)
| Element | Type | Bereik / standen | Gedrag |
|---|---|---|---|
| LED-test | schakelknop | inactief / bezig, met staplabel (elke lamp om beurten, Alles aan, Kachelflikker) | Doorloopt de vier lampen om bedrading te controleren |
| Pi herstarten | knop | — | Herstart de kast; pagina toont "Herstarten…" |

## Lampen (4 objecten: Plafond boven, Plafond onder, Kachel, Buiten)
Per lamp worden instellingen per atmosfeer bewaard (Dag en Nacht onthouden elk hun eigen).
| Element | Type | Bereik / standen | Gedrag |
|---|---|---|---|
| Aan / uit | schakelaar | aan / uit | Direct |
| Helderheid | schuif | 0–100 %, stap 1 | Direct, PWM |
| Flikker | schakelknop | aan / uit (bij Kachel heet het "Vuur") | Voegt willekeurige modulatie toe bovenop helderheid |
| Flikkersnelheid | schuif | 1–5, stap 0,5 | Hoger = snellere modulatie |
| Flikkerdiepte | schuif | 10–90 %, stap 5 | Hoe diep de dips gaan |
| Vuurgeluidvolume | schuif (alleen Kachel) | 0–100 % | Volume van de knetterloop zolang de kachellamp aan is |
| Gloeipunt | indicator | preview van helderheid/flikker | Toont de huidige lampstand |

## Scènes (13 Dag, 4 Nacht)
Elke scène heeft: naam, min. en max. pauze ervoor (minuten), en een tijdlijn van geluidsevents (per event: geluid, starttijd, duur, volume, pan, filter, galm).
| Element | Type | Bereik / standen | Gedrag |
|---|---|---|---|
| Scèneknop (één per scène, horizontale strook) | knop | inactief / speelt (oplichtend) | Speelt de scène direct af, buiten de planning om |
| Min. / max. pauze | numeriek (nu alleen in de editor) | minuten; nu 2–4 overdag, 2–10 's nachts, één zeldzame scène 15–40 | Willekeurige wachttijd vóór deze scène als de planner hem kiest |
| Tijdlijn | uitlezing (nu alleen in de editor) | lijst geluidsevents op een tijdas | Kan als strook op de scènepagina |

## Feedback en geluid
- Elke tik speelt een korte UI-klik op de kast (niet op de telefoon).
- De pagina moet overleven dat de kast offline is: gedimde bediening, badge "Pi offline", automatisch opnieuw verbinden.

## Gegevens die de pagina kan uitlezen (voor statusweergave)
Atmosfeer, speelt/gestopt, hoofdvolume, kachelvolume, uptime, audio beschikbaar, GPIO beschikbaar, plannerstand (inactief / wachtend / speelt), huidige scène, seconden tot volgende scène, resterende scènes in de shuffle, scène verstreken / totaal.
