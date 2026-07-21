# KONTINUUM Lite

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
| `sensor.kontinuum_lite_learning_state` | kategorisch | `cold_start` / `learning` / `stable` | `tick`, `total_events` |
| `binary_sensor.kontinuum_lite_anomaly` | on/off | device_class `problem` | `surprise`, `threshold`, `expected_next_room` |

> Die **adaptive Anomalie-Schwelle** (`threshold` / `anomaly_threshold`) macht
> sichtbar, ab welchem Surprise-Wert geflaggt wird — praktisch fürs Tuning von
> Automatisierungen. `token` ist das aktuelle `raum.semantik.zustand`-Symbol,
> über das die Engine gerade „nachdenkt".

> **Hinweis:** Ist keine Entity ausgewählt, lernt die Integration nichts und
> meldet das als **Reparatur** (Einstellungen → Reparaturen); sie verschwindet,
> sobald du in den Optionen Entities auswählst.

## Was wird gelernt?

Bei der Einrichtung (und jederzeit später über **Konfigurieren → Optionen**)
wählst du die **Entities** aus, von denen gelernt werden soll. Ab dann füttert
die Integration **automatisch** jeden Zustandswechsel dieser Entities in die
Engine — kein manuelles Scripting nötig.

> Damit eine Entity gelernt wird, muss der Core sie einem **Raum** zuordnen
> können. Die Integration liest dafür `area`, `device_class`, `unit` und
> `friendly_name` aus den HA-Registries. Entities ohne zuordenbaren Bereich
> werden vom Core ggf. übersprungen — weise ihnen also einen Bereich zu.

## Services

| Service | Zweck |
|---|---|
| `kontinuum_lite.evaluate` | Einen Engine-Tick aus manuellem Payload ausführen (Tests/Debug) |
| `kontinuum_lite.save_brain` | Sofortige Momentaufnahme des Gehirns auf die Platte erzwingen |
| `kontinuum_lite.reset_brain` | **Alles** Gelernte löschen und kalt neu starten (nicht umkehrbar) |

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
(via `requirements: ["kontinuum-core>=0.6.0,<0.7"]` im manifest):
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
