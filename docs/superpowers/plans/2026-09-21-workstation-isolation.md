# Workstation Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separare in modo verificabile PC personale e PC segreteria mantenendo un solo codice condiviso e portando il PC personale su un tunnel dedicato.

**Architecture:** Due profili JSON versionati e senza segreti descrivono le workstation. Un validatore Python e un installer PowerShell eseguono preflight espliciti, preservano la configurazione locale compatibile e rifiutano identità o runtime incoerenti. Tunnel, chiavi DPAPI e deployment restano locali e vengono validati una workstation alla volta.

**Tech Stack:** Python 3.12/3.13, `unittest`, PowerShell 5.1+, Windows Task Scheduler, DPAPI, OpenAI Secure MCP Tunnel, DaVinci Resolve Studio 21.

**Spec:** `docs/superpowers/specs/2026-09-21-workstation-isolation-design.md`

## Global Constraints

- Un solo branch stabile `main`; nessun branch permanente per workstation.
- Un tunnel, una Runtime API key, una config locale e un task Windows per workstation.
- Nessun segreto, blob DPAPI, log, media o progetto Resolve in Git.
- `PC_PERSONALE` usa Python `3.12.10` finché un gate esplicito non approva altro.
- Il Python già validato su `PC_SEGRETERIA` non viene modificato da questo rollout.
- Nessuna write remota finché il routing READ non identifica senza ambiguità `PC_PERSONALE`.
- Gli aggiornamenti Git non eseguono deployment automatici.

## Review Focus

- Profilo personale con tunnel legacy della segreteria: il preflight deve rifiutarlo prima di scrivere file.
- Config locale già appartenente all'altra workstation: l'installer deve fermarsi senza migrare segreti.
- Python assente, alias `WindowsApps` o versione errata: errore leggibile prima di registrare il task.
- File profilo contenente una chiave `sk-`: validazione fallita e nessuna stampa del valore.
- Due chiamate remote parallele dopo la migrazione: entrambe devono comparire nel log personale e descrivere lo stesso Resolve.

---

### Task 1: Consolidare le correzioni di portabilità già validate

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/ARPHE_MCP_BRIDGE_CREATIVE_03.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/resolve_connection.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/requirements.txt`
- Modify: `scripts/windows_bridge/arphe_bridge_runtime.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_entrypoint.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_resolve_connection.py`
- Test: `scripts/windows_bridge/tests/test_runtime.py`
- Remove: `scripts/windows_bridge/run_runtime_py312.cmd`

**Interfaces:**
- Consumes: entrypoint stdio, `bridge.resolve_connection.context()` e config runtime esistenti.
- Produces: avvio indipendente dalla working directory e accesso FusionScript serializzato nella singola istanza.

- [ ] **Step 1: Verificare i test di regressione già scritti**

Eseguire:

```powershell
python -m unittest discover -s scripts/windows_bridge/tests -v
python -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v
```

Risultato atteso: suite runtime verde e suite Creative Bridge con `57` test verdi.

- [ ] **Step 2: Controllare che il lock copra l'intera lettura Resolve**

Il pattern richiesto in `server.py` è:

```python
with RESOLVE_ACCESS_LOCK:
    resolve, manager, project, timeline, config, audit, error = _runtime()
    # Tutte le safe_call della stessa risposta restano dentro il lock.
