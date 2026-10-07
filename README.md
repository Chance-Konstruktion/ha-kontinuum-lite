# KONTINUUM Lite

[![Tests](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/tests.yaml/badge.svg)](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/tests.yaml)
[![Validate with hassfest](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/hassfest.yaml)
[![HACS Validate](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/validate.yaml/badge.svg)](https://github.com/Chance-Konstruktion/ha-kontinuum-lite/actions/workflows/validate.yaml)
[![HACS: Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0%2B-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![kontinuum-core](https://img.shields.io/badge/kontinuum--core-%E2%89%A50.7.0-4c1.svg)](https://github.com/Chance-Konstruktion/kontinuum-core)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

> Headless, lightweight variant of [KONTINUUM](https://github.com/Chance-Konstruktion/ha-kontinuum) — no UI, no brand assets, just the learning substrate.

> **Teil der 3-Repo-Familie:**
> [`kontinuum-core`](https://github.com/Chance-Konstruktion/kontinuum-core) (HA-freie Lern-Engine, PyPI) ·
> [`ha-kontinuum`](https://github.com/Chance-Konstruktion/ha-kontinuum) (volle Pro-Integration mit UI) ·
> **ha-kontinuum-lite** (dieses Repo)

## Was ist das?

`kontinuum-lite` ist eine schlanke Home-Assistant-Integration, die das
neuroinspirierte Lern-Substrat von KONTINUUM bereitstellt — **ohne** das
volle Pro-Paket (Dashboard, Brain-Visualisierung, Brand-Assets).

Ideal für:
- Headless-HA-Instanzen ohne Dashboard-Bedarf
- Reine Automatisierungen/Trigger auf Anomalien
- Entwickler, die nur die Engine-API brauchen

## Entitäten

| Entität | Typ | Werte | Attribute |
|---|---|---|---|
| `sensor.kontinuum_lite_surprise` | numerisch | `0.0` … `1.0` | `anomaly_threshold`, `token` |
| `sensor.kontinuum_lite_learning_state` | kategorisch | `cold_start` / `learning` / `stable` | `tick`, `total_events`, `next_event`, `next_event_probability`, `hit_rate` |
| `binary_sensor.kontinuum_lite_anomaly` | on/off | device_class `problem` | `surprise`, `threshold`, `expected_next_room` |
| `sensor.kontinuum_lite_situation` | numerisch | Personen, die das Lagebild für daheim hält | `presence`, `associations`, `learning` |
| `sensor.kontinuum_lite_presence_<person>` | numerisch | `0` … `100` % | `most_likely`, `reported`, `evidence`, `time_of_day`, `ticks`, `checked`, `hit_rate` |

Die letzten beiden gibt es ab `kontinuum-core` 0.7 (siehe [Lagebild](#lagebild-ab-kontinuum-core-07)).

> Die **adaptive Anomalie-Schwelle** (`threshold` / `anomaly_threshold`) macht
> sichtbar, ab welchem Surprise-Wert geflaggt wird — praktisch fürs Tuning von
> Automatisierungen. `token` ist das aktuelle `raum.semantik.zustand`-Symbol,
> über das die Engine gerade „nachdenkt". `next_event` ist ihr erster Tipp für
> das nächste Ereignis; `hit_rate` sagt, wie oft dieser erste Tipp bisher
> stimmte (ab 0.7, sonst leer).

> **Hinweis:** Trackt die Engine (z. B. im `labeled`-Modus ohne passende
> Labels) keine Entities, lernt sie nichts und meldet das als **Reparatur**
> (Einstellungen → Reparaturen); sie verschwindet, sobald wieder Entities
> getrackt werden.

## Einstellungen (nah an Pro)

Der Config- und Options-Flow ist bewusst so nah wie möglich an der
Pro-Integration (`ha-kontinuum`) gehalten — nur ohne Dashboard, Cortex und
LLM-Anbindung —, damit ein späterer Wechsel Lite → Pro keine Umgewöhnung
erfordert.

Bei der Einrichtung wählst du eine **Persönlichkeit** (Mutig / Ausgeglichen /
Konservativ). Alles Weitere steht unter **Konfigurieren → Allgemeine
Einstellungen**:

- **Betriebsmodus** — `shadow` (nur beobachten), `confirm` (fragt vor jeder
  Aktion per **actionable Benachrichtigung**) oder `active` (handelt
  selbstständig).
- **Entity-Tracking-Modus** — `standard` (alle Entities, Opt-out über das Label
  `ignore_kontinuum`), `labeled` (Opt-in: nur Entities mit dem Label
  `kontinuum`) oder `auto` (intelligenter Heuristik-Filter). **Standardmäßig
  sieht die Engine also alles** — kein manuelles Auswählen einzelner Entities
  mehr nötig.
- **Home-Only Modus** — pausiert das Lernen, wenn niemand zuhause ist (das
  Lagebild läuft weiter, siehe unten).

Die Integration entdeckt alle Entities automatisch (mit Area + Labels aus den
HA-Registries) und abonniert jeden Zustandswechsel; der Core-Thalamus filtert
anhand des Tracking-Modus.

> Damit eine Entity gelernt wird, muss der Core sie einem **Raum** zuordnen
> können (`area`/`friendly_name`). Entities ohne zuordenbaren Bereich werden
> ggf. übersprungen — weise ihnen also einen Bereich zu.

### Handeln: shadow / confirm / active

Im `confirm`-Modus legt die Engine eine geplante Aktion in die Warteschlange
und fragt per **actionable Notification** (Buttons **Bestätigen** / **Ablehnen**)
nach; ohne Companion-App gehen auch die Services `kontinuum_lite.confirm_action`
/ `reject_action` (mit `confirm_id`). Machst du eine KONTINUUM-Aktion innerhalb
von 60 s manuell rückgängig, lernt die Engine daraus (negatives Feedback).

## Lagebild (ab kontinuum-core 0.7)

Mit `kontinuum-core` 0.7 hört die Engine nicht mehr nur Einzelereignisse,
sondern sieht die **ganze Lage**: alle Gerätezustände zusammen und wie lange
schon. `unavailable` heißt dabei „weg“ — die Reifendrucksensoren eines Autos
melden sich ab, wenn es wegfährt, und genau das ist ein Hinweis. Leistungen
bekommen gelernte Gerätestufen (3 W Standby ist nicht 100 W Betrieb), und alle
5 Minuten wird eine Paar-Tafel „wenn A, dann B“ fortgeschrieben.

- **Anwesenheit je Person** (`sensor.kontinuum_lite_presence_<person>`): wie
  wahrscheinlich die Person daheim ist, **allein aus den Geräten** geschlossen.
  Ihre eigenen Tracker (Attribut `device_trackers` der `person`-Entität) sind
  das Etikett, nie ein Indiz — der Sensor ist eine zweite Meinung: Schweigt
  das Handy, ist er die einzige; liegt das Handy im Büro, widerspricht er ihm.
  `evidence` nennt die stärksten Belege, `hit_rate` wie oft der Schluss bisher
  zum Tracker passte (ehrlich geprüft: mit Wissen, das mindestens einen Tag
  alt ist). Der Sensor erscheint nach dem ersten Tag.
- **`sensor.kontinuum_lite_situation`** zählt die Personen, die das Lagebild
  für daheim hält, und trägt die stärksten Zusammenhänge der Paar-Tafel.
- Die **Vorhersage** des nächsten Ereignisses kommt aus der „Börse“ des Kerns,
  die alle Vorhersager nach ihrer echten Trefferquote mischt (gemessen auf
  fünf öffentlichen CASAS-Häusern: +9 bis +14 Punkte Top-1 über der besten
  einfachen Regel). Im `active`/`confirm`-Modus handelt die Engine auf dieser
  Grundlage.
- **Home-Only:** Das Lernen pausiert, das Lagebild nicht — das leere Haus ist
  genau das, woraus es „weg“ lernt.
- **Raspberry Pi:** Die Anwesenheit wird höchstens minütlich neu gelesen, die
  Zusammenhänge der Paar-Tafel (quadratisch) nur stündlich; die großen
  Attribute gehen nicht in den Recorder.

Diese Sensoren verlangen `kontinuum-core` 0.7; die Manifest-Regel steht seit
Lite 0.7.0 auf `>=0.7.0,<0.8`.

## Services

| Service | Zweck |
|---|---|
| `kontinuum_lite.evaluate` | Einen Engine-Tick aus manuellem Payload ausführen (Tests/Debug) |
| `kontinuum_lite.save_brain` | Sofortige Momentaufnahme des Gehirns auf die Platte erzwingen |
| `kontinuum_lite.reset_brain` | **Alles** Gelernte löschen und kalt neu starten (nicht umkehrbar) |
| `kontinuum_lite.set_mode` | Betriebsmodus umschalten (`shadow` / `confirm` / `active`) |
| `kontinuum_lite.confirm_action` | Wartende Aktion bestätigen (`confirm_id` oder `confirm_all: true`) |
| `kontinuum_lite.reject_action` | Wartende Aktion ablehnen (negatives Feedback an BG/Amygdala) |

### `evaluate` (optional / fortgeschritten)

Für manuelles Einspeisen oder Tests:

```yaml
service: kontinuum_lite.evaluate
data:
  payload:
    entity_id: binary_sensor.flur_bewegung
    new_state: "on"
    old_state: "off"
```

Führt einen Engine-Tick aus und feuert `kontinuum_lite_anomaly` auf den
Event-Bus, sobald der Surprise-Wert die (adaptive) Anomalie-Schwelle kreuzt.
Das Event enthält `surprise`, `learning_state`, `tick` und `entity_id`.

> Hinweis: Ein Payload ohne `entity_id`/`new_state` (oder für eine nicht
> ausgewählte/raumlose Entity) ist ein No-op fürs Lernen — der Core filtert
> ihn heraus.

### `save_brain` / `reset_brain`

`save_brain` schreibt sofort einen Snapshot (sonst passiert das periodisch,
beim Entladen und beim HA-Shutdown). `reset_brain` löscht das gelernte Gehirn
**und** die MetaPlasticity-Meta-Daten und lädt die Integration kalt neu —
nützlich, wenn das Modell „verdorben" ist und neu anlernen soll.

## Installation

### HACS (empfohlen)

1. HACS → Integrations → Custom Repositories
2. `https://github.com/Chance-Konstruktion/ha-kontinuum-lite` als **Integration** hinzufügen
3. "KONTINUUM Lite" installieren
4. Home Assistant neu starten
5. Einstellungen → Integrationen → "KONTINUUM Lite" hinzufügen

### Manuell

```
<config>/custom_components/kontinuum_lite/
```

## Status

**Phase 1+** — die Engine delegiert vollständig an
[`kontinuum-core`](https://github.com/Chance-Konstruktion/kontinuum-core)
(via `requirements: ["kontinuum-core>=0.7.0,<0.8"]` im manifest):
- **Automatische Daten-Ingestion**: ausgewählte Entities werden registriert
  (mit Area/Metadaten) und ihre Zustandswechsel live in die Engine gefüttert
- Echte Lern-Pipeline (Thalamus → Hippocampus → Predictive Processing → …)
- Lernzustand abgeleitet aus `hippocampus.total_events` und `accuracy`
- Anomalie bei **adaptiver** Surprise-Schwelle (robust: Median + MAD der
  letzten Surprise-Werte, geklemmt auf `0.10`–`0.95`; bis ~30 Beobachtungen
  gilt der Default `0.7`)
- Gelerntes Gehirn wird über Neustarts hinweg persistiert (Snapshot nur bei
  neuen Ticks → schont Flash/SD)
- Optional: 24 h MetaPlasticity-Loop via HAScheduler-Adapter
- Diagnostics (Einstellungen → Geräte → KONTINUUM Lite → Diagnose) zeigen
  Core-Version, Persistenz-Support und Lernfortschritt

Siehe [ROADMAP.md in ha-kontinuum](https://github.com/Chance-Konstruktion/ha-kontinuum/blob/main/ROADMAP.md) für den Gesamtplan der 3-Repo-Architektur.

## Lizenz

AGPL-3.0 — siehe [LICENSE](LICENSE).

Diese Integration bindet [`kontinuum-core`](https://github.com/Chance-Konstruktion/kontinuum-core)
(AGPL-3.0) als Requirement ein und lädt es im selben Home-Assistant-Prozess.
Das verteilte Gesamtwerk steht daher unter der **AGPL-3.0** — passend zur
Lizenz von kontinuum-core.
