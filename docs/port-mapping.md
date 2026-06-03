# Struktura połączeń: serwer ↔ Tofino #1 ↔ Tofino #2

Środowisko FanInOut. Wersja danych: 2026-05-24.

## Schemat fizyczny

```
                ┌──────────────────────────────────────────┐
                │  SERWER x86 — RHEL 10, TRex v3.08        │
                │                                          │
                │  ┌──────────────┐    ┌──────────────┐    │
                │  │  Karta #1    │    │  Karta #2    │    │
                │  │  E810-CQDA2  │    │  E810-CQDA2  │    │
                │  │  NUMA 0      │    │  NUMA 1      │    │
                │  │  3b:00.x     │    │  86:00.x     │    │
                │  └─┬──┬─────────┘    └─┬──┬─────────┘    │
                │    │  │                │  │              │
                │   B1  B0              A1  A0             │
                └────┼──┼────────────────┼──┼──────────────┘
                     │  │                │  │
                     │  │   4× DAC QSFP28 100G
                     │  │                │  │
                D_P 284 280            184 188
                ┌────┼──┼────────────────┼──┼──────────────┐
                │    │  │                │  │              │
                │  ┌─┴──┴────────────────┴──┴───────────┐  │
                │  │  tabela forward                    │  │
                │  │  16 wpisów fan-in + 4 fan-out      │  │
                │  │  = 20 wpisów                       │  │
                │  └─────────────┬───────┬──────────────┘  │
                │                │       │                 │
                │            D_P 60    D_P 132             │
                │                                          │
                │  Tofino #1 — FanInOut  (Wedge100BF-65X)  │
                └────────────────┼───────┼─────────────────┘
                                 │       │
                                 │   2× DAC QSFP28 100G
                                 │       │
                            Uplink_A   Uplink_B
                                 │       │
                ┌────────────────┼───────┼─────────────────┐
                │                │       │                 │
                │           ┌────┴───────┴────┐            │
                │           │  pass-through   │            │
                │           │  (hairpin)      │            │
                │           └─────────────────┘            │
                │                                          │
                │  Tofino #2 — DUT  (Wedge100BF-32X)       │
                └──────────────────────────────────────────┘
```

## Łącza serwer ↔ Tofino #1  (4 × DAC QSFP28 100 G)

| # | Interfejs serwera | PCI         | NUMA | Rola | TRex port | D_P Tofino #1 | Prefiks obsługiwany |
|--:|-------------------|-------------|:----:|:----:|:---------:|--------------:|---------------------|
| 1 | ens785f0np0       | 0000:3b:00.0 | 0   | B1   | 0         | 284           | 10.3.0.0/16         |
| 2 | ens785f1np1       | 0000:3b:00.1 | 0   | B0   | 1         | 280           | 10.2.0.0/16         |
| 3 | ens801f0np0       | 0000:86:00.0 | 1   | A1   | 2         | 184           | 10.1.0.0/16         |
| 4 | ens801f1np1       | 0000:86:00.1 | 1   | A0   | 3         | 188           | 10.0.0.0/16         |

## Łącza Tofino #1 ↔ Tofino #2 (DUT)  (2 × DAC QSFP28 100 G)

| # | Tofino #1 D_P | Nazwa logiczna | Tofino #2 D_P | Para ruchu (prefiksy) |
|--:|--------------:|----------------|---------------|------------------------|
| 5 | 60            | Uplink_A       | TBD¹         | 10.1.0.0/16  ↔  10.3.0.0/16 |
| 6 | 132           | Uplink_B       | TBD¹         | 10.0.0.0/16  ↔  10.2.0.0/16 |

¹ Numery D_P po stronie Tofino #2 zależą od obsadzenia front-panelu drugiego przełącznika — zweryfikować poleceniem `bfshell> pm show`.

## Logiczne pary cross-card

Ruch zawsze przebiega między kartami serwera (NUMA 0 ↔ NUMA 1). Każda para ma swój uplink — pakiety pary A wchodzą i wychodzą przez Uplink_A, pakiety pary B przez Uplink_B.

| Para | TRex porty | Karty serwera         | Podsieci nadawcze       | Uplink | D_P uplinku |
|:----:|:----------:|-----------------------|--------------------------|--------|------------:|
| A    | 0 ↔ 2      | Karta #1 (B1) ↔ Karta #2 (A1) | 10.3.0.0/16 ↔ 10.1.0.0/16 | Uplink_A | 60        |
| B    | 1 ↔ 3      | Karta #1 (B0) ↔ Karta #2 (A0) | 10.2.0.0/16 ↔ 10.0.0.0/16 | Uplink_B | 132       |

## Podsumowanie sprzętu

- **6 kabli** DAC QSFP28 100 Gbps łącznie:
  - 4 × host  ↔  Tofino #1
  - 2 × Tofino #1  ↔  Tofino #2 (DUT)
- **Serwer**: 2 × Intel Xeon Cascade Lake, 256 GB RAM, 2 × karta E810-CQDA2 (każda 2 × 100 G), magistrala PCIe 3.0 ×16.
- **Tofino #1**: Wedge100BF-65X (Intel Tofino-1) — pełni rolę FanInOut.
- **Tofino #2**: Wedge100BF-32X (Intel Tofino-1) — pełni rolę DUT.
- Każde łącze przenosi ruch **dwukierunkowo**, format RoCEv2: Ethernet / IPv4 / UDP:4791 / BTH / payload.

## Logika trasowania (skrót)

Tofino #1 — pojedyncza tabela `forward`, klucz `(ingress_port exact, dst_addr lpm)`:

- **Fan-in** (16 wpisów = 4 porty hosta × 4 prefiksy) — pakiet jest kierowany do uplinku **wyłącznie na podstawie `dst_ip`**, niezależnie od portu wejściowego. To zapewnia poprawne trasowanie ruchu cross-card.
- **Fan-out** (4 wpisy = 2 uplinki × 2 prefiksy każdy) — pakiet powracający z DUT jest kierowany do docelowego portu hosta zgodnie z `dst_ip`.

Tofino #2 — w konfiguracji bazowej hairpin: `ig_tm_md.ucast_egress_port = ig_intr_md.ingress_port`. Logikę DUT (ECN / INT / custom CC / MTD) wstawia się w to miejsce.

## Weryfikacja po stronie sprzętu

| Co sprawdzić                           | Polecenie                                |
|----------------------------------------|------------------------------------------|
| Numery D_P na obu Tofino               | `bfshell> pm show`                       |
| Stan linków (UP, 100 G)                | `bfshell> pm show`                       |
| Mapowanie front-panel ↔ D_P            | `bfshell> ucli` → `pm.port-info`         |
| Węzeł NUMA portu serwera               | `cat /sys/class/net/<iface>/device/numa_node` |
| Prędkość magistrali PCIe karty E810    | `lspci -vv -s 3b:00.0 \| grep LnkSta`    |

## Pliki powiązane

- `fanInOut_topologia.svg` — kolorowa wersja schematu.
- `fanInOut_dane.json` — pola `mapowanie_portow` i `uplinki` zawierają te same dane strukturalnie.
- `FanInOut_przewodnik_rekonfiguracji.docx` — pełny przewodnik (sekcje 2, 5).
