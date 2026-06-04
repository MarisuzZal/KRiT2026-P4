# Scenariusze TRex z modulacją natężenia

| Scenariusz | Plik | Typ | Tryb sterowania |
|---|---|---|---|
| Stałe natężenie | `constant.py` | STLProfile | `start -m N%` |
| Liniowy ramp | `ramp.py` | skrypt CLI (STLClient API) | argumenty CLI |
| Skokowe (schodki) | `step.py` | skrypt CLI | argumenty CLI |
| Microburst | `microburst.py` | STLProfile z STLTXMultiBurst | `start -d N` |

## Tryby

### Stałe (`constant.py`)
Klasyczny `STLTXCont` — wzbudzany przez TRex profile API. Natężenie
zadaje się parametrem `-m` przy starcie (`-m 50%`, `-m 10gbps`, itp.).

### Liniowy ramp (`ramp.py`)
Skrypt zewnętrzny: łączy się z TRex serverem przez `STLClient`, startuje
ruch i w pętli wywołuje `port.update(mult=...)` co `duration/steps`
sekund, zmieniając mnożnik liniowo od `--from` do `--to`.

Przykład: ramp 10%→95% w ciągu 30 s, 30 kroków.
```bash
python3 ramp.py --from 10 --to 95 --duration 30 --steps 30
```

### Skokowe / schodki (`step.py`)
Skrypt zewnętrzny: dla każdego poziomu z listy `--levels` ustawia
natężenie przez `port.update(mult=...)` i trzyma przez `--dwell` sekund.

Przykład: trzy poziomy 10%/50%/95% po 60 s każdy.
```bash
python3 step.py --levels 10,50,95 --dwell 60
```

### Microburst (`microburst.py`)
`STLTXMultiBurst` — TRex sam generuje sekwencję raf. Wewnątrz rafy
wysyła z 100% line-rate; między rafami pauza `ibg` mikrosekund.

W profilu domyślnym: 10 raf × 100k pakietów × 50 ms ciszy.

## Repodukowalność wyników

Każdy scenariusz generuje konkretną sygnaturę pomiarową (rozkład $t$,
percentyle 99/99.9/99.99) — kolejność uruchamiania i parametry są
zalogowane w skryptach `runner_*` w katalogu nadrzędnym `trex/`.
