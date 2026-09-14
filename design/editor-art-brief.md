# Signalbox editor — art brief

For the artboard `Signalbox editor.svg`, 1512 × 982.
Hand this to ChatGPT. It says what to draw, and which layers are **controls** (they change
state or move) versus **backdrop** (they never change).

---

## A. How the file must be split

Three kinds of layer, kept apart:

| Kind | Changes? | Export as |
|---|---|---|
| **Backdrop, fixed** | never | one flat image per element |
| **Backdrop, stretchable** | resizes with content | its own small image, plain middle, corners intact |
| **Control** | two or more states, or moves | one image per state, transparent background |

The third column matters. A scene panel has to grow when a scene has more sounds, so it
cannot live inside one flat picture of the whole screen. Each stretchable frame is cut into
nine pieces at build time: four fixed corners, four edges that repeat along one axis, and a
middle that tiles. Draw it small with a plain middle and it will grow to any size.

---

## B. Backdrop, stretchable — needed as separate images

Draw each at its **smallest sensible size**, with nothing crossing the middle.

1. **Scene panel frame** — grows in width and height.
2. **Inset field frame** — the recessed text field, used for the scene title, the intervals,
   the story name and the sound picker. Grows in width.
3. **Timeline well** — the large dark area inside a scene. Grows both ways.
4. **Sounds list well** — the tall inset in the left column. Grows in height.
5. **Header plate** — the recessed plates along the top. Grows in width.
6. **Background metal** — a seamless tile, roughly 400 × 400, no distinguishing marks.

Rules for these six:
- Screws in the corners. Put one in the **centre of each long edge** as well, and they will
  space themselves evenly as a panel grows, which reads as a bigger machine.
- **No lighting across the whole frame.** A sweep of highlight, or corners darkened by a
  vignette, will repeat and look wrong. Keep the light even within each frame.
- Give the edges and middle **60 points or more** of varied metal, so the repeat is not
  obvious.

---

## C. Controls to draw — new

Sizes follow the ones already on the artboard, so they sit together.
Every control needs **an off state and an on state**, on a transparent background.

| # | Control | Size | States | Where |
|---|---|---|---|---|
| 1 | **Pi lamp, unlit** | 34 × 33 | the dark lens to pair with the existing lit one | header, x 1204 |
| 2 | **Day / Night switch** | fits 235 × 56 | two positions | the empty header plate at **x 460–695** |
| 3 | **Save** push | 70 × 59 | idle, pressed; plus a lit variant for unsaved work | header |
| 4 | **Revert** push | 70 × 59 | idle, pressed | header |
| 5 | **Add scene** | about 160 × 40 | idle, pressed | below the last scene |
| 6 | **Remove scene** | 28 × 28 | idle, pressed | scene panel, by the transport |
| 7 | **Refresh sounds** | 24 × 24 | idle, pressed | beside the SOUNDS plate |
| 8 | **Master volume knob** | 56 × 56 | one image, rotated in code | header |
| 9 | **Inspector knob** | 44 × 44 | **one design, reused nine times** | inspector row |
| 10 | **Story restart** | 24 × 24 | idle, pressed | story strip |

On 8 and 9: draw the knob **pointing straight up** and unrotated. It is turned in code, as on
the phone panels. One knob covers all nine inspector controls.

---

## D. Backdrop to draw — new

1. **Brass plates**, in the style of the existing SCENE / SOUND / SOUNDS:
   `LOOP` · `STORY` · `INSPECTOR`
2. **Engraved labels** beside the scene fields: `MIN` · `MAX` · `STORY` · `STEP`
3. **Engraved labels** for the inspector's nine knobs:
   `VOL` · `PAN` · `FILTER` · `START` · `LENGTH` · `FADE IN` · `FADE OUT` · `ROOM` · `WET`
4. **A dial scale** for the inspector knob: a small arc of ticks, drawn once, reused nine times.
5. **Sun and moon** either side of the Day / Night switch, matching the phone panel.

---

## E. Export rules

- **One layer per item, named exactly** as in the tables above.
- State pairs named `<name> off` and `<name> on`. Keep the two the same size and position.
- **Transparent background** on every control.
- Export at **three times** final size. The current file is one-to-one and looks soft on a
  retina screen.
- For each stretchable frame, say how many pixels in from each edge the fixed corner ends.

---

## F. Do not draw

- Any text that is a **value**: scene names, numbers, times, sound names, percentages.
  All of that is live and rendered in code.
- The coloured blocks on the timeline. Drawn in code, one colour per sound.
- Anything that changes with the data.

---
---

# Signalbox editor — kunstopdracht

Voor het artboard `Signalbox editor.svg`, 1512 × 982.
Geef dit aan ChatGPT. Het beschrijft wat er getekend moet worden, en welke lagen
**bedieningselementen** zijn (ze wisselen van stand of bewegen) en welke **achtergrond**
(die nooit verandert).

---

## A. Hoe het bestand gesplitst moet worden

Drie soorten lagen, gescheiden gehouden:

| Soort | Verandert? | Exporteren als |
|---|---|---|
| **Achtergrond, vast** | nooit | één platte afbeelding per element |
| **Achtergrond, rekbaar** | schaalt mee met de inhoud | eigen kleine afbeelding, vlak midden, hoeken intact |
| **Bediening** | twee of meer standen, of beweegt | één afbeelding per stand, transparante achtergrond |

