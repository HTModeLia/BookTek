# BookTek — version 1.0.0

Application locale de gestion d'une bibliothèque personnelle, construite avec React, TypeScript, Dexie/IndexedDB et Electron.

## Fonctionnalités

- Collection de livres avec jaquette, auteur, ISBN, pages, résumé, genre, année et emplacement.
- Recherche ISBN multi-sources via Google Books et Open Library.
- Validation des ISBN-10 et ISBN-13 et détection des doublons.
- Recherche textuelle, filtres par genre et emplacement, affichage en grille ou en liste.
- Fiches emprunteurs : nom, e-mail, téléphone et notes.
- Prêts avec emprunteur, date de prêt, date de retour prévue et note facultative.
- Détection automatique des retards selon la date du jour.
- Historique filtrable : tous les prêts, en cours, en retard et rendus.
- Enregistrement du retour et conservation de l'historique.
- Statistiques de collection, prêts, retards, retours et emprunteurs.
- Export et import JSON incluant livres, prêts et fiches emprunteurs.

## Mise à niveau depuis la version 0.2

La base de données passe automatiquement de la version 1 à la version 2 via Dexie.
Les livres et prêts existants sont conservés. Les noms des emprunteurs présents dans les anciens prêts sont transformés en fiches emprunteurs, et les titres des livres sont copiés dans les enregistrements de prêt pour préserver l'historique même si un livre est supprimé plus tard.

Il est recommandé d'exporter une sauvegarde JSON avant toute mise à niveau importante.

## Prérequis

- Node.js 20 ou plus récent
- Windows 10/11 pour la version Electron
- VS Code (facultatif)

## Installation et lancement web

```powershell
npm install
npm run dev
```

## Lancement Windows en développement

```powershell
npm run electron:dev
```

## Génération de l'installateur Windows

```powershell
npm run desktop:build
```

L'installateur est généré dans `release/`.

## Données et sauvegardes

Les données restent locales dans IndexedDB. La version navigateur et la version Windows utilisent des stockages distincts : utiliser l'export/import JSON pour transférer une bibliothèque entre les deux.
La recherche ISBN et le téléchargement des couvertures nécessitent une connexion Internet.

## Version 1.0.0 — première version stable

- Gestion de la collection : fiches livres, recherche ISBN, filtres et statistiques.
- Gestion des emprunteurs, prêts, retours et historique.
- Sauvegardes automatiques et manuelles dans l’application Windows.
- Une sauvegarde automatique par jour ; une sauvegarde manuelle du jour ne bloque pas l’automatique.
- Conservation des 10 dernières sauvegardes locales.
- Restauration avec création préalable d’une sauvegarde de sécurité.
- Import/export JSON conservé pour les transferts entre appareils.

Les sauvegardes automatiques sont disponibles dans l’application Windows Electron. Le mode navigateur conserve l’import/export JSON.
