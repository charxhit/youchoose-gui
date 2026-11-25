"""Launch the YouChoose desktop demo: python main.py"""
import sys

try:
    from youchoose.ui import launch
except ImportError as exc:
    if exc.name and (exc.name.startswith('PySide6') or exc.name in ('PIL','numpy')):
        print('Missing GUI dependency. Install with: python -m pip install -r requirements.txt')
        print(f'Details: {exc}')
        sys.exit(1)
    raise

if __name__ == '__main__':
    sys.exit(launch())
