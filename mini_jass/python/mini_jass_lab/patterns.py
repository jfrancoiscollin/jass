"""Features de PATTERNS pour Mini-Jass — l'analogue de l'archi de production.

⛔ POURQUOI CE MODULE EXISTE. Tout le laboratoire tournait jusqu'ici sur un
`MiniJassMLP` : deux couches cachees de 32 et des ReLU, 5 225 parametres,
`linear: false` dans les SIX configs. La production, elle, est un modele
LINEAIRE sur des features de PATTERNS (~2,13 M buckets, `method="linear"`), et
la regle gravee interdit d'en changer de classe. Le labo mesurait donc une
boucle que la production ne peut pas reproduire — ce qui vide de sa substance
l'argument de transposition au 10x10, seule raison d'etre du banc.

« MEME ARCHI » A TROIS COUCHES, et elles ne coutent pas la meme chose :
  1. LINEAIRE plutot que MLP           — un drapeau (`ModelConfig.linear`)
  2. features de PATTERNS plutot que brutes — CE MODULE
  3. eval SEULE + politique derivee de la recherche, plutot que deux tetes
     — une chirurgie de la boucle, pas encore faite

CE QUE FAIT CE MODULE. Comme en production, un pattern est un petit ENSEMBLE DE
CASES, et son bucket est la CONJONCTION des occupations de ces cases. Chaque
case a cinq etats (vide, pion blanc, dame blanche, pion noir, dame noire), donc
un pattern de `k` cases porte `5^k` buckets, et le vecteur de features est
l'indicatrice creuse des buckets actifs. Un modele lineaire sur ces buckets a
donc exactement la forme de l'evaluation de production : une somme de poids
lus dans des tables indexees par des conjonctions locales.

LE PLI EXACT EST FAIT. La production plie ses buckets par `rot180 ∘
colour-swap` (+17,1 Elo mesures a L3, le plus gros gain de recette de la
campagne) ; `fold_map` fait de meme ici, apres avoir VERIFIE que la
transformation preserve l'adjacence diagonale — le critere non negociable.
Mesure : 49,9 % des buckets sont mutualises, ce qu'on attend d'une involution a
peu de points fixes.

⚠️ CE QUI N'EST PAS ENCORE FIDELE : la couche 3, l'evaluation VALEUR SEULE avec
la politique derivee de la recherche. Tant qu'un modele porte une tete policy,
il ne peut pas avoir la taille d'un modele de patterns (elle multiplie tout par
les 72 actions : 1 323 344 parametres contre 18 128 en valeur seule).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Geometrie du 5x5, recopiee de `include/mini_jass/rules.hpp` — 13 cases
# jouables, coordonnees (ligne, colonne) sur la grille 5x5.
SQUARE_COORDINATES: tuple[tuple[int, int], ...] = (
    (0, 0), (0, 2), (0, 4),
    (1, 1), (1, 3),
    (2, 0), (2, 2), (2, 4),
    (3, 1), (3, 3),
    (4, 0), (4, 2), (4, 4),
)
PLAYABLE = len(SQUARE_COORDINATES)
STATES_PER_SQUARE = 5  # vide, pion blanc, dame blanche, pion noir, dame noire


def window_patterns(window: int) -> tuple[tuple[int, ...], ...]:
    """Patterns = cases jouables d'une fenetre carree glissante.

    C'est la construction locale de Scan transposee : des regions qui se
    recouvrent et couvrent le damier, chacune donnant une table indexee par la
    conjonction de ses cases. `window` fixe la taille de la region et donc, tres
    directement, le nombre de parametres.
    """
    if window < 2:
        raise ValueError("window must span at least two rows and columns")
    index = {coord: i for i, coord in enumerate(SQUARE_COORDINATES)}
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[int, ...]] = []
    for top in range(0, 5 - window + 1):
        for left in range(0, 5 - window + 1):
            squares = tuple(
                sorted(
                    index[(row, column)]
                    for row in range(top, top + window)
                    for column in range(left, left + window)
                    if (row, column) in index
                )
            )
            # Deux fenetres peuvent couvrir exactement les memes cases jouables :
            # les dupliquer doublerait leurs poids sans rien ajouter au modele.
            if len(squares) >= 2 and squares not in seen:
                seen.add(squares)
                out.append(squares)
    return tuple(out)


@dataclass(frozen=True)
class PatternSet:
    patterns: tuple[tuple[int, ...], ...]
    offsets: tuple[int, ...]
    bucket_count: int

    @classmethod
    def from_window(cls, window: int) -> "PatternSet":
        patterns = window_patterns(window)
        offsets: list[int] = []
        total = 0
        for squares in patterns:
            offsets.append(total)
            total += STATES_PER_SQUARE ** len(squares)
        return cls(patterns, tuple(offsets), total)

    def describe(self) -> dict[str, object]:
        return {
            "pattern_count": len(self.patterns),
            "pattern_sizes": [len(p) for p in self.patterns],
            "bucket_count": self.bucket_count,
            "states_per_square": STATES_PER_SQUARE,
            # Le pli n'est pas une propriete du JEU de patterns mais de la
            # facon dont un modele partage ses poids : `fold_map` le calcule, et
            # `folded_class_count` dit ce qu'il reste de parametres libres.
            "folded_class_count": folded_class_count(self),
            "fold": "rot180_colour_swap",
        }


def square_states(planes: np.ndarray) -> np.ndarray:
    """(N, 4, cases) de plans binaires → (N, cases) d'etats dans [0, 5).

    L'ordre des plans suit `encode_features` : les quatre bitboards, puis le
    trait et les plies reversibles. Une case occupee par deux plans a la fois
    serait un etat impossible — on le refuse plutot que de le moyenner.
    """
    if planes.ndim != 3 or planes.shape[1] != 4:
        raise ValueError("expected (N, 4, squares) binary planes")
    occupancy = planes.sum(axis=1)
    if np.any(occupancy > 1.0 + 1e-6):
        raise ValueError("a square carries two pieces at once")
    weights = np.arange(1, 5, dtype=np.float32).reshape(1, 4, 1)
    return (planes * weights).sum(axis=1).astype(np.int64)


def bucket_indices(states: np.ndarray, pattern_set: PatternSet) -> np.ndarray:
    """(N, cases) d'etats → (N, patterns) d'indices GLOBAUX de bucket."""
    out = np.empty((states.shape[0], len(pattern_set.patterns)), dtype=np.int64)
    for column, (squares, offset) in enumerate(
        zip(pattern_set.patterns, pattern_set.offsets)
    ):
        index = np.zeros(states.shape[0], dtype=np.int64)
        for square in squares:
            index = index * STATES_PER_SQUARE + states[:, square]
        out[:, column] = index + offset
    return out


def pattern_features(
    raw_features: np.ndarray, pattern_set: PatternSet, extras: int = 2
) -> np.ndarray:
    """Features brutes de `encode_features` → indicatrice DENSE des buckets.

    ⚠️ Dense parce que le 5x5 est minuscule : `bucket_count` reste de l'ordre du
    millier. A 10x10 la production travaille evidemment en creux — la FORME du
    modele est la meme, seule l'implementation differe.

    Les `extras` (trait, plies reversibles) sont conserves tels quels et
    concatenes : la production a elle aussi un bloc d'extras a cote des buckets.
    """
    count = raw_features.shape[0]
    planes = raw_features[:, : 4 * PLAYABLE].reshape(count, 4, PLAYABLE)
    states = square_states(planes)
    index = bucket_indices(states, pattern_set)
    dense = np.zeros((count, pattern_set.bucket_count), dtype=np.float32)
    rows = np.repeat(np.arange(count), index.shape[1])
    dense[rows, index.reshape(-1)] = 1.0
    if extras:
        dense = np.concatenate(
            [dense, raw_features[:, 4 * PLAYABLE : 4 * PLAYABLE + extras]], axis=1
        )
    return dense


# --------------------------------------------------------------------------- #
#  LE PLI EXACT — `rot180 ∘ colour-swap`.
#
#  A L3 ce pli vaut +17,1 Elo, le plus gros gain de recette de la campagne, et
#  la lecon associee est de n'imposer QUE ce qui est vrai : `cs` seule et
#  `rot180` seule sont approximatives (les pions ont une direction), seule leur
#  COMPOSITION est une symetrie exacte. Le 5x5 la porte deja — le README
#  documente « an independently solved canonical graph using 180-degree rotation
#  plus colour/turn swap ».
#
#  ⛔ CRITERE NON NEGOCIABLE avant de plier quoi que ce soit : la transformation
#  doit PRESERVER L'ADJACENCE DIAGONALE. C'est ce qui disqualifie le miroir
#  gauche-droite a L3 (il casse 36 des 81 adjacences), et c'est verifie ici sur
#  la geometrie 5x5 par `rot180_preserves_diagonal_adjacency()`.
# --------------------------------------------------------------------------- #

# Plans dans l'ordre de `oracle.py` : white_men, black_men, white_kings,
# black_kings. L'etat d'une case vaut 0 (vide) ou plan+1.
STATE_COLOUR_SWAP: tuple[int, ...] = (0, 2, 1, 4, 3)


def _rot180_square_map() -> tuple[int, ...]:
    index = {coord: i for i, coord in enumerate(SQUARE_COORDINATES)}
    mapped = []
    for row, column in SQUARE_COORDINATES:
        image = (4 - row, 4 - column)
        if image not in index:
            raise ValueError(f"rot180 sends {(row, column)} off the playable set")
        mapped.append(index[image])
    return tuple(mapped)


SQUARE_ROT180: tuple[int, ...] = _rot180_square_map()


def rot180_preserves_diagonal_adjacency() -> bool:
    """Le critere de L3, applique a la geometrie 5x5.

    Deux cases jouables voisines en diagonale doivent le rester apres la
    transformation. Un miroir gauche-droite echoue ce test a 10x10 ; `rot180`
    doit le passer, sinon plier les buckets melangerait des positions qui ne se
    correspondent pas.
    """
    def adjacent(a: int, b: int) -> bool:
        (ra, ca), (rb, cb) = SQUARE_COORDINATES[a], SQUARE_COORDINATES[b]
        return abs(ra - rb) == 1 and abs(ca - cb) == 1

    for a in range(PLAYABLE):
        for b in range(a + 1, PLAYABLE):
            if adjacent(a, b) != adjacent(SQUARE_ROT180[a], SQUARE_ROT180[b]):
                return False
    return True


def fold_map(pattern_set: PatternSet) -> np.ndarray:
    """Bucket global → representant canonique de sa classe de symetrie.

    Deux buckets lies par `rot180 ∘ colour-swap` decrivent la MEME position a la
    couleur pres : ils doivent partager un seul poids. La fonction rend un
    tableau `classe[bucket]`, et un modele lineaire somme ses poids par classe.

    ⚠️ Le jeu de patterns doit etre CLOS par `rot180` — l'image d'un pattern doit
    etre un pattern du jeu — sinon la classe d'un bucket sortirait de l'espace
    represente. C'est verifie, et refuse si faux.
    """
    if not rot180_preserves_diagonal_adjacency():
        raise ValueError("rot180 does not preserve diagonal adjacency on this board")
    lookup = {squares: i for i, squares in enumerate(pattern_set.patterns)}
    images: list[int] = []
    for squares in pattern_set.patterns:
        image = tuple(sorted(SQUARE_ROT180[s] for s in squares))
        if image not in lookup:
            raise ValueError(
                "pattern set is not closed under rot180; folding would send a "
                f"bucket of {squares} outside the represented space"
            )
        images.append(lookup[image])

    classes = np.arange(pattern_set.bucket_count, dtype=np.int64)
    for source, squares in enumerate(pattern_set.patterns):
        target = images[source]
        target_squares = pattern_set.patterns[target]
        # Ou chaque case du pattern source atterrit dans le pattern image.
        position = {square: i for i, square in enumerate(target_squares)}
        order = [position[SQUARE_ROT180[s]] for s in squares]
        size = len(squares)
        for bucket in range(STATES_PER_SQUARE ** size):
            digits, rest = [], bucket
            for _ in range(size):
                digits.append(rest % STATES_PER_SQUARE)
                rest //= STATES_PER_SQUARE
            digits.reverse()                     # digits[i] = etat de squares[i]
            swapped = [STATE_COLOUR_SWAP[d] for d in digits]
            image_digits = [0] * size
            for i, slot in enumerate(order):
                image_digits[slot] = swapped[i]
            image_bucket = 0
            for digit in image_digits:
                image_bucket = image_bucket * STATES_PER_SQUARE + digit
            a = pattern_set.offsets[source] + bucket
            b = pattern_set.offsets[target] + image_bucket
            representative = min(a, b)
            classes[a] = representative
            classes[b] = representative
    return classes


def folded_class_count(pattern_set: PatternSet) -> int:
    return int(np.unique(fold_map(pattern_set)).size)
