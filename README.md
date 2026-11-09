# safety-agent

Assistant IA pour la sûreté de fonctionnement automobile (**ISO 26262**) : contrôle et relecture de l'**AMDEC** et des **exigences de sécurité**, avec un **modèle de langage hébergé en interne** (aucune donnée ne sort de l'entreprise).

> L'outil **propose**, l'ingénieur sûreté **valide**. Rien n'est modifié automatiquement dans vos fichiers.

## Ce que fait l'outil

| Commande | IA ? | Rôle |
|---|---|---|
| `check` | Non | Contrôles automatiques et reproductibles : ASIL, décomposition (ISO 26262-9 §5), héritage, traçabilité, formulation, cotations S/O/D, priorité d'action AIAG-VDA. Utilisable en intégration continue. |
| `review` | Oui | Relecture de chaque exigence selon les critères de l'ISO 26262-8 §6.4 (non ambiguë, atomique, vérifiable…) et proposition de reformulation. |
| `suggest` | Oui | Propose des modes de défaillance pour un élément (mots-guides), avec effets, causes et cotations à valider. Export CSV au format AMDEC. |
| `chat` | Oui | Agent conversationnel qui interroge vos données avec des outils (« Quels modes S≥9 ne sont pas couverts ? »). |

### Contrôles automatiques (`check`)

- **Exigences** : ASIL manquant ou illisible, exigence orpheline, parent inconnu, cycle, ASIL inférieur au parent sans décomposition, décomposition non autorisée (ex. B(D)+A(D)), termes ambigus (« rapidement », « approprié »…), exigence non atomique, contrainte temporelle non chiffrée, méthode de vérification absente.
- **AMDEC** : cotations manquantes ou hors échelle, priorité d'action H/M sans action, S≥9 sans détection, S≥9 sans exigence tracée, lien vers une exigence inconnue.
- **Traçabilité** : objectif de sécurité non couvert par l'AMDEC, matrice SG → exigences → lignes AMDEC.

## Démarrage rapide avec VS Code et les notebooks

1. Décompressez le dossier et ouvrez-le dans VS Code (**Fichier → Ouvrir le dossier**).
2. Acceptez les extensions recommandées (Python, Jupyter).
3. Créez l'environnement Python dans le terminal de VS Code :

   Windows (PowerShell) :
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   Linux / macOS :
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Ouvrez `notebooks/00_installation.ipynb`, choisissez le noyau **.venv** en haut à droite, puis **Exécuter tout**.

| Notebook | Contenu | IA |
|---|---|---|
| `00_installation.ipynb` | Vérification de l'installation et du serveur du modèle | — |
| `01_controles_automatiques.ipynb` | Contrôles des exigences et de l'AMDEC, matrice de traçabilité, rapport | Non |
| `02_relecture_exigences_ia.ipynb` | Relecture des exigences selon l'ISO 26262-8 §6 | Oui |
| `03_suggestion_modes_defaillance.ipynb` | Propositions de modes de défaillance, export CSV | Oui |
| `04_agent_conversationnel.ipynb` | Questions libres à l'agent | Oui |

**Sans serveur de modèle**, les notebooks 02 à 04 passent automatiquement en **mode démo** : réponses simulées, clairement marquées `[DÉMO]`, pour découvrir le fonctionnement. Pour de vraies analyses, installez Ollama (voir plus bas).

## Installation (ligne de commande)

