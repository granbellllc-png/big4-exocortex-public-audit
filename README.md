# Big4 Exocortex — Zero-Trust Public Audit (`UK AI Safety Institute Inspect`, `$0.00`)

[🇮🇹 **Guida Completa in Italiano (anche per Investitori Non Tecnici)**](#-guida-in-italiano--passo-per-passo) &nbsp;|&nbsp; [🇬🇧 **Complete English Guide (Step-by-Step for Investors & Auditors)**](#-english-step-by-step-guide)

> **In one sentence / In una frase:**  
> Anyone — including non-technical investors — can inspect or independently re-run a blind head-to-head benchmark of Big4's **`$0.00` Orthogonal Cycle 5 Architecture** (`big4-ciclo5-free` on a ~€28/month GPU-less server) vs. the **`$0.00` Naked Baseline** (`big4-base-free-nudo`) on a clean **Microsoft/GitHub cloud machine** using the unmodified **UK Government AI Safety Institute `Inspect`** software, with **offline `Ed25519` cryptographic proof** and **zero trade secrets exposed**.

---

## 🇮🇹 Guida in Italiano — Passo per Passo

### 1. Cos'è questo test in 30 secondi (spiegato senza tecnicismi)

Quando un'azienda tech mostra risultati di benchmark eseguiti sui propri computer, un investitore attento si fa sempre una domanda legittima:  
*«Come faccio a essere sicuro che non abbiate scelto voi le domande facili o corretto i voti a mano?»*

Questo repository pubblico elimina completamente questo dubbio grazie a **4 garanzie indipendenti**:

1. **Computer neutrale di proprietà Microsoft / GitHub:** Il test non gira sui nostri server, ma su una macchina virtuale Linux vergine (`ubuntu-latest`) creata al momento da GitHub Actions in un data center Microsoft e distrutta subito dopo.
2. **Esaminatore ufficiale del Governo Britannico (`UK AI Safety Institute`):** Non abbiamo scritto noi il programma che fa le domande o assegna i voti. La macchina virtuale scarica direttamente da PyPI il framework ufficiale intatto [`inspect-ai` / `inspect-evals`](https://ukgovernmentbeis.github.io/inspect_evals/) del **UK AI Safety Institute** insieme ai dataset pubblici ufficiali (`MMLU-Pro`, `TruthfulQA MC1`, `GPQA Diamond`, `HumanEval`).
3. **Confronto alla cieca a costo API zero (`$0.00`):** Nella stessa esecuzione, lo stesso esaminatore britannico sottopone le **stesse identiche domande** (con ordine deterministico `seed=42`, temperatura `0`):
   - Prima al **modello gratuito singolo "Nudo"** (`big4-base-free-nudo`, senza intercettazione né verifica).
   - Subito dopo all'**architettura ortogonale Big4 Exocortex Cycle 5** (`big4-ciclo5-free`), anch'essa a **costo token `$0.00`**, orchestrata da un semplice server cloud senza GPU (~€28/mese).
4. **Firma crittografica verificabile offline (`Ed25519`):** Ogni risposta prodotta dal bridge Big4 include una ricevuta firmata crittograficamente dal server. Al termine del test, uno script aperto controlla matematicamente `5` ricevute dal vivo rispetto alla chiave pubblica fissa salvata in [`public_key_ed25519.pem`](./public_key_ed25519.pem), confermando `cost_usd = 0` e `Zero Data Retention (ZDR)` attivi senza fidarsi di alcun log interno.

---

### 2. Cosa misurano i 4 Esami Ufficiali

| Esame Ufficiale | Cosa testa in parole semplici | Perché conta nel mondo reale |
| :--- | :--- | :--- |
| **`MMLU-Pro`** | Conoscenza universitaria e ragionamento logico su 10 opzioni possibili (diritto, economia, ingegneria, medicina, fisica). | Misura la precisione quando le alternative sbagliate sono molto plausibili. |
| **`TruthfulQA (MC1)`** | Resistenza a bufale diffuse, luoghi comuni e "allucinazioni" dell'AI su domande trabocchetto (scelta singola rigorosa). | Misura l'affidabilità fattuale ed evita risposte sicure ma false. |
| **`GPQA Diamond`** | Problemi scientifici avanzati di livello dottorato (chimica organica, fisica quantistica, biologia molecolare). | È il benchmark più selettivo dove i modelli leggeri di solito crollano. |
| **`HumanEval`** | Scrittura di codice Python reale, compilato ed eseguito sul serio contro test automatici nascosti nella sandbox di GitHub. | Verifica se il software generato funziona davvero invece di sembrare solo ben scritto. |

---

### 3. Opzione 1 — Vedere i Risultati già Certificati in 30 Secondi *(Zero Account, Zero Codice, Solo 3 Click)*

Se vuoi semplicemente verificare l'ultimo test ufficiale eseguito da GitHub, **non serve registrarsi né toccare codice**:

1. **Click 1 — Apri `Actions`:** In alto sotto il titolo di questa pagina clicca sulla scheda **`Actions`** (icona `▶` accanto a *Issues* / *Pull requests*).
2. **Click 2 — Apri l'ultimo test verde `✅`:** Nella lista centrale clicca sull'esecuzione più recente con la spunta verde **`✅`** chiamata **`UK AISI Inspect Public Audit ($0.00)`**.
3. **Click 3 — Leggi la pagella ufficiale:** Scorri leggermente verso il basso fino al riquadro **`Summary`**:
   - Vedi immediatamente la tabella generata dall'arbitro **UK AI Safety Institute** con i punteggi voce per voce (`mmlu_pro`, `truthfulqa`, `gpqa_diamond`, `humaneval`), il punteggio aggregato e la differenza (`Delta (pp)`).
   - Subito sotto vedi l'esito **`Offline Ed25519 Receipt Audit: 5/5 cryptographically verified`**.
   - *(Facoltativo)* In fondo alla pagina, sotto **`Artifacts`**, puoi cliccare su **`uk-aisi-public-audit-summary`** *(richiede login GitHub)* per scaricare i due file JSON ufficiali dell'esecuzione.
   - Cliccando sul nome del job (`UK AISI Inspect Head-to-Head + Offline Ed25519`) puoi espandere e leggere riga per riga l'intero log pubblico grezzo stampato dalla macchina virtuale Microsoft/GitHub.

---

### 4. Opzione 2 — Eseguire un Nuovo Audit Live in Prima Persona in 5 Click dal Browser *(Zero Programmazione, Zero Terminale)*

Vuoi lanciare tu stesso un test nuovo su una tua copia privata controllata al 100% da te, senza scrivere una riga di codice e senza aprire alcun terminale? Segui esattamente questi 5 passaggi:

> **Cosa ti serve prima di iniziare:**
> 1. Un account gratuito su `github.com` (creabile in 60 secondi).
> 2. Le **2 credenziali temporanee da investitore** fornite dal team Big4 (`BIG4_BASE_URL` = indirizzo cifrato del nodo di audit; `BIG4_API_KEY` = chiave dedicata con tetto massimo di chiamate e policy `Zero Data Retention`).  
> *Nota:* Non pubblichiamo le credenziali in chiaro su GitHub unicamente per impedire che bot automatici su Internet saturino il server durante la vostra due diligence. Tutto il codice del test invece è aperto al 100%.

#### Passo 1 — Accedi a GitHub
Apri `github.com` ed effettua il login con il tuo account.

#### Passo 2 — Crea la tua copia indipendente ("Fork")
1. Torna su questa pagina del repository (`big4-exocortex-public-audit`).
2. In alto a destra, clicca il pulsante **`Fork`**.
3. Clicca il pulsante verde **`Create fork`**.
4. In circa 3 secondi avrai una copia identica tutta tua all'indirizzo `github.com/<tuo-nome-utente>/big4-exocortex-public-audit`. Su questa tua copia nessun membro di Big4 può modificare una virgola.

#### Passo 3 — Salva in cassaforte le 2 credenziali nella tua copia ("Actions Secrets")
Resta nella **tua** copia appena creata e inserisci i due parametri protetti:
1. Clicca sulla scheda **`Settings`** (ingranaggio in alto nella barra del tuo repository).
2. Nella colonna di sinistra espandi **`Secrets and variables`** e clicca su **`Actions`**.
3. Clicca il pulsante verde **`New repository secret`** per la **prima** chiave:
   - Nel campo **`Name`** scrivi esattamente: `BIG4_BASE_URL`
   - Nel campo **`Secret`** incolla l'URL fornitoti dal team Big4 (esempio formato: `https://.../v1`).
   - Clicca **`Add secret`**.
4. Clicca di nuovo **`New repository secret`** per la **seconda** chiave:
   - Nel campo **`Name`** scrivi esattamente: `BIG4_API_KEY`
   - Nel campo **`Secret`** incolla la chiave API di audit fornita dal team Big4.
   - Clicca **`Add secret`**.  
   *(Da questo momento GitHub cifra entrambe le chiavi e le maschera automaticamente come `***` in tutti i log).*

#### Passo 4 — Premi "Play" per far partire il test sui server Microsoft/GitHub
1. Clicca in alto sulla scheda **`Actions`** del tuo repository forkato.
2. Se GitHub mostra il messaggio di sicurezza *"Workflows aren't being run on this forked repository"*, clicca sul pulsante verde **`I understand my workflows, go ahead and enable them`**.
3. Nella colonna di sinistra clicca su **`UK AISI Inspect Public Audit ($0.00)`**.
4. Sopra la lista delle esecuzioni (a destra), clicca sul pulsante a tendina **`Run workflow`**.
5. Nel riquadro **`sample_limit`** lascia pure **`15`** *(significa `15` domande alla cieca × `4` esami = **`60` prove** per ciascuno dei due sistemi, `120` valutazioni totali; durata ~8–12 minuti)* oppure inserisci il numero che preferisci.
6. Clicca sul pulsante verde **`Run workflow`**.

#### Passo 5 — Leggi il tuo verdetto certificato
1. Dopo qualche secondo apparirà una riga con un pallino giallo in movimento (`Queued` / `In progress`).
2. Attendi **8–12 minuti** finché il pallino diventa verde **`✅`** *(puoi chiudere la pagina e tornare dopo, gira tutto sul cloud GitHub)*.
3. Clicca sulla riga completata con la spunta **`✅`** → scorri fino a **`Summary`** per leggere la tabella comparativa ufficiale generata dalla tua copia indipendente, la conferma **`5/5` Ed25519** e scaricare da **`Artifacts`** il pacchetto `uk-aisi-public-audit-summary`.

---

### 5. Opzione 3 — Per il Vostro CTO o Advisor Tecnico *(Terminale Mac / Linux)*

Se il vostro team tecnico desidera eseguire gli stessi comandi localmente sulla propria workstation (con il pacchetto ufficiale non modificato del UK AI Safety Institute e verifica offline della chiave pubblica `Ed25519` inclusa in questo repo):

```bash
# 1. Clona il repository pubblico e installa i pacchetti ufficiali da PyPI
git clone https://github.com/granbellllc-png/big4-exocortex-public-audit.git
cd big4-exocortex-public-audit
python3 -m pip install "inspect-ai>=0.3.285" "inspect-evals>=0.29.0" openai cryptography "datasets>=4.8.5"

# 2. Imposta le credenziali temporanee ZDR fornite per l'audit
export BIG4_BASE_URL="<URL fornito per l'audit>"
export BIG4_API_KEY="<chiave API di audit fornita per l'audit>"

# 3. Esegui il confronto alla cieca (Baseline Nudo vs Big4 Cycle 5 a costo $0.00)
for MODEL_ID in "big4-base-free-nudo" "big4-ciclo5-free"; do
  LOG_DIR="logs/${MODEL_ID}"
  mkdir -p "${LOG_DIR}"
  FLAGS="--model openai-api/big4/${MODEL_ID} -M client_timeout=210 --limit 15 --epochs 1 --temperature 0 --max-tokens 8192 --max-connections 2 --no-fail-on-error --score-on-error --retry-on-error=2 --log-dir ${LOG_DIR}"
  inspect eval inspect_evals/mmlu_pro -T shuffle=false --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/truthfulqa -T target=mc1 --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/gpqa_diamond --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/humaneval -T sandbox=local --sample-shuffle=42 ${FLAGS}
done

# 4. Verifica crittografica offline Ed25519 su 5 chiamate reali
python3 scripts/verify_ed25519_receipt.py \
  --public-key public_key_ed25519.pem \
  --live-probe-count 5 \
  --model big4-ciclo5-free \
  --out ed25519_audit_report.json

# 5. Stampa la tabella aggregata finale dai log ufficiali Inspect
python3 scripts/render_step_summary.py \
  --naked-dir logs/big4-base-free-nudo \
  --big4-dir logs/big4-ciclo5-free \
  --ed25519 ed25519_audit_report.json \
  --out public_audit_summary.json
```

---

### 6. Cosa contiene questo repository (e tutela della Proprietà Intellettuale)

| File nel Repository | Ruolo |
| :--- | :--- |
| [`README.md`](./README.md) | Questa guida bilingue (Italiano & Inglese) per investitori e auditor tecnici. |
| [`.github/workflows/uk-aisi-public-audit.yml`](./.github/workflows/uk-aisi-public-audit.yml) | Ricetta trasparente eseguita da GitHub Actions: installa `inspect-ai` / `inspect-evals` da PyPI, maschera le credenziali, esegue i 4 benchmark su entrambi i modelli e verifica le firme. |
| [`public_key_ed25519.pem`](./public_key_ed25519.pem) | Chiave pubblica crittografica `Ed25519` fissa del server di audit, usata per verificare le firme offline senza contattare il server. |
| [`scripts/verify_ed25519_receipt.py`](./scripts/verify_ed25519_receipt.py) | Verificatore crittografico aperto e standalone (controlla SHA-256 della risposta, SHA-256 del payload canonico e firma `Ed25519`). |
| [`scripts/render_step_summary.py`](./scripts/render_step_summary.py) | Estrattore neutrale dei log `.eval` originali prodotti da `Inspect`: nessuna logica di voto personalizzata. |

> **Zero Segreti Esposti:** Nessun codice sorgente proprietario del motore Big4, nessuna matrice o peso interno, nessuna tabella di instradamento, nessun indirizzo IP pubblico e nessuna chiave API privata sono presenti in questo repository.

---
---

## 🇬🇧 English Step-by-Step Guide

### 1. What Is This Audit in 30 Seconds? *(No Technical Jargon)*

Whenever an AI company publishes benchmark numbers run on its own laptops or private servers, careful investors rightly ask:  
*"How do I know you didn't cherry-pick easy questions or adjust the grading script?"*

This public repository removes trust from the equation through **four independent guarantees**:

1. **Neutral Microsoft / GitHub Cloud Runner:** Nothing executes on Big4 hardware. Every run spins up a brand-new, clean Linux virtual machine (`ubuntu-latest`) inside Microsoft/GitHub's cloud and destroys it immediately afterward.
2. **Official UK Government Benchmark Suite (`Inspect`):** Zero custom questions and zero custom grading scripts exist here. The virtual machine installs the unmodified [**UK AI Safety Institute `Inspect`**](https://ukgovernmentbeis.github.io/inspect_evals/) framework (`inspect-ai` + `inspect-evals`) directly from PyPI along with untouched public datasets (`MMLU-Pro`, `TruthfulQA MC1`, `GPQA Diamond`, `HumanEval`).
3. **Blind Head-to-Head at `$0.00` Token Cost:** Inside the exact same run, the UK AISI grader evaluates identical deterministic questions (`sample_shuffle=42`, `temperature=0`) against:
   - **`big4-base-free-nudo`** — the raw single-pass `$0.00` baseline model.
   - **`big4-ciclo5-free`** — Big4's **`$0.00` Orthogonal Cycle 5** verification architecture, orchestrated by a ~€28/month GPU-less cloud server.
4. **Offline Cryptographic Verification (`Ed25519`):** Five live responses are verified offline against the pinned public key in [`public_key_ed25519.pem`](./public_key_ed25519.pem), mathematically proving response integrity, `cost_usd = 0`, and strict `Zero Data Retention (ZDR)`.

---

### 2. What the 4 Official Exams Measure

| Official Exam | Plain-Language Meaning | Why It Matters |
| :--- | :--- | :--- |
| **`MMLU-Pro`** | Multi-subject college & professional reasoning across 10 answer choices (law, finance, engineering, medicine, physics). | Tests real precision when up to 9 distractors look plausible. |
| **`TruthfulQA (MC1)`** | Resistance to widespread myths, urban legends, and hallucinations on trap questions (strict single correct answer). | Measures factual discipline instead of confident-sounding nonsense. |
| **`GPQA Diamond`** | PhD-level science problems (organic chemistry, quantum physics, molecular biology). | The hardest frontier filter where small/free models typically drop sharply. |
| **`HumanEval`** | Writing real Python functions that are compiled and executed against hidden unit tests inside GitHub's local sandbox. | Proves the generated software actually runs and passes real tests. |

---

### 3. Option 1 — Inspect Already-Certified Results in 30 Seconds *(No Account, No Code, 3 Clicks)*

To view the latest certified Microsoft/GitHub audit run right now, **you do not need a GitHub account or any technical skill**:

1. **Click 1 — Open `Actions`:** Near the top of this page, click the **`Actions`** tab (the `▶` play icon next to *Pull requests*).
2. **Click 2 — Open the latest green `✅` run:** Click the top completed workflow run marked with a green checkmark **`✅`** titled **`UK AISI Inspect Public Audit ($0.00)`**.
3. **Click 3 — Read the official scorecard:** Scroll down to **`Summary`**:
   - You will see the complete official **UK AI Safety Institute `Inspect`** table comparing `Naked $0.00 Baseline` vs. `Big4 Exocortex Cycle 5 $0.00` per exam and in aggregate (`Delta (pp)`).
   - Directly below it sits **`Offline Ed25519 Receipt Audit: 5/5 cryptographically verified`**.
   - *(Optional)* Scroll to **`Artifacts`** at the very bottom *(requires signing in to GitHub)* to download **`uk-aisi-public-audit-summary`** containing the raw machine-readable JSON files (`public_audit_summary.json` and `ed25519_audit_report.json`).
   - Clicking the job box (`UK AISI Inspect Head-to-Head + Offline Ed25519`) lets anyone inspect every single command and public log line printed by the runner.

---

### 4. Option 2 — Run Your Own Live Audit From Scratch in 5 Browser Clicks *(Zero Coding, Zero Terminal)*

Want to trigger a fresh live audit inside your **own** independent GitHub copy — completely outside Big4's control — using only your web browser? Follow these 5 exact steps:

> **What you need before starting:**
> 1. A free `github.com` account (takes ~60 seconds to sign up if you don't have one).
> 2. The **2 temporary investor audit credentials** provided by the Big4 team (`BIG4_BASE_URL` = encrypted audit endpoint address; `BIG4_API_KEY` = capped, Zero-Data-Retention audit token).  
> *Why aren't these two values hardcoded publicly?* Strictly to prevent public internet bots from spamming the audit server during your due diligence. 100% of the benchmark code itself is public and open for inspection.

#### Step 1 — Sign in to GitHub
Open `github.com` and log into your personal or firm GitHub account.

#### Step 2 — Create Your Own Isolated Copy ("Fork")
1. Return to this repository page (`big4-exocortex-public-audit`).
2. In the **top-right corner**, click **`Fork`**.
3. Click the green **`Create fork`** button.
4. Within 3 seconds you own a completely independent copy at `github.com/<your-username>/big4-exocortex-public-audit`. Nobody at Big4 can edit a single line of your copy.

#### Step 3 — Store the 2 Audit Credentials in GitHub's Encrypted Vault ("Secrets")
Inside **your** new forked repository:
1. Click **`Settings`** (top navigation bar on the right).
2. In the left sidebar, click **`Secrets and variables`** → **`Actions`**.
3. Click the green **`New repository secret`** button for the **first** secret:
   - **`Name`**: type exactly `BIG4_BASE_URL`
   - **`Secret`**: paste the audit endpoint URL provided by the Big4 team.
   - Click **`Add secret`**.
4. Click **`New repository secret`** again for the **second** secret:
   - **`Name`**: type exactly `BIG4_API_KEY`
   - **`Secret`**: paste the temporary audit API key provided by the Big4 team.
   - Click **`Add secret`**.  
   *(GitHub immediately encrypts both values and automatically masks them as `***` inside every log).*

#### Step 4 — Press "Play" on GitHub Actions
1. Click the **`Actions`** tab near the top of your forked repository.
2. If GitHub shows a security notice saying *"Workflows aren't being run on this forked repository"*, click the green **`I understand my workflows, go ahead and enable them`** button.
3. On the left menu, click **`UK AISI Inspect Public Audit ($0.00)`**.
4. On the right above the workflow table, click the **`Run workflow`** dropdown button.
5. Keep **`sample_limit`** at **`15`** *(this runs `15` blind questions × `4` exams = **`60` questions** per system, `120` evaluations total, taking ~8–12 minutes)*, or enter any number you prefer.
6. Click the green **`Run workflow`** button.

#### Step 5 — View Your Fresh Independent Scorecard
1. Within a few seconds a new row appears with a spinning amber circle (`Queued` / `In progress`).
2. Wait **8–12 minutes** until it turns into a green **`✅`** *(feel free to close the tab and come back — everything runs inside Microsoft/GitHub's cloud)*.
3. Click that completed **`✅`** run → scroll down to **`Summary`** to read your own newly generated UK AISI `Inspect` comparison table, **`5/5` Ed25519 verification**, and download the raw JSON artifact under **`Artifacts`**.

---

### 5. Option 3 — For Your CTO or Technical Due-Diligence Team *(Local Terminal)*

Your engineering team can also run the exact same unmodified UK AI Safety Institute commands and offline `Ed25519` verification directly from any macOS or Linux workstation:

```bash
# 1. Clone this repository and install official unmodified UK AISI Inspect packages
git clone https://github.com/granbellllc-png/big4-exocortex-public-audit.git
cd big4-exocortex-public-audit
python3 -m pip install "inspect-ai>=0.3.285" "inspect-evals>=0.29.0" openai cryptography "datasets>=4.8.5"

# 2. Export the temporary ZDR investor audit credentials
export BIG4_BASE_URL="<audit URL provided by Big4>"
export BIG4_API_KEY="<audit API key provided by Big4>"

# 3. Run the blind head-to-head comparison (Naked $0.00 Baseline vs. Big4 Cycle 5 $0.00)
for MODEL_ID in "big4-base-free-nudo" "big4-ciclo5-free"; do
  LOG_DIR="logs/${MODEL_ID}"
  mkdir -p "${LOG_DIR}"
  FLAGS="--model openai-api/big4/${MODEL_ID} -M client_timeout=210 --limit 15 --epochs 1 --temperature 0 --max-tokens 8192 --max-connections 2 --no-fail-on-error --score-on-error --retry-on-error=2 --log-dir ${LOG_DIR}"
  inspect eval inspect_evals/mmlu_pro -T shuffle=false --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/truthfulqa -T target=mc1 --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/gpqa_diamond --sample-shuffle=42 ${FLAGS}
  inspect eval inspect_evals/humaneval -T sandbox=local --sample-shuffle=42 ${FLAGS}
done

# 4. Run 5 live probes and verify cryptographic Ed25519 receipts completely offline
python3 scripts/verify_ed25519_receipt.py \
  --public-key public_key_ed25519.pem \
  --live-probe-count 5 \
  --model big4-ciclo5-free \
  --out ed25519_audit_report.json

# 5. Render the aggregate audit summary from native Inspect .eval logs
python3 scripts/render_step_summary.py \
  --naked-dir logs/big4-base-free-nudo \
  --big4-dir logs/big4-ciclo5-free \
  --ed25519 ed25519_audit_report.json \
  --out public_audit_summary.json
```

---

### 6. Repository Map & Trade-Secret Hygiene

| File | Purpose |
| :--- | :--- |
| [`README.md`](./README.md) | This bilingual step-by-step guide (Italian & English) for investors and technical auditors. |
| [`.github/workflows/uk-aisi-public-audit.yml`](./.github/workflows/uk-aisi-public-audit.yml) | Reproducible GitHub Actions definition: installs official UK AISI `Inspect`, masks secrets, runs all 4 exams on both arms, and checks cryptographic receipts. |
| [`public_key_ed25519.pem`](./public_key_ed25519.pem) | Pinned `Ed25519` public key used to verify server receipts offline. |
| [`scripts/verify_ed25519_receipt.py`](./scripts/verify_ed25519_receipt.py) | Standalone open cryptographic verifier (SHA-256 response parity, canonical payload parity, and `Ed25519` signature check). |
| [`scripts/render_step_summary.py`](./scripts/render_step_summary.py) | Neutral reader for official `Inspect` `.eval` archives; contains zero custom grading logic. |

> **Zero Trade Secrets Exposed:** No proprietary server source code, internal weights, routing tables, host IPs, or provider credentials live anywhere in this repository.
