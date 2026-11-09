# Assistant Sûreté — Guide d'installation sur serveur (DSI)

## 1. Objet

L'Assistant Sûreté aide les ingénieurs sûreté de fonctionnement (ISO 26262) à contrôler et relire les exigences de sécurité et les AMDEC. Il comprend :

- une **page web** (Python / Streamlit) ouverte dans le navigateur, sans installation sur les postes ;
- un **modèle d'IA hébergé en interne** (Ollama). **Aucune donnée ne sort de l'entreprise** : pas d'appel à un service d'IA externe, et aucune statistique d'usage envoyée.

Objectif : un site interne toujours disponible, par exemple `https://assistant-surete.mon-entreprise.local`.

## 2. Architecture

```
 Postes des ingénieurs (navigateur)
          │  HTTPS (443)
          ▼
 Proxy inverse (IIS, nginx…) — certificat interne
          │  HTTP (8501, local au serveur)
          ▼
 ┌──────────────── Serveur Linux + GPU NVIDIA ────────────────┐
 │  Conteneur « assistant » (page web)                         │
 │     │  HTTP interne (11434, non publié)                      │
 │     ▼                                                        │
 │  Conteneur « ollama » (modèle d'IA, sur la carte graphique) │
 │                                                              │
 │  Volumes : /data (journaux)  /docs (documents, lecture seule)│
 └──────────────────────────────────────────────────────────────┘
```

## 3. Prérequis matériels

| Usage | Modèle conseillé | Carte graphique (mémoire) | RAM | CPU | Disque |
|---|---|---|---|---|---|
| Pilote, 1 à 5 utilisateurs | `qwen2.5:14b` | 16 Go et plus | 32 Go | 8 cœurs | 100 Go SSD |
| **Équipe, 5 à 20 utilisateurs (recommandé)** | `qwen2.5:32b` | **24 à 48 Go** | 64 Go | 16 cœurs | 200 Go SSD |
| Plus de 20 utilisateurs | 32B ou plus | 48 Go et plus, ou plusieurs cartes | 64 Go et plus | 16 cœurs et plus | 200 Go SSD |

Carte graphique **NVIDIA** obligatoire pour des temps de réponse de quelques secondes. Pour comparaison, le prototype sur PC portable sans carte graphique répond en 2 à 4 minutes.

## 4. Prérequis logiciels

- Linux 64 bits (Ubuntu Server LTS ou RHEL)
- Pilote NVIDIA et **NVIDIA Container Toolkit**
- **Docker** et **Docker Compose**
- Accès Internet **uniquement pendant l'installation** : images Docker, paquets Python, téléchargement du modèle. En fonctionnement, aucun accès externe n'est nécessaire.

Une alternative sous Windows Server, sans Docker, est décrite au §10.

## 5. Installation (Linux + Docker)

```bash
# 1. Récupérer le projet
# (tant que le code n'est pas fusionné dans la branche principale : ajouter -b claude/safety-agent-prototype)
git clone https://github.com/ndiaye-ghost/agent-system.git assistant-surete
cd assistant-surete/deploiement

# 2. Préparer les dossiers
mkdir -p data documents          # documents : y copier les documents de l'entreprise
sudo chown 1000:1000 data        # l'application tourne avec l'utilisateur non privilégié 1000

# 3. Construire et démarrer
docker compose up -d --build

# 4. Télécharger le modèle (une seule fois, ~20 Go pour qwen2.5:32b)
docker compose exec ollama ollama pull qwen2.5:32b

# 5. Vérifier
docker compose ps                         # les deux services « running », assistant « healthy »
curl http://localhost:8501/_stcore/health # doit répondre « ok »
```

La page est alors disponible sur `http://NOM-DU-SERVEUR:8501`. Configurez ensuite HTTPS (§7) et la connexion avec les comptes de l'entreprise (§6).

## 6. Connexion avec les comptes de l'entreprise (Microsoft Entra ID)

Sans cette étape, la page est ouverte à tout le réseau et chaque utilisateur saisit son nom. **Elle est recommandée** : elle restreint l'accès aux comptes autorisés et enregistre automatiquement le nom de l'utilisateur dans le journal des décisions, ce qui sert la traçabilité ISO 26262.

1. Dans le portail Entra ID : **Inscriptions d'applications → Nouvelle inscription**.
   - URI de redirection (Web) : `https://assistant-surete.mon-entreprise.local/oauth2callback`
2. Créez un **secret client**. Notez l'ID d'application (client), l'ID du locataire (tenant) et le secret.
3. Copiez `secrets.toml.exemple` en `secrets.toml` et remplissez les valeurs.
4. Dans `docker-compose.yml`, décommentez la ligne `./secrets.toml:/app/.streamlit/secrets.toml:ro`.
5. Relancez : `docker compose up -d`.

Pour limiter l'accès à un groupe (par exemple « Sûreté de fonctionnement »), utilisez l'option **« Affectation requise »** de l'application d'entreprise dans Entra ID.

Tout fournisseur OpenID Connect fonctionne (Okta, Keycloak, Google Workspace…).

## 7. HTTPS

Placez un proxy inverse devant le port 8501 (IIS avec ARR, nginx, Traefik…) avec le certificat interne de l'entreprise. Le proxy doit **transmettre les WebSockets** (la page en dépend). Exemple nginx :

```nginx
location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 600s;   # les analyses longues peuvent prendre plusieurs minutes
}
```