Die derde kolom is het belangrijkst. Een scènepaneel moet groeien als een scène meer geluiden
heeft, dus het kan niet in één platte afbeelding van het hele scherm zitten. Elk rekbaar kader
wordt bij het bouwen in negen stukken geknipt: vier vaste hoeken, vier randen die langs één as
herhalen, en een midden dat tegelt. Teken het klein met een vlak midden en het groeit naar elke maat.

---

## B. Achtergrond, rekbaar — nodig als losse afbeeldingen

Teken elk op de **kleinst zinnige maat**, met niets dat door het midden loopt.

1. **Kader scènepaneel** — groeit in breedte en hoogte.
2. **Kader invoerveld** — het verzonken tekstveld, gebruikt voor scènetitel, intervallen,
   verhaalnaam en geluidskeuze. Groeit in breedte.
3. **Tijdlijnvak** — het grote donkere vlak in een scène. Groeit in beide richtingen.
4. **Geluidenlijstvak** — het hoge vlak in de linkerkolom. Groeit in hoogte.
5. **Kopplaat** — de verzonken platen bovenaan. Groeit in breedte.
6. **Achtergrondmetaal** — een naadloze tegel, ongeveer 400 × 400, zonder herkenbare kenmerken.

Regels voor deze zes:
- Schroeven in de hoeken. Zet er ook één **midden op elke lange rand**, dan verdelen ze zichzelf
  gelijkmatig als een paneel groeit, wat leest als een grotere machine.
- **Geen belichting over het hele kader.** Een doorlopende glans, of hoeken die door een vignet
  donkerder worden, herhaalt zich en gaat er verkeerd uitzien. Houd het licht gelijkmatig binnen elk kader.
- Geef de randen en het midden **60 punten of meer** aan gevarieerd metaal, zodat de herhaling
  niet opvalt.

---

## C. Bediening om te tekenen — nieuw

Maten volgen wat al op het artboard staat, zodat ze bij elkaar passen.
Elk element heeft **een uit-stand en een aan-stand** nodig, op transparante achtergrond.

| # | Element | Maat | Standen | Waar |
|---|---|---|---|---|
| 1 | **Pi-lampje, gedoofd** | 34 × 33 | de donkere lens naast de bestaande brandende | kop, x 1204 |
| 2 | **Dag / Nacht-schakelaar** | past in 235 × 56 | twee standen | de lege kopplaat op **x 460–695** |
| 3 | **Opslaan**-drukknop | 70 × 59 | rust, ingedrukt; plus een brandende variant voor niet-opgeslagen werk | kop |
| 4 | **Terugdraaien**-drukknop | 70 × 59 | rust, ingedrukt | kop |
| 5 | **Scène toevoegen** | ongeveer 160 × 40 | rust, ingedrukt | onder de laatste scène |
| 6 | **Scène verwijderen** | 28 × 28 | rust, ingedrukt | scènepaneel, bij het transport |
| 7 | **Geluiden verversen** | 24 × 24 | rust, ingedrukt | naast de SOUNDS-plaat |
| 8 | **Hoofdvolumeknop** | 56 × 56 | één afbeelding, in code gedraaid | kop |
| 9 | **Inspectieknop** | 44 × 44 | **één ontwerp, negen keer hergebruikt** | inspectierij |
| 10 | **Verhaal herstarten** | 24 × 24 | rust, ingedrukt | verhaalstrook |

Over 8 en 9: teken de knop **recht omhoog wijzend** en ongedraaid. Hij wordt in code gedraaid,
net als op de telefoonpanelen. Eén knop volstaat voor alle negen inspectieregelaars.

---

## D. Achtergrond om te tekenen — nieuw

1. **Messing plaatjes**, in de stijl van de bestaande SCENE / SOUND / SOUNDS:
   `LOOP` · `STORY` · `INSPECTOR`
2. **Gegraveerde labels** naast de scènevelden: `MIN` · `MAX` · `STORY` · `STEP`
3. **Gegraveerde labels** voor de negen inspectieknoppen:
   `VOL` · `PAN` · `FILTER` · `START` · `LENGTH` · `FADE IN` · `FADE OUT` · `ROOM` · `WET`
4. **Een wijzerplaat** voor de inspectieknop: een boogje met streepjes, één keer getekend,
   negen keer hergebruikt.
5. **Zon en maan** aan weerszijden van de Dag / Nacht-schakelaar, passend bij het telefoonpaneel.

---

## E. Exportregels

- **Eén laag per element, exact benoemd** zoals in de tabellen hierboven.
- Standenparen heten `<naam> off` en `<naam> on`. Houd beide even groot en op dezelfde plek.
- **Transparante achtergrond** bij elk bedieningselement.
- Exporteer op **drie keer** de eindmaat. Het huidige bestand staat op één-op-één en oogt
  zacht op een retina-scherm.
- Geef bij elk rekbaar kader aan hoeveel pixels vanaf elke rand de vaste hoek eindigt.

---

## F. Niet tekenen

- Tekst die een **waarde** is: scènenamen, getallen, tijden, geluidsnamen, percentages.
  Dat is allemaal live en wordt in code gezet.
- De gekleurde blokken op de tijdlijn. Die worden in code getekend, één kleur per geluid.
- Alles wat met de data meeverandert.
