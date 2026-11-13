# Historique des versions

Les sections de ce fichier servent de notes de version : `tools/release.py` publie la section correspondant à la version en cours comme description de la release GitHub, affichée aussi dans l'application au moment d'installer une mise à jour.

## [1.14.0] - 2026-11-13

### Modifications
- Le menu **Outils** reste en bas de la fenêtre.
- Fenêtre redimensionnable : la liste des livres et la fiche défilent chacune de leur côté. En fenêtre étroite, la barre du bas (rubriques et Outils) reste visible.

### Corrections
- En grands caractères, la fenêtre ne déborde plus à droite.

## [1.13.0] - 2026-11-13

### Modifications
- Les actions de la barre latérale (importer, compléter via Internet, exporter, thème sombre, grands caractères) sont regroupées dans un menu **Outils**.
- L'écran **Sauvegardes** s'ouvre désormais depuis **Outils > Sauvegardes…**.

## [1.12.0] - 2026-11-13

### Ajouts
- **Sauvegardes** : nouvel écran (menu **Sauvegardes**) qui garde des copies de votre bibliothèque, livres, prêts, emprunteurs et jaquettes. Une sauvegarde est créée automatiquement au lancement, au maximum une fois par jour. Vous pouvez aussi en créer une à tout moment avec **Créer une sauvegarde**.
- **Restaurer** une sauvegarde depuis la liste. BookTek fait d'abord une copie de sécurité de vos données actuelles, au cas où.

### Modifications
- Les 10 dernières sauvegardes sont conservées ; les plus anciennes sont supprimées automatiquement.

## [1.11.0] - 2026-11-11

### Modifications
- **Choisir une jaquette** : la fenêtre rappelle le livre concerné (titre - auteur), et les boutons **−** et **+** agrandissent les jaquettes pour mieux les comparer. Quand elles sont grandes, la liste défile.

## [1.10.0] - 2026-11-11

### Ajouts
- **Liste par auteur, année ou genre à gauche** : à cocher dans le menu *Affichage*. Un panneau à gauche de la bibliothèque liste les auteurs (triés par nom de famille), les années ou les genres, chacun avec son nombre de livres. Un clic sur une ligne n'affiche que les livres correspondants, en *Liste* comme en *Miniatures* ; « (Tous les livres) » les réaffiche tous.
- **Actualiser les informations** d'un livre : bouton dans *Modifier…*, qui récupère en ligne titre, auteurs, éditeur, année, genre, pages et résumé. Vous vérifiez avant d'enregistrer ; l'emplacement et les notes ne changent pas.
- **Clic droit sur un livre**, en Liste comme en Miniatures : *Actualiser la jaquette…* (vous choisissez parmi les jaquettes trouvées), *Actualiser les informations…* (les changements s'affichent et ne sont enregistrés qu'après confirmation) et *Modifier…*.

## [1.9.0] - 2026-11-11

### Ajouts
- **Importer une liste d'ISBN** : menu *Fichier > Importer une liste d'ISBN (texte ou CSV)…*. BookTek ajoute chaque livre de la liste (un par ligne ; dans un tableau, le premier ISBN de la ligne est retenu), ignore ceux déjà présents, puis propose de compléter les fiches via Internet : titre, auteur, éditeur, résumé et couverture.

## [1.8.0] - 2026-11-11

### Ajouts
- **Rechercher une jaquette** : dans *Modifier…*, un bouton cherche les jaquettes en ligne (ISBN, puis titre et auteur). Si plusieurs sont trouvées, elles s'affichent côte à côte pour choisir celle de votre édition.

### Modifications
- Les **sources des données** (API utilisées) sont maintenant présentées dans un tableau, dans *Aide > À propos de BookTek*, au lieu d'un sous-menu.

## [1.7.0] - 2026-11-11

### Ajouts
- **Fiches plus complètes à l'ajout d'un livre** : les trois catalogues (BnF, Google Books, Open Library) sont interrogés en même temps et leurs informations sont combinées. Le résumé retenu est le plus complet, et une couverture est cherchée dans chaque catalogue tour à tour. Les résumés de Google Books, souvent absents jusqu'ici, sont maintenant récupérés.
- **Nouvelle icône** : un livre ouvert sur fond bleu, traversé par le trait rouge du lecteur de code-barres, sur l'exe, la barre des tâches et toutes les fenêtres.
- **Fiche du livre à droite ou en bas**, au choix dans le menu *Affichage*.
- **Une ligne sur deux colorée** dans les tableaux, pour mieux suivre une ligne.
- **Aide > Sources des données (API utilisées)** : la liste des services interrogés, avec leurs adresses (un clic ouvre la page).