Une fois le proxy en place, limitez le port 8501 au serveur lui-même : remplacez `"8501:8501"` par `"127.0.0.1:8501:8501"` dans `docker-compose.yml`.

## 8. Configuration

Variables d'environnement du service `assistant` (`docker-compose.yml`) :

| Variable | Rôle | Valeur par défaut |
|---|---|---|
| `SAFETY_AGENT_MODEL` | Modèle utilisé | `qwen2.5:32b` |
| `SAFETY_AGENT_BASE_URL` | Adresse du serveur de modèle (API compatible OpenAI) | `http://ollama:11434/v1` |
| `SAFETY_AGENT_DOCS` | Dossier des documents de l'entreprise | `/docs` |
| `SAFETY_AGENT_JOURNAL` | Journal des décisions (CSV) | `/data/journal_validations.csv` |
| `SAFETY_AGENT_AUDIT_LOG` | Journal d'audit des échanges avec le modèle (JSONL) | `/data/safety_agent_audit.jsonl` |
| `SAFETY_AGENT_SERVEUR` | Verrouille les réglages du modèle et du dossier pour les utilisateurs | `1` |
| `DOSSIER_DOCUMENTS` | Dossier de l'hôte monté sur `/docs` (variable de Compose) | `./documents` |

Côté `ollama`, `OLLAMA_NUM_PARALLEL` fixe le nombre de questions traitées en même temps (4 par défaut). Au-delà d'une vingtaine d'utilisateurs simultanés, le serveur de modèle peut être remplacé par **vLLM** : il suffit de changer `SAFETY_AGENT_BASE_URL`.

**Documents de l'entreprise** : déposez-les dans le dossier monté sur `/docs` (PDF texte, Word, Excel, CSV, texte). Ils sont relus automatiquement quand un fichier est ajouté ou modifié. Ce dossier peut être un partage réseau monté sur le serveur.

## 9. Sécurité

| Point | Disposition |
|---|---|
| Données | Restent sur le serveur. Le modèle tourne localement, sans appel externe |
| Télémétrie | Désactivée (`gatherUsageStats = false`). Le bouton de publication cloud de Streamlit est masqué |
| Réseau | Seul le port de la page est publié. Le modèle (11434) n'est joignable que par la page |
| Comptes | Connexion Entra ID recommandée (§6) |
| Exécution | Conteneur avec utilisateur non privilégié (uid 1000). Documents montés en lecture seule |
| Fichiers des utilisateurs | Les fichiers déposés sont traités dans la session et stockés temporairement dans le conteneur |
| Système de fichiers | En mode serveur, les utilisateurs ne peuvent pas choisir un dossier du serveur |

**Licence du modèle** : `qwen2.5:14b` et `qwen2.5:32b` sont publiés sous licence Apache 2.0. Vérifiez la licence de tout autre modèle avant usage.

## 10. Alternative : Windows Server sans Docker

1. Installez Python 3.12 et Ollama, puis `ollama pull qwen2.5:32b`.
2. Copiez le projet dans `C:\AssistantSurete`, puis :

```powershell
cd C:\AssistantSurete
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r deploiement\requirements-serveur.txt
```

3. Créez une tâche planifiée qui démarre la page avec le serveur :

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\AssistantSurete\.venv\Scripts\pythonw.exe" `
           -Argument "-m safety_agent web --partage --port 8501" -WorkingDirectory "C:\AssistantSurete"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "AssistantSurete" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest
```

Définissez les variables du §8 en variables d'environnement **système**, par exemple `SAFETY_AGENT_SERVEUR=1`, `SAFETY_AGENT_MODEL=qwen2.5:32b` et `SAFETY_AGENT_DOCS=D:\DocumentsSurete`. Ouvrez le port 8501 dans le pare-feu Windows, ou placez IIS en proxy inverse (§7). La connexion Entra ID se configure avec le fichier `C:\AssistantSurete\.streamlit\secrets.toml` (§6).

## 11. Exploitation

- **Sauvegarde** : le dossier `data/`, qui contient le journal des décisions et le journal d'audit, est la **trace des revues ISO 26262**. Sauvegarde quotidienne recommandée.
- **Supervision** : `GET /_stcore/health` répond `ok`. Le conteneur expose aussi un état de santé Docker.
- **Journaux techniques** : `docker compose logs assistant` et `docker compose logs ollama`.
- **Mise à jour** : `git pull`, puis `docker compose up -d --build`.
- **Gestion de configuration** : pour un projet donné, figez la version de l'outil (commit Git), la version d'Ollama (`OLLAMA_VERSION`) et le modèle utilisé. Le journal d'audit enregistre le modèle et l'empreinte de chaque requête.

## 12. Recette (à cocher après installation)

- [ ] `https://assistant-surete…` s'ouvre depuis un poste du réseau
- [ ] La connexion avec un compte de l'entreprise fonctionne ; le nom apparaît dans la barre latérale
- [ ] Le point est **vert** avec le nom du modèle (pas « Mode démonstration »)
- [ ] Une question dans la conversation reçoit une réponse en moins de 30 secondes
- [ ] Documents : les documents de l'entreprise sont listés et la recherche trouve des extraits
- [ ] Relecture d'une exigence, puis « Valider » : la décision apparaît dans `data/journal_validations.csv`
- [ ] Le port 11434 (modèle) n'est **pas** joignable depuis un poste du réseau

## 13. Contact

Responsable fonctionnel : à compléter. Code source : dépôt `ndiaye-ghost/agent-system`.
