"""Publie une nouvelle version de BookTek sur GitHub.

Usage (depuis la racine du dépôt) ::

    python tools/release.py            # publie
    python tools/release.py --dry-run  # vérifie tout sans rien publier

Étapes :

1. lit la version dans ``booktek/__init__.py`` et ses notes dans
   ``CHANGELOG.md`` (section ``## [x.y.z]``) ;
2. vérifie que la copie de travail est propre, que la branche est ``main``,
   synchronisée avec ``origin``, et que le tag ``vx.y.z`` n'existe pas ;
3. lance les tests unitaires ;
4. construit ``dist/BookTek.exe`` avec PyInstaller ;
5. crée et pousse le tag, crée la release GitHub et y joint l'exe.

Une fois la release publiée, les installations existantes la détectent et
se mettent à jour d'elles-mêmes (voir ``docs/mises-a-jour.md``).

Authentification : le jeton GitHub est lu dans le gestionnaire
d'identifiants de Git (celui utilisé pour ``git push``), ou dans la variable
d'environnement ``GITHUB_TOKEN``. Il n'est jamais affiché.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "HTModeLia/BookTek"
EXE = os.path.join(ROOT, "dist", "BookTek.exe")


def run(*cmd, capture=False):
    """Exécute une commande depuis la racine du dépôt ; arrête le script en cas d'échec."""
    res = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True)
    if res.returncode:
        sys.exit(f"Échec : {' '.join(cmd)}\n{res.stderr if capture else ''}")
    return res.stdout.strip() if capture else ""


def version():
    text = open(os.path.join(ROOT, "booktek", "__init__.py"), encoding="utf-8").read()
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def changelog_notes(ver):
    """Contenu de la section ``## [ver]`` du CHANGELOG (jusqu'à la section suivante)."""
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    m = re.search(rf"^## \[{re.escape(ver)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not m or not m.group(1).strip():
        sys.exit(f"Ajoutez une section « ## [{ver}] » dans CHANGELOG.md avant de publier.")
    return m.group(1).strip()


def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("Aucun jeton GitHub : définissez GITHUB_TOKEN ou faites d'abord un git push authentifié.")


def api(url, data, content_type, tok):
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"token {tok}", "Accept": "application/vnd.github+json",
        "User-Agent": "BookTek-release", "Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


def main():
    dry = "--dry-run" in sys.argv
    ver = version()
    tag = f"v{ver}"
    notes = changelog_notes(ver)
    print(f"Version {ver} (tag {tag})")

    if run("git", "status", "--porcelain", capture=True):
        sys.exit("La copie de travail contient des modifications non commitées.")
    if run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True) != "main":
        sys.exit("Publiez depuis la branche main.")
    run("git", "fetch", "-q", "origin", "--tags")
    if run("git", "rev-parse", "HEAD", capture=True) != run("git", "rev-parse", "origin/main", capture=True):
        sys.exit("main n'est pas synchronisée avec origin/main (git pull / git push).")
    if run("git", "tag", "-l", tag, capture=True):
        sys.exit(f"Le tag {tag} existe déjà : incrémentez __version__ dans booktek/__init__.py.")

    print("Tests…")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q")
    print("Construction de l'exécutable…")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
        "--name", "BookTek", "--distpath", "dist", "--workpath", "build", "main.py", capture=True)
    size = os.path.getsize(EXE)
    print(f"{EXE} ({size / 1e6:.1f} Mo)")

    if dry:
        print("\n--dry-run : rien n'a été publié. Notes de version :\n\n" + notes)
        return

    tok = token()
    run("git", "tag", "-a", tag, "-m", f"BookTek {ver}")
    run("git", "push", "-q", "origin", tag)
    rel = api(f"https://api.github.com/repos/{REPO}/releases",
              json.dumps({"tag_name": tag, "name": f"BookTek {ver}", "body": notes}).encode(),
              "application/json", tok)
    upload = rel["upload_url"].split("{")[0] + "?name=BookTek.exe"
    with open(EXE, "rb") as f:
        asset = api(upload, f.read(), "application/vnd.microsoft.portable-executable", tok)
    print(f"Release publiée : {rel['html_url']}")
    print(f"Exécutable : {asset['browser_download_url']}")


if __name__ == "__main__":
    main()