```

Verificare che `resolve_status` e `get_feature_flags` non rilascino il lock prima di costruire la risposta.

- [ ] **Step 3: Rimuovere il launcher diagnostico specifico del PC**

Non versionare `run_runtime_py312.cmd`: contiene percorsi locali e diagnostica hash temporanea. I percorsi personali saranno espressi dal profilo locale introdotto nel Task 2.

- [ ] **Step 4: Rieseguire entrambe le suite**

Eseguire gli stessi comandi dello Step 1. Risultato atteso: zero failure e zero error.

- [ ] **Step 5: Commit**

```powershell
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03 scripts/windows_bridge/arphe_bridge_runtime.py scripts/windows_bridge/tests/test_runtime.py
git commit -m "fix: stabilize personal Resolve bridge runtime"
```

---

### Task 2: Aggiungere profili workstation validati

**Files:**
- Create: `scripts/windows_bridge/profile_config.py`
- Create: `scripts/windows_bridge/profiles/pc_personale.example.json`
- Create: `scripts/windows_bridge/profiles/pc_segreteria.example.json`
- Create: `scripts/windows_bridge/tests/test_profile_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: percorso a un JSON locale o di esempio.
- Produces: `load_profile(path: Path, *, allow_placeholder_tunnel: bool = False) -> dict[str, object]` e CLI `profile_config.py validate --profile PATH --emit-json`.

- [ ] **Step 1: Scrivere i test fallenti**

```python
def test_profiles_have_distinct_workstations_and_tunnel_names(self):
    personal = load_profile(PROFILES / "pc_personale.example.json", allow_placeholder_tunnel=True)
    office = load_profile(PROFILES / "pc_segreteria.example.json", allow_placeholder_tunnel=True)
    self.assertEqual("PC_PERSONALE", personal["workstation_id"])
    self.assertEqual("PC_SEGRETERIA", office["workstation_id"])
    self.assertNotEqual(personal["tunnel_name"], office["tunnel_name"])

def test_personal_profile_rejects_legacy_office_tunnel(self):
    profile = valid_personal_profile(tunnel_name="ARPHE-RESOLVE-HOME")
    with self.assertRaisesRegex(ValueError, "reserved for PC_SEGRETERIA"):
        validate_profile(profile, allow_placeholder_tunnel=False)

def test_profile_rejects_api_key_material(self):
    profile = valid_personal_profile()
    profile["runtime_api_key"] = "sk-proj-test-value"
    with self.assertRaisesRegex(ValueError, "secret"):
        validate_profile(profile, allow_placeholder_tunnel=False)
```

- [ ] **Step 2: Eseguire il test e osservare il fallimento**

```powershell
python -m unittest scripts.windows_bridge.tests.test_profile_config -v
```

Risultato atteso: FAIL perché `profile_config` non esiste.

- [ ] **Step 3: Implementare schema e validazione minima**

Campi obbligatori:

```python
REQUIRED_FIELDS = {
    "schema_version", "workstation_id", "tunnel_name", "tunnel_id",
    "python_path", "pythonw_path", "python_version", "tunnel_client_path",
    "install_root", "log_dir", "creative_destination",
}
```

La validazione deve:

- ammettere solo `PC_PERSONALE` e `PC_SEGRETERIA`;
- richiedere percorsi Windows assoluti;
- rifiutare `Microsoft\\WindowsApps`;
- rifiutare qualsiasi chiave o valore che inizi con `sk-`;
- richiedere `ARPHE-RESOLVE-PERSONALE` per il personale;
- ammettere `ARPHE-RESOLVE-SEGRETERIA` o il legacy `ARPHE-RESOLVE-HOME` solo per la segreteria;
- ammettere `tunnel_REPLACE_*` soltanto con `allow_placeholder_tunnel=True`.

- [ ] **Step 4: Aggiungere i due esempi e l'esclusione locale**

Il personale dichiara Python `3.12.10` e `C:/Program Files/Python312/python.exe`. Il profilo segreteria conserva il percorso/versione già validato sulla macchina e usa un placeholder esplicito finché non viene verificato localmente.

Aggiungere a `.gitignore`:

```gitignore
scripts/windows_bridge/profiles/*.local.json
```

- [ ] **Step 5: Eseguire i test**

```powershell
python -m unittest scripts.windows_bridge.tests.test_profile_config -v
```

