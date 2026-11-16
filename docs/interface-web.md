# Interface web (branche `webview`)

Proposition : garder toutes les fonctions de BookTek (Python) avec le visuel de la maquette Electron (branche `electron`).

## Technologie retenue : Python + pywebview (WebView2)

| | Python + pywebview (retenu) | Electron (maquette) | Tauri |
|---|---|---|---|
| Logique existante (`db`, `lookup`, `isbn`, `bkc_import`, `updater`) | réutilisée telle quelle | à réécrire en TypeScript | à réécrire (Rust ou TS) |
| Base `booktek.db` des utilisateurs | inchangée | migration vers IndexedDB | migration |
| Mise à jour automatique (exe unique) | inchangée | à refaire (electron-updater, installeur NSIS) | à refaire |
| Taille de l'exe | ~29 Mo | ~100 Mo et plus | ~10 Mo |
| Tests existants | gardés | perdus | perdus |

La fenêtre est un Edge WebView2 (présent d'origine sur Windows 10 et 11), qui affiche la même interface React que la maquette Electron, donc le même rendu.

## Organisation

- `web/` : interface React + Vite (reprise de la maquette Electron, sans Dexie). `npm run build` produit `web/dist`.
- `booktek/web.py` : la fenêtre, un petit serveur local (bottle, fourni avec pywebview) pour `web/dist` et les jaquettes `covers/`, et la classe `Api` appelée depuis JavaScript (`window.pywebview.api.…`). Elle reprend la logique de `app.py`.
- **Photo par téléphone** : `Api.phone_start()` ouvre un second serveur (`http.server`, sur toutes les cartes réseau, port libre) dont seule l'adresse `/<jeton aléatoire>` répond : en GET la page `PHONE_PAGE`, en POST la photo, redressée et réduite par Pillow puis transmise à l'interface par l'événement `phone_photo`. L'adresse est affichée en QR code par `booktek/qr.py`, un encodeur minimal écrit pour éviter une dépendance (mode octet, niveau M, versions 1 à 6, masque fixe). `phone_stop()` ferme le serveur à la fermeture de la fenêtre du QR code. Au premier lancement, le pare-feu Windows demande d'autoriser BookTek sur les réseaux privés.
- `main.py` ouvre l'interface web ; `python main.py --tk` ouvre encore l'ancienne interface Tkinter.

## Commandes

```
pip install pywebview                 # une fois
cd web && npm install && npm run build   # après chaque modification de web/src
python main.py
```

`tools/release.py` construit l'interface puis l'embarque dans l'exe (`--add-data web/dist`).

## Ce qui diffère de la version Tkinter

- Fiche du livre toujours à droite (disposition de la maquette) ; regroupement par auteur, année ou genre dans une liste déroulante au lieu d'un panneau.
- Thème sombre obtenu par inversion des couleurs (raccourci, voir `style.css`).
- Les polices DM Sans et Manrope viennent de Google Fonts : hors ligne, police système.
- Sauvegardes reprises de la maquette Electron, mais sous forme d'archive ZIP (`booktek/backup.py`) : base + jaquettes, une par jour au lancement, 10 conservées, restauration avec copie de sécurité. Les sauvegardes JSON de la maquette ne sont pas reprises.

## Journal

`booktek.log` à côté de la base (`setup_log()` dans `web.py`, module `logging` standard, 1 Mo et 3 fichiers gardés).

- Toutes les méthodes publiques de `Api` sont enveloppées par `_logged()` (boucle après la classe) : une nouvelle méthode est tracée sans rien ajouter. Le wrapper recopie la signature (`__signature__`), car pywebview lit les paramètres pour créer la fonction JavaScript.
- **Standard** (INFO) : démarrage, appels de `ACTIONS` (méthodes qui modifient les données), message `status` renvoyé, erreurs (`ValueError` en WARNING, autres exceptions avec la pile), fin du complément, mises à jour, exceptions des threads.
- **Verbeux** (DEBUG, réglage `verbose_log`, appliqué tout de suite) : tous les appels avec arguments tronqués, durée et réponse, et dans `lookup.py` chaque requête (clé Google masquée) et ce que chaque source a trouvé.
