# Non-validated scripts archive

Questo archivio conserva gli script originali presenti nelle cartelle `scripts/partial/` e `scripts/experiments/` dello snapshot iniziale.

È suddiviso in 5 parti Base64 per compatibilità con il connettore GitHub:

- `part00.b64` — 7000 byte
- `part01.b64` — 7000 byte
- `part02.b64` — 7000 byte
- `part03.b64` — 7000 byte
- `part04.b64` — 6640 byte

Totale Base64: **34640 byte**.

## Ricostruzione su Linux/macOS/Git Bash

```bash
cat part00.b64 part01.b64 part02.b64 part03.b64 part04.b64 > nonvalidated_scripts.tar.gz.b64
base64 -d nonvalidated_scripts.tar.gz.b64 > nonvalidated_scripts.tar.gz
tar -xzf nonvalidated_scripts.tar.gz
```

## Checksum

SHA-256 del Base64 concatenato:

`48c3a7c33ff8a4ae32598e5c73a00e824f4809bdd4c8770c49122dc0b367f204`

SHA-256 del `tar.gz` ricostruito:

`25761391a1c07511c6366f837d73e45cfd2699c9a9a9abef9dc0d06c7ff6db1f`

Gli script contenuti qui **non vanno considerati primitive validate**. Per uso operativo consultare prima `../../CURRENT_STATE.md` e `../../scripts/validated/`.
