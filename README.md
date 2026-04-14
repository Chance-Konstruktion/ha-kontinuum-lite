# KONTINUUM Lite

> Headless, lightweight variant of [KONTINUUM](https://github.com/Chance-Konstruktion/ha-kontinuum) — no UI, no brand assets, just the learning substrate.

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

**Phase 0** — das Engine-Modul ist ein Stub mit Platzhalter-Werten. Die echte
Lern-Engine (`kontinuum-core`) wird in Phase 1 vendored oder über PyPI
nachgezogen. Siehe [ROADMAP.md in ha-kontinuum](https://github.com/Chance-Konstruktion/ha-kontinuum/blob/main/ROADMAP.md).

## Lizenz

MIT — siehe [LICENSE](LICENSE).