Risultato atteso: tutti i test PASS.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore scripts/windows_bridge/profile_config.py scripts/windows_bridge/profiles scripts/windows_bridge/tests/test_profile_config.py
git commit -m "feat: add isolated workstation deployment profiles"
```

---

### Task 3: Installer guidato dal profilo e preflight non distruttivo

**Files:**
- Create: `scripts/install_workstation_profile.ps1`
- Create: `scripts/windows_bridge/tests/test_profile_installer.py`
- Modify: `scripts/install_personal_pc.ps1`
- Modify: `scripts/windows_bridge/README.md`
- Modify: `docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md`

**Interfaces:**
- Consumes: `-ProfilePath <file.local.json>`, `-PreflightOnly`, `-KeepExistingSecret`.
- Produces: riepilogo normalizzato e, senza `-PreflightOnly`, invocazione controllata degli installer esistenti.

- [ ] **Step 1: Scrivere il test fallente del preflight**

```python
@unittest.skipUnless(os.name == "nt", "PowerShell preflight is Windows-only")
def test_preflight_prints_identity_without_writing_config(self):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(INSTALLER),
         "-ProfilePath", str(self.profile_path), "-PreflightOnly"],
        capture_output=True, text=True, check=False,
    )
    self.assertEqual(0, result.returncode, result.stderr)
    self.assertIn("PC_PERSONALE", result.stdout)
    self.assertIn("ARPHE-RESOLVE-PERSONALE", result.stdout)
    self.assertFalse(self.local_config_path.exists())
