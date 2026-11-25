# YouChoose — Protocol Demonstration

An interactive desktop GUI demonstrating the selective-forwarding mechanism in [YouChoose: A Lightweight Anonymous Proof of Account Ownership](https://doi.org/10.1145/3774904.3792744) (Aarav Varshney, Prashant Agrawal and Mahabir Prasad Jhanwar, WWW 2026).

The demo illustrates how a prover can recover a verifier's secret challenge from a message retrieved from an authenticated account, without sending the image to the verifier.

## Installation

Requires Python 3.10+ and runs on Windows, macOS and Linux.

```bash
python -m venv .venv
```

Activate the virtual environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the dependencies and launch the GUI:

```bash
python -m pip install -r requirements.txt
python main.py
```

Dependencies: PySide6, Pillow and NumPy.

Alternatively, use `launch_windows.bat` on Windows or `bash launch_macos_linux.sh` on macOS/Linux.

## How it works

1. Use the default image or select another image.
2. Choose the number of TLS record analogues (default: 10; range: 2–80).
3. Click **Start protocol**. The prover (P) generates two image variants, `m0` and `m1`, by applying complementary small pixel-intensity changes with randomized directions per block.
4. Act as the verifier (V) and choose which block to forward at each round. The server (S) assembles the selected blocks into a final image in real time.
5. Retrieve the image and recover `d'` by comparing each block against the corresponding blocks of the two original variants. Recovery uses the retrieved image bytes, not the verifier's stored choices.
6. Verify the proof by comparing `H(d' || pkV)` with `H(d || pkV)`.

Here, `d` is the verifier's challenge, `d'` is the recovered challenge, and `pkV` represents the verifier's public key. The real protocol sends the hash over a fresh authenticated TLS session, rather than sending the reconstructed image to V.

## Project structure

```text
YouChoose_Desktop/
├── main.py
├── requirements.txt
├── launch_windows.bat
├── launch_macos_linux.sh
├── assets/
├── youchoose/
│   ├── __init__.py
│   ├── engine.py        # Image variants, forwarding and challenge recovery
│   └── ui.py            # PySide6 desktop interface
└── tests/
    ├── test_engine.py
    └── test_sequential.py
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests cover image recovery, hash verification, sequential forwarding, partial delivery and reset behavior.

## Limitations

This is an educational simulation, not a production proof of account ownership. Image stripes represent TLS records conceptually and are not constrained by real TLS record sizes. The GUI exposes plaintext image previews for teaching purposes; a real verifier only sees protected records. SMTP, live TLS encryption, oblivious transfer, QUIC and actual account authentication are not implemented. The hash uses a demonstration public-key label, not a real cryptographic public key. The default ten-bit challenge is for illustration only and is not secure for real-world use.

## Reference

Varshney, A., Agrawal, P., & Jhanwar, M. P. (2026). *YouChoose: A Lightweight Anonymous Proof of Account Ownership*. Proceedings of the ACM Web Conference 2026. [Paper](https://doi.org/10.1145/3774904.3792744) · [Original implementation](https://github.com/aarav22/anon-pao).
