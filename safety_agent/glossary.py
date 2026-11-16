"""Built-in glossary of functional-safety terms.

Written and reviewed by people, not generated: the model uses these definitions
as a reliable reference instead of guessing what an acronym means.
The safety team can edit or extend this file.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Term:
    name: str
    aliases: tuple[str, ...]
    definition: str


GLOSSARY: list[Term] = [
    Term("AMDEC", ("amdec", "fmea", "fmeca", "amde", "dfmea", "pfmea", "amdec conception", "amdec processus"),
         "Analyse des Modes de Défaillance, de leurs Effets et de leur Criticité (en anglais FMEA, Failure Mode "
         "and Effects Analysis). Méthode d'analyse inductive (du bas vers le haut) : pour chaque élément ou "
         "fonction, on liste les modes de défaillance possibles, leurs effets et leurs causes, puis on cote la "
         "gravité (S), l'occurrence (O) et la détection (D), de 1 à 10, pour décider des actions. Selon le manuel "
         "AIAG-VDA (2019), l'analyse suit 7 étapes et la priorité d'action (AP : H, M ou L) remplace l'IPR "
         "(S × O × D). On distingue l'AMDEC conception (DFMEA) et l'AMDEC processus (PFMEA). En ISO 26262, "
         "c'est une des analyses de sécurité inductives. Exemple : pour un capteur de courant, le mode « offset "
         "de mesure » peut avoir pour effet une surcharge de la batterie non détectée."),
    Term("FMEDA", ("fmeda",),
         "Failure Modes, Effects and Diagnostic Analysis. Variante quantitative de l'AMDEC appliquée au matériel : "
         "on attribue un taux de défaillance à chaque mode de défaillance des composants et on évalue la "
         "couverture de diagnostic des mécanismes de sécurité. Elle sert à calculer les métriques matérielles "
         "de l'ISO 26262-5 : SPFM, LFM et PMHF."),
    Term("AMDE / analyse inductive et déductive", ("analyse inductive", "analyse deductive", "inductive", "deductive"),
         "Une analyse inductive part des causes pour remonter aux effets (ex. AMDEC). Une analyse déductive part "
         "d'un événement redouté pour descendre vers ses causes (ex. arbre de défaillance, FTA). L'ISO 26262 "
         "demande des analyses inductives et, pour les ASIL C et D, aussi déductives."),
    Term("FTA", ("fta", "arbre de defaillance", "arbre des defaillances", "arbre de defaillances", "fault tree"),
         "Fault Tree Analysis, ou arbre de défaillance. Analyse déductive : on part d'un événement redouté (par "
         "exemple la violation d'un objectif de sécurité) et on le décompose en causes combinées par des portes "
         "logiques ET / OU, jusqu'aux défaillances de base. Elle identifie les coupes minimales, c'est-à-dire "
         "les combinaisons de défaillances qui suffisent à provoquer l'événement."),
    Term("ISO 26262", ("iso 26262", "iso26262", "securite fonctionnelle", "surete de fonctionnement"),
         "Norme internationale de sécurité fonctionnelle des systèmes électriques et électroniques (E/E) des "
         "véhicules routiers de série. L'édition 2018 comporte 12 parties : gestion, concept, développement "
         "système, matériel et logiciel, production, supports (outils, exigences, configuration), analyses "
         "(ASIL, défaillances dépendantes, analyses de sécurité), semi-conducteurs et motos. Elle couvre les "
         "risques dus aux défaillances des systèmes E/E."),
    Term("ASIL", ("asil", "niveau asil", "automotive safety integrity level"),
         "Automotive Safety Integrity Level. Niveau d'exigence de sécurité, de A (le moins exigeant) à D (le plus "
         "exigeant) ; QM signifie que la gestion de la qualité habituelle suffit. Il est déterminé lors de la "
         "HARA à partir de trois paramètres : la gravité S (S0 à S3), l'exposition E (E0 à E4) et la "
         "contrôlabilité C (C0 à C3). Plus l'ASIL est élevé, plus les méthodes de développement, de "
         "vérification et les métriques matérielles exigées sont strictes."),
    Term("QM", ("qm", "quality management"),
         "Quality Management. Classification d'un risque qui ne requiert pas d'ASIL : le processus qualité "
         "standard de l'entreprise (par exemple IATF 16949) suffit."),
    Term("HARA", ("hara", "analyse des dangers", "analyse de risque", "evaluation des risques"),
         "Hazard Analysis and Risk Assessment, analyse des dangers et évaluation des risques (ISO 26262-3). On "
         "identifie les situations dangereuses que peuvent provoquer les dysfonctionnements de l'élément, on les "
         "classe selon la gravité S, l'exposition E et la contrôlabilité C, on en déduit l'ASIL et on formule "
         "les objectifs de sécurité."),
    Term("Objectif de sécurité", ("objectif de securite", "objectifs de securite", "safety goal", "safety goals", "sg"),
         "Safety goal. Exigence de sécurité de plus haut niveau, issue de la HARA, avec son ASIL. Exemple : « le "
         "système doit empêcher la surcharge des cellules pouvant conduire à un emballement thermique » (ASIL C). "
         "Les exigences de sécurité fonctionnelles (FSR) en sont dérivées."),
    Term("FSR / TSR / HSR / SSR", ("fsr", "tsr", "hsr", "ssr", "exigence de securite fonctionnelle",
                                   "exigence de securite technique", "exigences de securite"),
         "Niveaux d'exigences de sécurité de l'ISO 26262, du plus général au plus détaillé : objectif de "
         "sécurité (SG), puis exigences fonctionnelles (FSR, concept de sécurité fonctionnel), exigences "
         "techniques (TSR, concept de sécurité technique), puis exigences matérielles (HSR) et logicielles (SSR). "
         "Chaque exigence hérite de l'ASIL de son parent, sauf décomposition d'ASIL."),
    Term("Décomposition d'ASIL", ("decomposition d'asil", "decomposition asil", "asil decomposition", "decomposition"),
         "Répartition d'une exigence entre deux éléments suffisamment indépendants, avec des ASIL plus faibles "
         "(ISO 26262-9). Combinaisons autorisées : D = C(D)+A(D), B(D)+B(D) ou D(D)+QM(D) ; C = B(C)+A(C) ou "
         "C(C)+QM(C) ; B = A(B)+A(B) ou B(B)+QM(B) ; A = A(A)+QM(A). La notation B(D) signifie « ASIL B issu "
         "d'une décomposition d'un ASIL D ». L'indépendance doit être démontrée par une analyse des défaillances "
         "dépendantes (DFA)."),
    Term("DFA", ("dfa", "defaillances dependantes", "cause commune", "defaillance de cause commune", "ccf"),
         "Dependent Failure Analysis, analyse des défaillances dépendantes (ISO 26262-9). Elle vérifie qu'une même "
         "cause (alimentation commune, température, logiciel partagé…) ne peut pas faire défaillir en même temps "
         "deux éléments censés être indépendants (défaillance de cause commune), ni qu'une défaillance se "
         "propage de l'un à l'autre (défaillance en cascade)."),
    Term("FTTI", ("ftti", "fault tolerant time interval", "intervalle de temps de tolerance"),
         "Fault Tolerant Time Interval. Durée minimale entre l'apparition d'une défaillance et l'apparition "
         "possible d'un événement dangereux si aucun mécanisme de sécurité n'agit. Le mécanisme de sécurité "
         "doit détecter le défaut (temps de détection, FDTI) et amener le système dans un état sûr (temps de "
         "réaction, FRTI) en moins que le FTTI. Dans une exigence, le FTTI se traduit par un temps de réaction "
         "chiffré, par exemple « ouvrir les contacteurs en moins de 100 ms »."),
    Term("État sûr", ("etat sur", "safe state", "mode degrade"),
         "Mode de fonctionnement sans risque déraisonnable, dans lequel le système est amené après un défaut. "
         "Exemple pour un BMS : contacteurs principaux ouverts et défaut mémorisé."),
    Term("Mécanisme de sécurité", ("mecanisme de securite", "mecanismes de securite", "safety mechanism", "diagnostic"),
         "Fonction ou mesure technique qui détecte, maîtrise ou atténue une défaillance pour atteindre ou "
         "maintenir un état sûr. Exemples : watchdog, contrôle de plausibilité entre deux capteurs, CRC et "
         "compteur de vie sur un message, redondance matérielle."),
    Term("Couverture de diagnostic", ("couverture de diagnostic", "diagnostic coverage", "dc"),
         "Diagnostic coverage. Proportion du taux de défaillance d'un élément détectée ou maîtrisée par un "
         "mécanisme de sécurité, exprimée en pourcentage. Elle intervient dans le calcul des métriques SPFM et LFM."),
    Term("SPFM / LFM / PMHF", ("spfm", "lfm", "pmhf", "metriques materielles", "single point fault metric",
                               "latent fault metric"),
         "Métriques matérielles de l'ISO 26262-5. SPFM (défauts ponctuels) : cibles ≥ 90 % en ASIL B, ≥ 97 % "
         "en C, ≥ 99 % en D. LFM (défauts latents) : ≥ 60 % en B, ≥ 80 % en C, ≥ 90 % en D. PMHF (probabilité "
         "de violation de l'objectif de sécurité due aux défaillances aléatoires) : < 10⁻⁷ par heure (100 FIT) "
         "en ASIL B et C, < 10⁻⁸ par heure (10 FIT) en D."),
    Term("Défaut, erreur, défaillance", ("defaut", "erreur", "defaillance", "fault", "error", "failure"),
         "Vocabulaire de l'ISO 26262 : un défaut (fault) est une condition anormale, par exemple un composant "
         "endommagé ; il peut provoquer une erreur (error), un écart entre une valeur calculée et la valeur "
         "attendue ; l'erreur peut conduire à une défaillance (failure), c'est-à-dire la perte de la capacité "
         "d'un élément à remplir sa fonction."),
    Term("Cotations S, O, D", ("gravite", "occurrence", "detection", "cotation", "cotations", "s o d", "sod"),
         "Dans une AMDEC : S (severity, gravité) mesure la gravité de l'effet, O (occurrence) la probabilité de "
         "la cause compte tenu des mesures de prévention, D (détection) la capacité des mesures de détection à "
         "trouver le défaut avant qu'il n'ait un effet. Chaque cotation va de 1 à 10 ; un D élevé signifie une "
         "détection faible. À ne pas confondre avec les paramètres S, E, C de la HARA."),
    Term("Priorité d'action (AP)", ("priorite d'action", "action priority", "ap", "ipr", "rpn",
                                    "indice de priorite de risque"),
         "Dans le manuel AIAG-VDA (2019), la priorité d'action H (haute), M (moyenne) ou L (basse) est lue dans "
         "une table à partir de S, O et D, en donnant le plus de poids à la gravité. Une ligne en H exige une "
         "action ou une justification. Elle remplace l'IPR (RPN = S × O × D), qui pouvait masquer des gravités "
         "élevées derrière un produit faible."),
    Term("SOTIF", ("sotif", "iso 21448", "securite de la fonction attendue"),
         "Safety Of The Intended Functionality, norme ISO 21448. Elle traite des risques dus aux limites de "
         "performance ou aux insuffisances de spécification d'une fonction, sans défaillance (par exemple un "
         "capteur qui interprète mal une scène). Elle complète l'ISO 26262, qui traite des défaillances."),
    Term("Qualification d'outil", ("qualification d'outil", "tool qualification", "tcl", "confiance dans les outils"),
         "ISO 26262-8 : tout outil logiciel utilisé dans le développement est classé selon l'impact de l'outil "
         "(TI) et la probabilité de détecter ses erreurs (TD), ce qui donne un niveau de confiance TCL1 à TCL3. "
         "En TCL1, aucune qualification n'est requise ; en TCL2 et TCL3, l'outil doit être qualifié."),
]


def _norm(text: str) -> str:
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9' ]+", " ", text)


def find_terms(text: str, limit: int = 3) -> list[Term]:
    """Glossary entries mentioned in the text (longest aliases first, so 'decomposition d'asil' beats 'asil')."""
    padded = f" {_norm(text)} "
    found: list[tuple[int, int, Term]] = []
    for term in GLOSSARY:
        for alias in sorted(term.aliases, key=len, reverse=True):
            pos = padded.find(f" {alias} ")
            if pos >= 0:
                found.append((-len(alias), pos, term))
                break
    found.sort(key=lambda x: (x[0], x[1]))
    out: list[Term] = []
    for _, _, term in found:
        if term not in out:
            out.append(term)
    return out[:limit]


def format_terms(terms: list[Term]) -> str:
    if not terms:
        return "Aucun terme du glossaire ne correspond à la question."
    return "\n\n".join(f"[Glossaire — {t.name}]\n{t.definition}" for t in terms)
