# Guide d'utilisation de BookTek

## Sommaire

- [Installation](#installation)
- [La fenêtre principale](#la-fenêtre-principale)
- [Scanner un livre](#scanner-un-livre)
- [Ajouter des livres](#ajouter-des-livres)
- [Prêter et récupérer un livre](#prêter-et-récupérer-un-livre)
- [Rechercher, modifier, supprimer](#rechercher-modifier-supprimer)
- [Importer une collection Book Collector](#importer-une-collection-book-collector)
- [Exporter vers Excel](#exporter-vers-excel)
- [Mises à jour](#mises-à-jour)
- [Sauvegarder ses données](#sauvegarder-ses-données)
- [Dépannage](#dépannage)

## Installation

1. Téléchargez `BookTek.exe` depuis la [page des releases](https://github.com/HTModeLia/BookTek/releases/latest).
2. Créez un dossier personnel, par exemple `Documents\BookTek`, et placez-y le fichier.
3. Double-cliquez sur `BookTek.exe`.

Au premier lancement, Windows peut afficher « Windows a protégé votre ordinateur » : l'exécutable n'est pas signé numériquement. Cliquez sur **Informations complémentaires** puis **Exécuter quand même**.

> Évitez de placer BookTek dans `C:\Program Files` : ce dossier est protégé en écriture. Dans ce cas, la base est enregistrée dans `%APPDATA%\BookTek`, et la mise à jour automatique ne peut pas remplacer l'exécutable.

## La fenêtre principale

- **En haut** : le champ **ISBN** où arrivent les codes scannés, et le choix du **mode de scan**. Un bouton **Mettre à jour** apparaît à droite quand une nouvelle version est prête.
- **La ligne de statut**, en couleur, sous le champ ISBN, indique le résultat de chaque action :
  - vert : action réussie ;
  - orange : avertissement ;
  - rouge, avec un bip : erreur, par exemple un code invalide.
- **Trois onglets** :
  - **Bibliothèque** : tous les livres avec leur statut (disponible ou prêté à quelqu'un) ;
  - **Prêts en cours** : les livres sortis, triés par date de retour, les retards en rouge ;
  - **Historique des prêts** : tous les prêts passés et en cours.
- **En bas** : le nombre de livres, de prêts en cours et de retards.

Appuyez sur **F2** à tout moment pour remettre le curseur dans le champ ISBN.

## Scanner un livre

Une douchette code-barres USB fonctionne comme un clavier : elle « tape » le code puis la touche Entrée. Il suffit que le curseur soit dans le champ ISBN. Sans douchette, tapez l'ISBN au clavier (avec ou sans tirets) et appuyez sur Entrée.

BookTek accepte les ISBN à 10 et 13 chiffres et vérifie leur clé de contrôle : un code mal lu ou mal tapé est refusé avec un bip.

Le **mode de scan** détermine ce qui se passe :

| Mode | Livre déjà dans la bibliothèque | Livre inconnu |
|---|---|---|
| **Automatique** | Ouvre sa fiche avec les boutons **Prêter** ou **Enregistrer le retour** | Recherche ses informations en ligne et ouvre la fiche pré-remplie pour validation |
| **Ajout rapide** | Simple avertissement « déjà dans la bibliothèque » | Enregistré directement, sans fenêtre |
| **Retour rapide** | Le retour est enregistré immédiatement | Erreur |

Dans la fiche d'un livre, le bouton principal est présélectionné : appuyez sur la **barre d'espace** pour le déclencher. La touche Entrée ne fait volontairement rien : un scan fait par erreur pendant que la fiche est ouverte ne déclenche aucune action.

## Ajouter des livres

### Un livre à la fois (mode Automatique)

1. Scannez le livre.
2. BookTek recherche le titre, les auteurs, l'éditeur, l'année et le nombre de pages dans les catalogues en ligne.
3. La fiche s'ouvre pré-remplie. Complétez si besoin l'**emplacement** (par exemple « Salon, étagère 2 ») et les **notes**, puis cliquez sur **Enregistrer** ou appuyez sur Entrée.

Si le livre est introuvable en ligne, la fiche s'ouvre avec seulement l'ISBN : saisissez au moins le titre.

### Toute une étagère (mode Ajout rapide)

Choisissez **Ajout rapide** puis scannez les livres les uns après les autres, sans toucher à la souris. Chaque livre trouvé en ligne est enregistré aussitôt. Si un livre est introuvable, sa fiche s'ouvre pour une saisie manuelle.

### Un livre sans ISBN

Dans l'onglet **Bibliothèque**, cliquez sur **Ajouter manuellement…**. L'ISBN est facultatif, seul le titre est obligatoire.

## Prêter et récupérer un livre

### Prêter

1. En mode **Automatique**, scannez le livre. Vous pouvez aussi double-cliquer dessus dans l'onglet Bibliothèque.
2. Cliquez sur **Prêter…**, ou appuyez sur Espace.
3. Saisissez le nom de l'emprunteur. Les noms déjà utilisés sont proposés dans la liste.
4. La date de retour prévue est fixée à 21 jours par défaut. Modifiez-la au format `JJ/MM/AAAA`, ou videz le champ pour un prêt sans échéance.
5. Validez avec **Prêter** ou Entrée.

Un livre déjà prêté ne peut pas être prêté une seconde fois avant son retour.

### Récupérer

- **Un livre** : scannez-le en mode Automatique puis cliquez sur **Enregistrer le retour**.
- **Plusieurs livres** : passez en mode **Retour rapide** et scannez-les à la suite.
- **Sans scanner** : onglet **Prêts en cours**, sélectionnez le prêt puis cliquez sur **Enregistrer le retour**.

### Suivre les retards

L'onglet **Prêts en cours** affiche en rouge les prêts dont la date de retour est dépassée, avec le nombre de jours de retard. Le nombre de retards figure aussi en bas de la fenêtre.

## Rechercher, modifier, supprimer

- **Rechercher** : dans l'onglet Bibliothèque, tapez dans le champ **Rechercher**. La recherche porte sur le titre, les auteurs, l'ISBN, l'emplacement et le nom de l'emprunteur.
- **Trier** : cliquez sur l'en-tête d'une colonne ; un second clic inverse l'ordre.
- **Modifier** : sélectionnez un livre puis cliquez sur **Modifier…**.
- **Supprimer** : sélectionnez un livre puis cliquez sur **Supprimer**. Un livre prêté ne peut pas être supprimé avant son retour. La suppression efface aussi l'historique de ses prêts.

## Importer une collection Book Collector

Si vos livres sont déjà catalogués dans *Book Collector* (Collectorz.com) :

1. Menu **Fichier > Importer une collection Book Collector (.bkc)…**, puis choisissez le fichier `.bkc`.
2. BookTek importe l'**ISBN** et le **titre** de chaque livre. Les livres dont l'ISBN est déjà présent sont ignorés : vous pouvez relancer l'import sans créer de doublons.
3. Le format `.bkc` ne permet pas de récupérer les auteurs. BookTek propose donc de **compléter les fiches via Internet** : acceptez. La progression s'affiche dans la ligne de statut et vous pouvez continuer à travailler pendant ce temps.

À tout moment, **Fichier > Compléter les fiches via Internet** complète les livres qui n'ont pas encore d'auteur ou d'éditeur. Seuls les champs vides sont remplis : vos saisies ne sont jamais écrasées.

Les couvertures de Book Collector ne sont pas importées.

> Si un livre importé n'est pas retrouvé quand vous le scannez, son ISBN est probablement faux dans le fichier d'origine. Corrigez-le avec **Modifier…**.

## Exporter vers Excel

Menu **Fichier > Exporter en CSV…**. Le fichier s'ouvre directement dans Excel. Il contient tous les livres, avec l'emprunteur et la date de retour prévue de ceux qui sont prêtés.

## Mises à jour

BookTek se met à jour tout seul depuis la page GitHub du projet :

1. Pendant que vous l'utilisez, il vérifie discrètement s'il existe une nouvelle version : au démarrage, puis toutes les 6 heures.
2. Si c'est le cas, il la télécharge en arrière-plan et affiche le bouton **⬆ Mettre à jour vers x.y.z**.
3. Deux possibilités :
   - cliquez sur ce bouton : les nouveautés s'affichent, puis BookTek redémarre dans la nouvelle version ;
   - ou ne faites rien : la mise à jour sera installée automatiquement au prochain lancement.

Pour vérifier sans attendre : menu **Aide > Rechercher une mise à jour**. Le numéro de version actuel est affiché dans le titre de la fenêtre et dans **Aide > À propos**.

Vos livres et vos prêts ne sont pas touchés par une mise à jour. Pour plus de détails, voir [Mises à jour](mises-a-jour.md).

## Sauvegarder ses données

Toutes les données sont dans un seul fichier, `booktek.db`. Son emplacement est indiqué dans **Aide > À propos** : en général le dossier de `BookTek.exe`.

- **Sauvegarder** : fermez BookTek, puis copiez `booktek.db` (clé USB, cloud…).
- **Restaurer** : fermez BookTek, puis remplacez `booktek.db` par la copie.
- **Changer d'ordinateur** : copiez `BookTek.exe` et `booktek.db` dans le même dossier sur le nouvel ordinateur.

## Dépannage

| Problème | Solution |
|---|---|
| Les scans n'apparaissent nulle part | Appuyez sur **F2** pour remettre le curseur dans le champ ISBN. |
| « n'est pas un ISBN valide » | Le code a été mal lu : scannez à nouveau. Certains livres portent deux codes-barres ; scannez celui qui commence par 978 ou 979. |
| Livre introuvable en ligne | Fréquent pour les livres anciens ou les éditions de club. Saisissez le titre à la main. |
| Livre importé non reconnu au scan | Son ISBN est faux dans le fichier `.bkc` : corrigez-le avec **Modifier…**. |
| Pas de bouton « Mettre à jour » | Vérifiez la connexion Internet, puis **Aide > Rechercher une mise à jour**. Si BookTek est dans un dossier protégé comme Program Files, déplacez-le dans un dossier personnel. |
| Avertissement Windows au lancement | Normal pour un logiciel non signé : **Informations complémentaires > Exécuter quand même**. |
