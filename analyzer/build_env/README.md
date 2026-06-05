# analyzer/build_env — środowisko kompilacji P4 dla Tofino #1

Tymczasowa struktura ułatwiająca kompilację bez ręcznego kopiowania plików.

## Struktura

```
build_env/
├── Build_sh        # skrypt cmake → make → make install
├── src/            # skopiowane ../p4/*.p4 (gitignored, generuje się)
│   └── .gitkeep
├── build/          # build artefakty (gitignored)
└── README.md       # ten plik
```

**Single source of truth:** `analyzer/p4/measurement.p4`. Edycje robisz tam,
`Build_sh` synchronizuje do `src/` przed kompilacją.

## Użycie

Na hoście analizatora (10.133.5.4):

```bash
# 1. Ustaw zmienne SDE (jednorazowo, najlepiej w ~/.bashrc):
export SDE=/home/student/sde/bf-sde-9.13.4
export SDE_INSTALL=$SDE/install

# 2. Kompiluj:
cd analyzer/build_env
./Build_sh measurement

# 3. Uruchom switchd:
$SDE/run_switchd.sh -p measurement
```

## Common headers (Barefoot proprietary)

Jeśli kiedyś będziemy potrzebować `common/headers.p4` lub `common/util.p4`
(np. parser TofinoIngressParser z Barefoot examples), skopiuj je z:

```
$SDE/pkgsrc/p4-examples/p4_16_programs/common/
```

do `src/common/`. **Nie commituj ich** — mają nagłówek "Barefoot Confidential".
