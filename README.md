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

| Entität | Typ | Werte |
|---|---|---|
| `sensor.kontinuum_lite_surprise` | numerisch | `0.0` … `1.0` |
| `sensor.kontinuum_lite_learning_state` | kategorisch | `cold_start` / `learning` / `stable` |
| `binary_sensor.kontinuum_lite_anomaly` | on/off | device_class `problem` |

## Service

```yaml
service: kontinuum_lite.evaluate
data:
  payload:
    source: manual
```

Führt einen Engine-Tick aus und feuert `kontinuum_lite_anomaly` auf den
Event-Bus, sobald der Surprise-Wert die Anomalie-Schwelle kreuzt.

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
(via `requirements: ["kontinuum-core>=0.1.2"]` im manifest, installiert die
jeweils aktuellste 0.x):
- Echte Lern-Pipeline (Thalamus → Hippocampus → Predictive Processing → …)
- Lernzustand abgeleitet aus `hippocampus.total_events` und `accuracy`
- Anomalie bei **adaptiver** Surprise-Schwelle (robust: Median + MAD der
  letzten Surprise-Werte, geklemmt auf `0.10`–`0.95`; bis ~30 Beobachtungen
  gilt der Default `0.7`)
- Gelerntes Gehirn wird über Neustarts hinweg persistiert
- Optional: 24 h MetaPlasticity-Loop via HAScheduler-Adapter

Siehe [ROADMAP.md in ha-kontinuum](https://github.com/Chance-Konstruktion/ha-kontinuum/blob/main/ROADMAP.md) für den Gesamtplan der 3-Repo-Architektur.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
