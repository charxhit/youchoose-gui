"""Pure-Python YouChoose *educational simulation* engine.

This intentionally does not implement SMTP, TLS record encryption, or OT.  It
models the paper's record-choice game using authentic image-byte variants and
opaque, synthetic 'ciphertext identifiers'.  Never treat the identifiers as
cryptographic ciphertexts or the game as an account-ownership proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from secrets import randbelow, token_bytes
from typing import Optional
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

PAPER_DOI = "10.1145/3774904.3792744"
PUBLIC_KEY_LABEL = "demo-verifier-public-key"


def sample_image() -> Image.Image:
    """Make a soft landscape scene locally, avoiding downloads/assets."""
    width, height = 512, 320
    a = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / (height - 1)
        if t < .62:
            u = t/.62
            rgb = (22+76*u, 57+86*u, 105+68*u)
        else:
            u = (t-.62)/.38
            rgb = (54-11*u, 104-34*u, 103-36*u)
        a[y, :, :] = np.array(rgb, dtype=np.uint8)
    im = Image.fromarray(a, "RGB")
    d = ImageDraw.Draw(im)
    d.ellipse((373, 39, 433, 99), fill=(227, 175, 107))
    d.polygon([(0,204),(100,114),(190,207)], fill=(36,86,111))
    d.polygon([(103,207),(270,89),(417,208)], fill=(39,89,107))
    d.polygon([(255,208),(398,131),(512,222)], fill=(49,96,103))
    d.polygon([(228,131),(270,89),(313,134)], fill=(143,164,157))
    d.polygon([(0,248),(87,217),(178,258),(307,215),(512,250),(512,320),(0,320)],fill=(53,107,93))
    for x,y,scale in [(78,254,1),(428,270,1.2),(354,247,.7),(177,272,.8)]:
        h=int(34*scale)
        d.line((x,y+h,x,y), fill=(39,70,62), width=max(2,int(4*scale)))
        d.polygon([(x,y-12*scale),(x-13*scale,y+8*scale),(x+13*scale,y+8*scale)],fill=(30,78,66))
        d.polygon([(x,y-25*scale),(x-10*scale,y-5*scale),(x+10*scale,y-5*scale)],fill=(31,85,71))
    return im.filter(ImageFilter.GaussianBlur(.4))


def normalize_image(image: Image.Image) -> Image.Image:
    """Resize and limit extrema so signed ± intensity perturbations are invertible."""
    im = image.convert("RGB")
    im.thumbnail((680, 420), Image.Resampling.LANCZOS)
    if im.height < 160:
        target_h = 160
        target_w = min(680, max(1, round(im.width * target_h / im.height)))
        im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    arr = np.asarray(im, dtype=np.int16).copy()
    arr = np.clip(arr, 24, 231).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def hash_challenge(bits: list[int], public_key: str = PUBLIC_KEY_LABEL) -> str:
    # This mirrors the *structure* H(d || pk_V), not TLS channel binding.
    bitstring = ''.join(str(b) for b in bits)
    return sha256((bitstring+'|'+public_key).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class Record:
    index: int
    token_0: str
    token_1: str
    epsilon: int


class Simulator:
    """Deterministic state transitions given random bit choices."""

    def __init__(self, image: Optional[Image.Image] = None, n_bits: int = 8, intensity: int = 3):
        self.raw_image = image.copy() if image is not None else sample_image()
        self.n_bits = n_bits
        self.intensity = intensity
        self.session = token_bytes(24)
        self.challenge = []
        self.perturbations = []
        self.records = []
        self.original = None
        self.variant_0 = None
        self.variant_1 = None
        self.delivered = None
        self.authenticated = True
        self.retrieved = False
        self.recovered: Optional[list[int]] = None
        self.verdict: Optional[bool] = None
        self.regenerate()

    def regenerate(self, n_bits: Optional[int] = None, intensity: Optional[int] = None) -> None:
        if n_bits is not None:
            self.n_bits = int(n_bits)
        if intensity is not None:
            self.intensity = int(intensity)
        if not 2 <= self.n_bits <= 80:
            raise ValueError('n_bits must be between 2 and 80')
        if not 1 <= self.intensity <= 12:
            raise ValueError('intensity must be between 1 and 12')
        self.session = token_bytes(24)
        self.original = normalize_image(self.raw_image)
        base = np.asarray(self.original, dtype=np.int16).copy()
        a = base.copy()
        b = base.copy()
        self.perturbations = [1 if randbelow(2) else -1 for _ in range(self.n_bits)]
        boundaries = np.linspace(0, base.shape[0], self.n_bits+1, dtype=int)
        self.boundaries = list(zip(boundaries[:-1].tolist(),boundaries[1:].tolist()))
        self.records = []
        for i, (y0,y1) in enumerate(self.boundaries):
            sign=self.perturbations[i]
            a[y0:y1] += sign*self.intensity
            b[y0:y1] -= sign*self.intensity
        self.variant_0=Image.fromarray(np.clip(a,0,255).astype(np.uint8), 'RGB')
        self.variant_1=Image.fromarray(np.clip(b,0,255).astype(np.uint8), 'RGB')
        self.challenge=[randbelow(2) for _ in range(self.n_bits)]
        for i,(y0,y1) in enumerate(self.boundaries):
            # Synthetic opaque identifiers, intentionally NOT encrypted TLS bytes.
            digests=[]
            for j, image in enumerate((self.variant_0,self.variant_1)):
                data=np.asarray(image)[y0:y1].tobytes()
                digest=sha256(self.session+i.to_bytes(2,'big')+bytes([j])+data).hexdigest()
                digests.append(digest[:16])
            self.records.append(Record(i, digests[0], digests[1], self.perturbations[i]))
        self.retrieved=False
        self.recovered=None
        self.verdict=None
        self._refresh_delivery()

    def _refresh_delivery(self) -> None:
        a = np.asarray(self.variant_0)
        b = np.asarray(self.variant_1)
        mixed = a.copy()
        for i,(y0,y1) in enumerate(self.boundaries):
            if self.challenge[i] == 1:
                mixed[y0:y1] = b[y0:y1]
        self.delivered=Image.fromarray(mixed, 'RGB')
        self.retrieved=False
        self.recovered=None
        self.verdict=None

    def choose(self, i: int, bit: int) -> None:
        if not (0 <= i < self.n_bits and bit in (0,1)):
            raise ValueError('Invalid record or bit')
        self.challenge[i]=bit
        self._refresh_delivery()

    def randomize(self) -> None:
        self.challenge=[randbelow(2) for _ in range(self.n_bits)]
        self._refresh_delivery()

    def retrieve(self) -> Optional[list[int]]:
        if not self.authenticated:
            self.retrieved=False
            self.recovered=None
            return None
        target=np.asarray(self.delivered)
        a=np.asarray(self.variant_0)
        b=np.asarray(self.variant_1)
        bits=[]
        for y0,y1 in self.boundaries:
            chunk=target[y0:y1]
            if np.array_equal(chunk,a[y0:y1]):
                bits.append(0)
            elif np.array_equal(chunk,b[y0:y1]):
                bits.append(1)
            else:
                raise ValueError('The message contains a block that is neither allowed variant.')
        self.retrieved=True
        self.recovered=bits
        return bits

    def verify(self, submitted: Optional[list[int]] = None) -> bool:
        if submitted is None:
            submitted=self.recovered
        if submitted is None or len(submitted) != self.n_bits:
            self.verdict=False
            return False
        expected=hash_challenge(self.challenge)
        observed=hash_challenge(submitted)
        self.verdict=compare_digest(expected,observed)
        return self.verdict

    @property
    def chance(self) -> str:
        return f'1 in {2**self.n_bits:,}'

    def guess_without_access(self) -> list[int]:
        return [randbelow(2) for _ in range(self.n_bits)]

    def pixel_demo(self, record_index: int) -> tuple[tuple[int,int,int],tuple[int,int,int],tuple[int,int,int]]:
        y0,y1=self.boundaries[record_index]
        x=self.original.width//2
        y=(y0+y1)//2
        return (self.original.getpixel((x,y)), self.variant_0.getpixel((x,y)),self.variant_1.getpixel((x,y)))


class SequentialDemo:
    """One irreversible verifier choice per round; no unselected data delivered."""
    def __init__(self, image: Optional[Image.Image] = None, n_bits: int = 10):
        self.sim = Simulator(image, n_bits=n_bits, intensity=3)
        self.selections: list[int] = []
        self.recovered: Optional[list[int]] = None
        self.verdict: Optional[bool] = None
        self._output = np.full_like(np.asarray(self.sim.original), 225)

    @property
    def complete(self) -> bool:
        return len(self.selections) == self.sim.n_bits

    @property
    def round_index(self) -> int:
        return len(self.selections)

    @property
    def image(self) -> Image.Image:
        return Image.fromarray(self._output.copy(), 'RGB')

    def forward(self, bit: int) -> None:
        if self.complete or bit not in (0, 1):
            raise ValueError('No active round or invalid bit')
        i = self.round_index
        y0, y1 = self.sim.boundaries[i]
        variant = self.sim.variant_0 if bit == 0 else self.sim.variant_1
        self._output[y0:y1] = np.asarray(variant)[y0:y1]
        self.selections.append(bit)

    def recover(self) -> list[int]:
        if not self.complete:
            raise ValueError('Complete all rounds before retrieval')
        # Recovery uses only the retrieved image bytes and original variants,
        # not the verifier's selection list.
        self.sim.delivered = self.image
        self.recovered = self.sim.retrieve()
        return self.recovered.copy()

    def verify(self, submitted: Optional[list[int]] = None) -> bool:
        if not self.complete:
            raise ValueError('Complete all rounds before verification')
        bits = self.recovered if submitted is None else submitted
        self.verdict = bool(bits is not None and len(bits) == self.sim.n_bits
                            and all(b in (0, 1) for b in bits)
                            and compare_digest(hash_challenge(self.selections), hash_challenge(bits)))
        return self.verdict
