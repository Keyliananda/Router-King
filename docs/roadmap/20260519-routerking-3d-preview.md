# RouterKing G-code Preview Roadmap

## Zielbild

Die RouterKing Preview soll von der aktuellen projizierten G-code Ansicht zu einer echten interaktiven 3D-Ansicht wachsen:

- Arbeitsraum als echtes Volumen mit X/Y/Z-Ausdehnung.
- Fräsbahn, HOME, CUT START, Werkzeugradius und Fit-Kandidaten in gemeinsamen Maschinenkoordinaten.
- Mausbedienung fuer orbit, pan, zoom und spaeter 3D-Picking.
- Gleiche Datenquelle fuer Inline-Preview, separates Preview-Fenster, Snap und Validierung.

## Ist-Stand

- Die Preview rendert G-code Segmente als 3D-Daten, projiziert sie aber in eine `QGraphicsScene`.
- Iso/Top/Side/Front sind feste Projektionen.
- Z-View-Rotation ist in 90-Grad-Schritten waehlbar und beeinflusst nur die Anzeige/Snap-Projektion, nicht den G-code.
- Der Maschinenarbeitsraum wird als X/Y/Z-Box aus dem Maschinenprofil gerendert.
- G-code-Pfad, HOME, CUT START, Werkzeugdummy, Snap-Punkte, Fit-Kandidaten und Arbeitsraum laufen ueber dieselbe `PreviewTransform` von Maschinenraum nach Preview-Welt. Top/Iso unterscheiden sich danach nur noch durch die Projektion.
- Manual-XYZ-Preview startet beim Prepare an der realen Live-WPos des Fraesers. Alte G-code-Startpunkte im Editor werden nicht mehr als Baseline fuer die Controller-Bewegung verwendet.

## Phase 1: Datenmodell stabilisieren

- [x] Gemeinsame Maschinenraum-Transformation fuer Pfad, Marker, Arbeitsraum, Snap und Fit-Kandidaten einfuehren.
- [x] Manual-XYZ-Delta als reale 1:1-mm-Bewegung aus der Prepare-Position absichern.
- [ ] Preview-State als eigenes Objekt kapseln: G-code Path, Maschinenprofil, Work Offset, Projection, Z-Rotation, Tool Area, Manual Start.
- Maschinenprofil-Konflikte sichtbar melden, z.B. wenn `$130/$131/$132` und gespeicherte Limits auseinanderlaufen.
- Akzeptanz: HOME, CUT START, Arbeitsraum und Fräsbahn liegen in jeder Projektion deckungsgleich nachvollziehbar.

### Aenderung 2026-05-19

Problem: Top- und Iso-Ansicht konnten scheinbar auseinanderlaufen, weil mehrere Preview-Schichten zwar aehnliche, aber nicht explizit gemeinsame Transformationspfade nutzten. Zusaetzlich wurde die Manual-XYZ-Preview beim Prepare an einem alten G-code-Cut-Start verankert, falls solcher G-code bereits im Editor stand.

Umsetzung: `PreviewTransform` kapselt jetzt Swap, Flip und Z-Rotation. Die RouterKing-Preview benutzt diese eine Transformation fuer G-code-Pfad, Snap-Kandidaten, HOME/CUT-START-Marker, Arbeitsraum, Werkzeugdummy und Fit-Kandidaten. Manual-XYZ verwendet die Live-WPos beim Prepare als Baseline und verschiebt die Preview danach 1:1 um die gemessene MPos-Bewegung.

Tests: Abgedeckt sind Top/Iso-Projektion aus derselben Preview-Weltposition, Snap-vs-Render-Konsistenz in Iso, FoxAlien-400x400x60-Arbeitsraum, Manual-XYZ-1:1-mm-Delta und der Fall, dass bei gleichem HOME/CUT-START-X/Y kein irrefuehrender diagonaler HOME-Leitstrich erzeugt wird.

## Phase 2: QGraphics-Orbit-MVP

- Innerhalb der bestehenden `QGraphicsView` freie Kamera-Winkel als Matrix einfuehren.
- Maus links: orbit, mittlere/rechte Taste: pan, Rad: zoom.
- Presets Iso/Top/Side/Front bleiben als Reset-Punkte.
- Picking bleibt zunaechst snap-basiert auf projizierten Punkten.
- Akzeptanz: Rotation veraendert nur die Kamera, nicht die Maschinenkoordinaten oder den generierten G-code.

## Phase 3: Echte 3D-Render-Backend-Option

- `QOpenGLWidget` als separates Preview-Backend pruefen.
- Rendering-Schichten: Arbeitsraum, G-code Linien, Rapid Moves, Werkzeugvolumen, Marker, Textlabels.
- Fallback auf `QGraphicsView`, falls OpenGL in FreeCAD/PySide nicht verfuegbar ist.
- Akzeptanz: grosse G-code Jobs bleiben fluessig zoombar und drehbar.

## Phase 4: 3D-Picking und Snapping

- Raycasting auf Snap-Punkte, Arbeitsraum-Ecken und Werkzeugpfad-Segmente.
- Snap-Radius bildschirmbasiert beibehalten, aber Kandidaten im 3D-Raum bewerten.
- Fit-Corner und Cut-Start-Snap verwenden exakt dieselbe Picking-Pipeline.
- Akzeptanz: Der geklickte Punkt ist reproduzierbar, unabhaengig von Kamera-Winkel und Zoom.

## Phase 5: Maschinenprofil-Integration

- Maschinenmodelle als ladbare Profile pflegen, inklusive FoxAlien Masuter Pro.
- Profil-Import/Export, aktive Datei, aktuelle GRBL-Settings und Konflikte in der UI anzeigen.
- Optional spaeter: bekannte Presets als JSON-Dateien unter `RouterKing/profiles/`.
- Akzeptanz: Ein neues Profil aktualisiert Validierung, Preview-Arbeitsraum und Sicherheitsfahrten ohne Neustart.
