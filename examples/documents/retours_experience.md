# Retours d'expérience sûreté de fonctionnement — BMS

Document d'exemple fictif, créé pour la démonstration de safety-agent.

## REX-2023-07 : Dérive du capteur de courant à froid

Sur le projet BMS Gen1, des essais à -30 °C ont montré une dérive de l'offset du capteur de courant à effet Hall de 2 A.
L'état de charge était surestimé de 4 % après 8 heures. Mesure corrective : calibration de l'offset à chaque ouverture
des contacteurs et ajout d'une mesure redondante par shunt. À reprendre systématiquement dans les nouvelles AMDEC.

## REX-2024-02 : Réveil intempestif par le watchdog

Le watchdog externe n'était pas testé au démarrage. Un défaut de configuration est passé inaperçu jusqu'aux essais véhicule.
Mesure corrective : test de déclenchement du watchdog à chaque démarrage (exigence SSR ajoutée), détection D=2.

## REX-2024-09 : Exigences temporelles non chiffrées

Lors de l'audit ISO 26262 du projet Gen1, l'évaluateur a relevé 14 exigences contenant « rapidement » ou « dès que possible ».
Conséquence : non-conformité mineure et reprise de la spécification. Voir le guide GUI-SDF-012, règles R2 et R4.
