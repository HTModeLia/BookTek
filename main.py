"""Point d'entrée de BookTek (``python main.py``), également utilisé par PyInstaller.

Branche webview : interface web (booktek/web.py) ; ``python main.py --tk`` ouvre l'ancienne interface Tkinter.
"""
import sys

if __name__ == "__main__":
    if "--tk" in sys.argv:
        from booktek.app import main
    else:
        from booktek.web import main
    main()
