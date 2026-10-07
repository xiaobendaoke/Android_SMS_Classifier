"""Training-only text augmentation stubs."""
from __future__ import annotations

import random
from typing import List, Sequence

_ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d"]


def insert_zero_width(text: str, rng: random.Random) -> str:
    """Insert a zero-width character at a random position."""
    if not text:
        return text
    pos = rng.randrange(len(text))
    ch = rng.choice(_ZERO_WIDTH_CHARS)
    return text[:pos] + ch + text[pos:]


def random_space_jitter(text: str, rng: random.Random) -> str:
    """Insert extra spaces around punctuation."""
    return text.replace("，", " ， ") if "，" in text and rng.random() < 0.5 else text


def augment_text(text: str, seed: int = 42, num_variants: int = 1) -> List[str]:
    """
    Generate augmented variants (train split only).

    Phase 0: lightweight perturbations for pipeline wiring.
    """
    rng = random.Random(seed)
    variants: List[str] = []
    for i in range(num_variants):
        local_rng = random.Random(rng.randint(0, 2**31 - 1) + i)
        out = text
        if local_rng.random() < 0.5:
            out = insert_zero_width(out, local_rng)
        if local_rng.random() < 0.5:
            out = random_space_jitter(out, local_rng)
        if out != text:
            variants.append(out)
    return variants


def augment_records_texts(texts: Sequence[str], seed: int = 42) -> List[str]:
    """Augment a list of texts, returning originals plus variants."""
    output = list(texts)
    for idx, text in enumerate(texts):
        output.extend(augment_text(text, seed=seed + idx))
    return output
