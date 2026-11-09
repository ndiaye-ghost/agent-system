# Rapport d'analyse sûreté de fonctionnement

Généré le 2026-11-09 08:36 par safety-agent.

> **Avertissement.** Les éléments marqués « IA » sont des propositions produites par un modèle de langage. Ils ne constituent pas une preuve de conformité ISO 26262 et doivent être revus et validés par un ingénieur sûreté de fonctionnement avant toute prise en compte.

## Synthèse

| Indicateur | Valeur |
|---|---|
| Exigences | 11 |
| Lignes AMDEC | 6 |
| Priorité d'action H / M / L | 2 / 2 / 1 |
| Erreurs | 9 |
| Avertissements | 7 |
| Informations | 5 |
| Propositions IA à valider | 0 |

## ERREUR (9)

| Code | Élément | Constat | Source |
|---|---|---|---|
| FMEA-001 | FM-06 | Cotation O manquante. | règle |
| FMEA-010 | FM-01 | Priorité d'action H sans action définie (action ou justification obligatoire). | règle |
| FMEA-010 | FM-04 | Priorité d'action H sans action définie (action ou justification obligatoire). | règle |
| FMEA-020 | FM-04 | Exigence(s) liée(s) inconnue(s) : FSR-77. | règle |
| FMEA-021 | FM-04 | Effet critique pour la sécurité (S≥9) sans exigence de sécurité tracée. | règle |
| FMEA-021 | FM-06 | Effet critique pour la sécurité (S≥9) sans exigence de sécurité tracée. | règle |
| REQ-012 | SW-01 | Exigence orpheline : aucun parent (rupture de traçabilité vers un objectif de sécurité). | règle |
| REQ-013 | TSR-02 | Parent inconnu : FSR-99. | règle |
| REQ-031 | FSR-05 | ASIL A inférieur à l'ASIL du parent SG-02 (ASIL B) sans décomposition déclarée. | règle |

## AVERTISSEMENT (7)

| Code | Élément | Constat | Source |
|---|---|---|---|
| FMEA-004 | FM-04 | Cause de la défaillance non renseignée. | règle |
| FMEA-011 | FM-03 | Priorité d'action M sans action ni justification. | règle |
| REQ-003 | FSR-06 | Méthode de vérification non renseignée (ISO 26262-8 §9). | règle |
| REQ-021 | FSR-06 | Termes ambigus ou non vérifiables : appropriée, rapidement. | règle |
| REQ-023 | FSR-06 | Exigence non atomique : 2 verbes d'obligation, à scinder. | règle |
| REQ-024 | FSR-06 | Contrainte temporelle sans valeur chiffrée (FTTI / temps de réaction ?). | règle |
| TRA-001 | SG-02 | Objectif de sécurité non couvert par l'AMDEC (aucun mode de défaillance relié). | règle |

## INFO (5)

| Code | Élément | Constat | Source |
|---|---|---|---|
| REQ-034 | SG-01 | Décomposition B(C) + A(C) (FSR-03, FSR-04) : justifier l'indépendance (analyse des défaillances de cause commune). | règle |
| TRA-002 | FSR-04 | Exigence terminale non reliée à un mode de défaillance de l'AMDEC. | règle |
| TRA-002 | FSR-05 | Exigence terminale non reliée à un mode de défaillance de l'AMDEC. | règle |
| TRA-002 | FSR-06 | Exigence terminale non reliée à un mode de défaillance de l'AMDEC. | règle |
| TRA-002 | TSR-02 | Exigence terminale non reliée à un mode de défaillance de l'AMDEC. | règle |

## Matrice de traçabilité

| Objectif de sécurité | ASIL | Exigences dérivées | Lignes AMDEC |
|---|---|---|---|
| SG-01 | ASIL C | FSR-01, FSR-02, FSR-03, FSR-04, TSR-01 | FM-01, FM-02 |
| SG-02 | ASIL B | FSR-05, FSR-06 | **aucune** |