```

Aggiungere un secondo test che prepara una config `PC_SEGRETERIA` e verifica exit code non zero quando viene passato il profilo personale.

- [ ] **Step 2: Eseguire i test e osservare il fallimento**

```powershell
python -m unittest scripts.windows_bridge.tests.test_profile_installer -v
```

Risultato atteso: FAIL perché l'installer non esiste.

- [ ] **Step 3: Implementare il preflight**

`install_workstation_profile.ps1` deve:

1. chiamare `profile_config.py validate --emit-json` con il Python dichiarato;
2. controllare esistenza e versione di `python.exe`/`pythonw.exe`;
3. controllare il tunnel client;
4. leggere l'eventuale config locale e rifiutare workstation o tunnel incompatibili;
5. stampare soltanto workstation, versione Python, tunnel name/ID redatto, destinazioni e task;
6. uscire senza scritture con `-PreflightOnly`;
7. senza preflight, chiamare l'installer creativo e `install_autostart.ps1` con percorsi assoluti.

- [ ] **Step 4: Rendere il vecchio installer personale un wrapper esplicito**

`install_personal_pc.ps1` deve richiedere `-ProfilePath` e delegare al nuovo installer. Non deve più ricostruire implicitamente il comando MCP da parametri indipendenti.

- [ ] **Step 5: Eseguire test profilo, installer e runtime**

```powershell
python -m unittest scripts.windows_bridge.tests.test_profile_config -v
python -m unittest scripts.windows_bridge.tests.test_profile_installer -v
python -m unittest discover -s scripts/windows_bridge/tests -v
```

Risultato atteso: zero failure e nessun file locale prodotto dai test preflight.

- [ ] **Step 6: Aggiornare le guide**

Documentare copia `pc_personale.example.json` -> `pc_personale.local.json`, compilazione del nuovo `tunnel_id`, preflight, installazione, rollback e divieto di riutilizzare `ARPHE-RESOLVE-HOME` sul personale.

- [ ] **Step 7: Commit**

```powershell
git add scripts/install_workstation_profile.ps1 scripts/install_personal_pc.ps1 scripts/windows_bridge/tests/test_profile_installer.py scripts/windows_bridge/README.md docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md
git commit -m "feat: install bridge from explicit workstation profile"
```

---

### Task 4: Creare e distribuire il tunnel personale

**Files:**
- Local only: `scripts/windows_bridge/profiles/pc_personale.local.json`
- Local only: `%LOCALAPPDATA%/ARPHE/WindowsBridgeRuntimeV1/bridge_config.json`
- Local only: `%LOCALAPPDATA%/ARPHE/WindowsBridgeRuntimeV1/runtime_api_key.dpapi`

**Interfaces:**
- Consumes: tunnel `ARPHE-RESOLVE-PERSONALE` e nuova Runtime API key Restricted con `Tunnels Read + Use`.
- Produces: runtime personale collegato esclusivamente al nuovo tunnel.

- [ ] **Step 1: Creare il tunnel nel control plane**

Creare `ARPHE-RESOLVE-PERSONALE`, associarlo al workspace ARPHE e annotare il `tunnel_id` restituito. Questa operazione richiede conferma dell'utente al momento della creazione.

- [ ] **Step 2: Creare la Runtime API key personale**

Creare una chiave Restricted dedicata, salvarla direttamente nel DPAPI del PC personale e non inserirla in chat, comandi, file JSON o Git. Questa operazione richiede conferma dell'utente al momento della creazione.

- [ ] **Step 3: Preparare il profilo locale ed eseguire il preflight**

```powershell
Copy-Item .\scripts\windows_bridge\profiles\pc_personale.example.json .\scripts\windows_bridge\profiles\pc_personale.local.json
.\scripts\install_workstation_profile.ps1 -ProfilePath .\scripts\windows_bridge\profiles\pc_personale.local.json -PreflightOnly
```

Risultato atteso: `PC_PERSONALE`, Python `3.12.10`, tunnel `ARPHE-RESOLVE-PERSONALE`, nessuna modifica.

- [ ] **Step 4: Installare preservando l'ambiente segreteria**

Eseguire l'installer sul solo PC personale. Non collegarsi, scrivere o riavviare il PC segreteria.

- [ ] **Step 5: Verificare localmente**

Verificare task personale, `/readyz=ready`, config `PC_PERSONALE`, processo Python 3.12 e collegamento locale a Resolve `21.0.4.5`.

- [ ] **Step 6: Collegare l'app ChatGPT personale e testare READ**

Collegare o creare l'app `ARPHE Resolve Personale` sul nuovo tunnel. Eseguire `ping`, `resolve_status` e `get_feature_flags`, prima in sequenza e poi le ultime due in parallelo. Entrambe le chiamate parallele devono comparire nel log personale.

- [ ] **Step 7: Eseguire safe-write separata**

Solo dopo READ PASS, creare una timeline vuota con nome univoco in un progetto di prova e verificare il ritorno alla timeline originale. Non cancellare timeline e non usare progetti clinici o di produzione.

---

### Task 5: Verifica complessiva e pubblicazione

**Files:**
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md`

**Interfaces:**
- Consumes: risultati reali dei test locali e remoti.
- Produces: stato pubblico riproducibile e commit `main` verificato.

- [ ] **Step 1: Eseguire la suite completa**

```powershell
python -m unittest discover -s scripts/windows_bridge/tests -v
python -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v
git diff --check
```

Risultato atteso: zero failure, zero error e nessun errore whitespace.

- [ ] **Step 2: Eseguire la scansione segreti**

```powershell
git grep -n -E "sk-(proj|admin|svcacct)-[A-Za-z0-9_-]{12,}|CONTROL_PLANE_API_KEY[=:][^[]" -- .
```

Risultato atteso: nessuna chiave o assegnazione reale.

- [ ] **Step 3: Aggiornare lo stato con prove, non intenzioni**

Registrare tunnel personale creato, versione Python effettiva, test READ, test parallelo e safe-write. Lasciare `PENDING` qualsiasi gate non eseguito.

- [ ] **Step 4: Commit e push**

```powershell
git add CURRENT_STATE.md CHANGELOG.md docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md
git commit -m "docs: validate isolated personal Resolve tunnel"
git push origin main
```

- [ ] **Step 5: Verificare il remoto**

Confrontare `git rev-parse HEAD` con `git ls-remote origin refs/heads/main`. I due SHA devono coincidere.
