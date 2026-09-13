# Prompt: iPhone control app concept for the Signalbox (for ChatGPT → SVG)

_Paste everything below the line into ChatGPT. Ask for the SVG as a downloadable file, not inline text._

---

You are a senior product designer. Design a concept UI for an iPhone web app that controls a physical model: a Gauge 0 scale, 3D-printed Great Western Railway signal box with ambient sound and lighting, driven by a Raspberry Pi. The app is a full-screen mobile web page (home-screen web app), portrait only, used at arm's length in a dim room. Deliver the design as SVG artboards so a developer can refactor it into HTML/CSS.

## What the box does
- Plays an **ambient loop** continuously, plus **scenes** (short scripted sound stories such as a train passing, a phone call, tea being made) that fire one at a time with a random pause between them. There are two **atmospheres**: Day (13 scenes) and Night (4 scenes), each with its own loop, scene pool and lighting levels.
- Has **four lamps**: Upper ceiling, Lower ceiling, Stove (fire glow with a crackling fire sound), Exterior lamp. Each lamp has on/off, brightness, a flicker toggle, flicker speed and flicker depth. The stove additionally has a fire-sound volume.
- Runs on its own after power-up. The phone is for overrides and tweaks, not for keeping it alive.

## Information architecture (this is the brief)
1. **Main page** — overarching controls only:
   - Connection/status badge (Pi online / offline, current atmosphere, uptime)
   - Atmosphere switch: Day / Night
   - Transport: Play, Pause, Stop (Play resumes the scheduler; Stop silences everything)
   - Master volume
   - "Now playing": current scene name, progress, and a countdown to the next scene
   - Utilities tucked away: LED test, Reboot Pi
2. **One swipeable page per object** (horizontal paging with a page indicator, or a card deck), reachable from the main page and from each other:
   - **Each lamp** (4 pages): big on/off, brightness, flicker on/off, speed, depth; stove page also has fire-sound volume. Show a live glow preview of the lamp state.
   - **Each scene** (17 pages, grouped by atmosphere): "Fire now" button, min/max pause before this scene (in minutes), the scene's timeline of sound events as a simple horizontal strip, and a "playing now" state.
   - A compact **index/overview** page listing all objects so you can jump directly.
3. Navigation must be one-handed: bottom-anchored controls, swipe between pages, a persistent mini header showing atmosphere and a tiny transport control so you never lose the main state.

## Tone and visual language
- Evoke a 1930s GWR signal box: dark timber, brass, cream enamel, lever-frame colours (red, black, blue, yellow levers), lamp glow. Restrained, tactile, not kitsch. Typography with a railway-signage feel for headings, a plain sans for values.
- Dark UI by default; it is used in a dimly lit room. Large touch targets (min 44 pt). Clear active/inactive states. Sliders must be comfortable to drag with a thumb.

## Deliverable format (strict)
- iPhone artboards at 390 × 844 pt, portrait. Produce: Main page; Index page; one Lamp page (Stove, showing all controls); one Scene page (Day scene, with timeline strip); and a strip showing the paging/swipe model with the persistent mini header.
- Output **one SVG file per artboard**, valid SVG 1.1, `viewBox="0 0 390 844"`, real `<text>` elements (no outlined type), no raster images, no external fonts or links. Group elements with `<g id="...">` using descriptive ids (e.g. `header`, `atmosphere-switch`, `transport`, `volume-slider`, `now-playing`, `page-indicator`, `lamp-brightness`, `scene-timeline`). Use a small consistent palette declared as named colours in a `<style>` block, and define reusable components with `<symbol>` + `<use>` (button, slider, toggle, card).
- Include a short legend on the artboard margin, or in a separate text block, listing components, colours, spacing scale and font sizes, so the design can be turned into CSS variables.
- Before drawing, briefly state your design decisions (5–8 bullets), then produce the SVGs.

Do not add features beyond the list above. Where a control's exact behaviour is unclear, choose the simplest reading and note the assumption.

---

# Nederlandse versie

_Plak alles onder de streep in ChatGPT. Vraag om de SVG als downloadbaar bestand, niet als tekst._

---

Je bent een senior productontwerper. Ontwerp een concept-UI voor een iPhone-webapp die een fysiek model bestuurt: een 3D-geprint Great Western Railway-seinhuis op schaal 0, met sfeergeluid en verlichting, aangestuurd door een Raspberry Pi. De app is een schermvullende mobiele webpagina (beginscherm-webapp), alleen staand, gebruikt op armlengte in een schemerige kamer. Lever het ontwerp als SVG-artboards zodat een ontwikkelaar het kan omzetten naar HTML/CSS.

