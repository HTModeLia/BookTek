# Retrouver les ISBN d'une collection Book Collector

Ces scripts servent une seule fois, pour reprendre une collection Book Collector dans BookTek. Ils ne font pas partie de l'application.

Ils travaillent sur le dossier `Book Collector` à la racine du dépôt. On peut aussi donner un autre dossier en argument. Ce dossier contient les données personnelles (images, `.bkc`, résultats) et n'est **jamais commité** : il faut le copier à la main d'un ordinateur à l'autre.

## Étapes

```
powershell -File tools/bookcollector/ocr.ps1 -Dir "Book Collector\Images" -Out "Book Collector\ocr.json"
python tools/bookcollector/isbn_list.py
python tools/bookcollector/tri_html.py
```

1. **`ocr.ps1`** lit le texte de chaque image avec l'OCR intégré à Windows (`Windows.Media.Ocr`, en français), sans rien installer. Résultat : `ocr.json`, environ 10 s pour 340 images.
2. **`isbn_list.py`** propose un ISBN par image. Il cherche d'abord un ISBN lu sur l'image. Sinon, il interroge Google Books (avec la clé de `booktek/_key.py`) à partir du titre tiré du nom du fichier et du texte lu. Si rien n'est trouvé ou si le quota journalier de Google est épuisé (erreur 429), il interroge le catalogue de la BnF. Résultat : `livres_ocr.csv`. On peut le relancer : les lignes qui ont déjà un ISBN sont gardées et seules les autres sont recherchées.
3. **`tri_html.py`** construit `tri.html`, à ouvrir dans un navigateur. Chaque image y apparaît avec sa vignette, l'ISBN déduit et trois boutons : *Garder*, *Rejeter*, *Vérifier*.
   - **ISBN sûr** : chaque fiche des `.bkc` (y compris dans `Backup`) contient le chemin de l'image, l'ISBN et la vignette `Thumbnails\<md5>.png`. Chaque vignette est rattachée à son image par comparaison visuelle.
   - **ISBN à confirmer** : il vient de `livres_ocr.csv`. Les autres ISBN proposés sont cliquables, et l'ISBN reste modifiable à la main.
   - Les choix sont gardés dans le navigateur. **Exporter les décisions** produit `booktek_tri.csv`, qui se recharge avec *Reprendre un fichier de décisions*, par exemple sur un autre ordinateur. **Exporter les ISBN gardés** produit un fichier texte à importer dans BookTek (*import d'une liste d'ISBN*).

`liste_html.py` et `choix_html.py` sont deux versions plus anciennes de la page de tri (une ligne par image, ou les doublons regroupés). Elles sont gardées pour mémoire.

## Limites

- Les ISBN de la recherche sont des propositions : l'édition peut différer (poche, club, gros caractères). Il faut les vérifier.
- Le nom de fichier Book Collector est tronqué vers 25 caractères et perd les accents (« Tmraire » pour « Téméraire »), ce qui dégrade la recherche.
- Les vignettes « sans image » ne ressemblent à aucune image du dossier `Images`. La plupart ne sont plus citées par aucune fiche.
