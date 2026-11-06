# Historique des versions

Les sections de ce fichier servent de notes de version : `tools/release.py` publie la section correspondant à la version en cours comme description de la release GitHub, affichée aussi dans l'application au moment d'installer une mise à jour.

## [1.1.0] - 2026-11-06

### Ajouts
- **Mise à jour automatique** depuis les releases GitHub :
  - vérification en arrière-plan au démarrage puis toutes les 6 heures ;
  - téléchargement automatique de la nouvelle version, avec contrôle de son empreinte SHA-256 ;
  - installation au démarrage suivant, ou immédiatement avec le bouton **Mettre à jour**.
- Menu **Aide** : *Rechercher une mise à jour* et *À propos de BookTek*.
- Documentation utilisateur et technique dans le dossier `docs/`.

### Note
La version 1.0.0 ne contenait pas encore la mise à jour automatique : téléchargez la version 1.1.0 une fois manuellement depuis la page des releases. Les versions suivantes s'installeront d'elles-mêmes.

## [1.0.0] - 2026-11-06

Première version.

- Scan d'ISBN par douchette ou clavier, avec trois modes : automatique, ajout rapide, retour rapide.
- Gestion des prêts : emprunteur, date de retour prévue, retards, historique.
- Recherche des fiches en ligne : BnF (prioritaire pour les livres français), Google Books, Open Library.
- Import des collections Book Collector (`.bkc`) et export CSV.