## Wat de kast doet
- Speelt continu een **sfeerloop**, plus **scènes** (korte geluidsverhaaltjes zoals een passerende trein, een telefoontje, thee zetten) die één voor één afgaan met een willekeurige pauze ertussen. Er zijn twee **atmosferen**: Dag (13 scènes) en Nacht (4 scènes), elk met eigen loop, scènepool en lichtniveaus.
- Heeft **vier lampen**: Plafond boven, Plafond onder, Kachel (vuurgloed met knetterend vuurgeluid), Buitenlamp. Elke lamp heeft aan/uit, helderheid, flikker aan/uit, flikkersnelheid en flikkerdiepte. De kachel heeft daarnaast een volume voor het vuurgeluid.
- Draait zelfstandig na inschakelen. De telefoon is voor ingrijpen en bijstellen, niet om het draaiend te houden.

## Informatiearchitectuur (dit is de opdracht)
1. **Hoofdpagina** — alleen overkoepelende bediening:
   - Verbindings-/statusbadge (Pi online / offline, huidige atmosfeer, uptime)
   - Atmosfeerschakelaar: Dag / Nacht
   - Transport: Play, Pauze, Stop (Play hervat de planner; Stop maakt alles stil)
   - Hoofdvolume
   - "Nu speelt": naam van de huidige scène, voortgang en aftelling naar de volgende scène
   - Weggestopte hulpmiddelen: LED-test, Pi herstarten
2. **Eén swipebare pagina per object** (horizontaal bladeren met pagina-indicator, of een kaartenstapel), bereikbaar vanaf de hoofdpagina en vanaf elkaar:
   - **Elke lamp** (4 pagina's): grote aan/uit, helderheid, flikker aan/uit, snelheid, diepte; de kachelpagina ook vuurgeluidvolume. Toon een live gloed-preview van de lampstand.
   - **Elke scène** (17 pagina's, gegroepeerd per atmosfeer): knop "Nu afspelen", min/max pauze vóór deze scène (in minuten), de tijdlijn van geluidsevents als eenvoudige horizontale strook, en een "speelt nu"-status.
   - Een compacte **index/overzichtspagina** met alle objecten om direct te springen.
3. Navigatie moet eenhandig kunnen: bediening onderaan verankerd, swipen tussen pagina's, een vaste mini-header met atmosfeer en een kleine transportknop zodat je de hoofdstatus nooit kwijtraakt.

## Toon en beeldtaal
- Roep een GWR-seinhuis uit de jaren dertig op: donker hout, messing, crème emaille, kleuren van het hefboomframe (rood, zwart, blauw, geel), lampgloed. Ingetogen, tastbaar, niet kitscherig. Koppen met een gevoel van spoorwegbewegwijzering, waarden in een neutrale schreefloze letter.
- Standaard donkere UI; wordt gebruikt in een schemerige ruimte. Grote aanraakdoelen (minimaal 44 pt). Duidelijke actief/inactief-staten. Schuifregelaars moeten prettig met de duim te bedienen zijn.

## Opleverformaat (strikt)
- iPhone-artboards van 390 × 844 pt, staand. Maak: Hoofdpagina; Indexpagina; één Lamppagina (Kachel, met alle regelaars); één Scènepagina (dagscène, met tijdlijnstrook); en een strook die het blader-/swipemodel met de vaste mini-header toont.
- Lever **één SVG-bestand per artboard**, geldige SVG 1.1, `viewBox="0 0 390 844"`, echte `<text>`-elementen (geen omgetrokken letters), geen rasterafbeeldingen, geen externe fonts of links. Groepeer elementen met `<g id="...">` met beschrijvende ids (bijv. `header`, `atmosphere-switch`, `transport`, `volume-slider`, `now-playing`, `page-indicator`, `lamp-brightness`, `scene-timeline`). Gebruik een klein, consistent palet als benoemde kleuren in een `<style>`-blok, en definieer herbruikbare componenten met `<symbol>` + `<use>` (knop, schuif, schakelaar, kaart).
- Voeg een korte legenda toe in de marge van het artboard of als apart tekstblok met componenten, kleuren, afstandsschaal en lettergroottes, zodat het ontwerp naar CSS-variabelen kan worden vertaald.
- Benoem vóór het tekenen kort je ontwerpkeuzes (5–8 punten) en maak daarna de SVG's.

Voeg geen functies toe buiten bovenstaande lijst. Waar het exacte gedrag van een regelaar onduidelijk is, kies de eenvoudigste lezing en noteer de aanname.
