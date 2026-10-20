"""Denní vstup: stejný trénink jako train.py. Brána rozhodne, jestli se publikuje nový strom."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import train

if __name__ == "__main__":
    sys.exit(train.main())