Python 3.10 ou plus. Aucune dépendance obligatoire (`openpyxl` seulement pour lire l'Excel).

```bash
pip install -e ".[excel]"
```

## Modèle hébergé

L'outil parle l'API « compatible OpenAI » proposée par **Ollama**, **vLLM**, llama.cpp, LM Studio ou TGI.

Le plus simple, avec Ollama sur un serveur interne doté d'un GPU :

```bash
ollama pull qwen2.5:14b
```

```bash
export SAFETY_AGENT_BASE_URL=http://serveur-ia.interne:11434/v1
export SAFETY_AGENT_MODEL=qwen2.5:14b
```

Pour la production avec plusieurs utilisateurs, préférez **vLLM**. Ordre de grandeur des besoins (quantification 4 bits) :

| Taille du modèle | Mémoire GPU | Usage |
|---|---|---|
| 7–8 B | ~6 Go | Tests, `check` + `suggest` simples |
| 14 B | ~10 Go | Bon compromis, outils fiables |
| 32 B | ~20–24 Go | Recommandé pour `review` et `chat` |
| 70 B | ~40–48 Go | Meilleure qualité d'analyse |

Le mode `chat` demande un modèle qui gère l'appel d'outils (Qwen 2.5 ou plus récent, Llama 3.1+, Mistral Small…). Comparez plusieurs modèles sur vos propres données avant de choisir.

## Utilisation

```bash
safety-agent check --reqs examples/bms_exigences.csv --fmea examples/bms_amdec.csv --out rapport.md
```

```bash
safety-agent review --reqs examples/bms_exigences.csv --ids FSR-06,TSR-02 --out relecture.md
```

```bash
safety-agent suggest --item "Capteur de courant pack" --function "Mesurer le courant batterie" --context "BMS 400 V, véhicule électrique" --fmea examples/bms_amdec.csv --csv propositions.csv
```

```bash
safety-agent chat --reqs examples/bms_exigences.csv --fmea examples/bms_amdec.csv
```

En intégration continue, `check --fail-on error` renvoie le code 1 s'il y a des erreurs.

## Format des fichiers

CSV (séparateur `,` ou `;`) ou Excel. Les en-têtes sont reconnus en français ou en anglais, sans tenir compte des accents ni des majuscules.

**Exigences** : `ID`, `Texte`, `Niveau` (SG, FSR, TSR, HSR, SSR), `ASIL` (`C`, `ASIL B(D)`, `QM`…), `Parent` (plusieurs : séparés par des virgules), `Méthode de vérification`, `Statut`.

**AMDEC** : `ID`, `Élément`, `Fonction`, `Mode de défaillance`, `Effet`, `Cause`, `S`, `O`, `D`, `Prévention`, `Mesures de détection`, `Actions`, `Exigences`.

> Dans un CSV séparé par `;`, séparez plusieurs identifiants d'une même cellule par des **virgules**.

Les exemples dans `examples/` (BMS de véhicule électrique) contiennent des erreurs volontaires pour la démonstration.

## Points de vigilance ISO 26262

1. **Qualification d'outil (ISO 26262-8 §11).** Si les sorties de l'outil servent de preuve sans revue humaine, il faut l'évaluer (TI/TD → TCL) et peut-être le qualifier. L'approche retenue ici est de garder une **vérification humaine systématique**, ce qui place l'IA en assistance (détection d'erreurs élevée par la revue) et réduit l'exigence de qualification. Faites valider ce raisonnement par votre responsable sûreté et votre évaluateur.
2. **Séparation règles / IA.** Les contrôles `check` sont déterministes et testés. Les éléments produits par l'IA sont marqués « IA » et « À VALIDER » dans les rapports.
3. **Traçabilité des échanges.** Chaque requête au modèle et sa réponse sont enregistrées dans `safety_agent_audit.jsonl` (horodatage, modèle, empreinte SHA-256). Température à 0 pour limiter la variabilité.
4. **Confidentialité.** Le modèle tourne chez vous. Vérifiez que le serveur d'inférence n'envoie aucune télémétrie.
5. **Table de priorité d'action.** La table AIAG-VDA codée dans `safety_agent/checks/action_priority.py` doit être vérifiée contre votre exemplaire du manuel (certains constructeurs ont leur variante).

## Architecture

```
safety_agent/
  models.py         Exigences, lignes AMDEC, constats, propositions
  loaders.py        Import CSV / Excel, en-têtes FR/EN
  checks/           Contrôles déterministes (exigences, AMDEC, traçabilité, priorité d'action)
  llm.py            Client du modèle hébergé + journal d'audit
  prompts.py        Tous les prompts (à relire et versionner par l'équipe sûreté)
  ai.py             Relecture d'exigences, suggestion de modes de défaillance
  agent.py          Agent à outils (lecture seule + enregistrement de propositions)
  report.py         Rapport Markdown, export CSV
  cli.py            Ligne de commande
  notebook.py       Tableaux pandas et choix du modèle pour les notebooks
  demo.py           Faux modèle (réponses simulées) pour le mode démo
notebooks/          Notebooks Jupyter 00 à 04
```

## Tests

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

## Pistes d'évolution

- Import ReqIF (DOORS, Polarion) et export vers votre outil AMDEC (APIS IQ, Medini…).
- Base documentaire (RAG) sur vos procédures internes et vos AMDEC passées.
- Analyse FMEDA (métriques SPFM / LFM / PMHF) et arbres de défaillance.
- Interface web pour valider ou rejeter les propositions une par une.
- Jeu d'évaluation interne pour mesurer la qualité de chaque modèle sur vos données.