## [1.6.0] - 2026-11-10

### Ajouts
- **Fiche sous la liste** : un clic sur un livre affiche sa jaquette, ses informations et son résumé complet sous la liste, avec les boutons *Prêter…* / *Enregistrer le retour*, *Modifier…* et *Supprimer*.
- **Nombre de livres affichés** à côté du champ de recherche.
- **Thème sombre** à fort contraste et **grands caractères**, dans le nouveau menu *Affichage*. Vos choix sont conservés.

## [1.5.1] - 2026-11-10

### Modifications
- La jaquette se change désormais depuis **Modifier…** : elle s'affiche à droite du formulaire, avec le bouton *Changer la jaquette…*. La nouvelle image est enregistrée avec la fiche (et ignorée si vous annulez).

## [1.5.0] - 2026-11-10

### Ajouts
- **Modifier la jaquette** : bouton *Jaquette…* dans la fiche d'un livre pour choisir une image de couverture sur l'ordinateur.
- **Défilement horizontal** des tableaux quand la fenêtre est trop étroite pour afficher toutes les colonnes.

### Corrections
- En vue *Miniatures*, les couvertures ne s'alignent plus toutes sur une seule ligne après une recherche, un tri ou une modification.

## [1.4.0] - 2026-11-10

### Ajouts
- **Affichage en miniatures** : dans l'onglet Bibliothèque, choisissez *Liste* ou *Miniatures* pour voir vos livres sous forme de couvertures.
- **Genre** du livre, modifiable dans la fiche et récupéré en ligne (Google Books) par *Compléter les fiches via Internet*.
- **Filtre par champ** : *Chercher dans* limite la recherche au titre, à l'auteur, à l'année ou au genre.
- **Trier par** titre, auteur, année ou genre, en ordre croissant ou décroissant, dans les deux affichages.

## [1.3.1] - 2026-11-08

### Corrections
- Les résumés et couvertures sont de nouveau récupérés depuis Google Books, qui refusait la plupart des recherches faute de quota.
- Pour récupérer les résumés et couvertures des livres déjà présents, utilisez **Fichier > Compléter les fiches via Internet (résumés, couvertures…)**.

## [1.3.0] - 2026-11-08

### Ajouts
- **Résumé** du livre, récupéré en ligne (Google Books), affiché dans la fiche et modifiable.
- **Photo de couverture**, téléchargée en ligne (Google Books ou Open Library) et affichée dans la fiche du livre. Les images sont enregistrées dans le dossier `covers` à côté de la base : pensez à le copier avec `booktek.db` quand vous faites une sauvegarde.
- *Compléter les fiches via Internet* ajoute aussi les résumés, couvertures et nombres de pages manquants, sans jamais remplacer ce que vous avez saisi.

### Corrections
- Le nombre de pages des livres non paginés (albums jeunesse notamment) est désormais récupéré depuis la BnF.

## [1.2.0] - 2026-11-07

### Ajouts
- **Rangement détaillé** avec un code d'emplacement universel *Meuble › Étage › Box › Rangée*, par exemple `Salon › É2 › B3 › R2`. La rangée 1 est celle de devant, la 2 celle de derrière, pour les livres rangés sur deux rangs.
- **Annuaire des emprunteurs** (nouvel onglet) : téléphone, e-mail, notes, livres en cours, ancienneté du plus vieux prêt en cours, nombre total de prêts. Les contacts en retard apparaissent en rouge.
- **Durée des prêts** : colonne « Depuis » dans les prêts en cours, colonne « Durée » dans l'historique.
- **Date de lecture** sur chaque livre.
- **Tri** par auteur (sur le nom de famille), titre, année, date de lecture ou emplacement, en cliquant sur l'en-tête de colonne. Le tri est conservé après chaque scan.

### Note
Les bases existantes sont mises à niveau automatiquement au premier lancement, sans perte de données. Les emprunteurs des prêts passés sont ajoutés à l'annuaire.

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
