# Référence historique — patterns rois à cinq états

Ce document préserve la seule partie encore utile du module standalone de la branche `claude/0121-pattern-jass-variant-C-kings`, cité par la PR #241 comme référence de l'`extract_index` introduit dans la PR #186. Le module n'est pas réintroduit comme code actif.

## Encodage et dimensions

Chaque case d'un pattern reçoit un chiffre :

| État | Chiffre |
|---|---:|
| vide | 0 |
| homme noir | 1 |
| dame noire | 2 |
| homme blanc | 3 |
| dame blanche | 4 |

Pour les huit cases `squares[i]` d'un pattern, l'index base-5 est :

```text
index = Σ cell(squares[i]) × 5^i, pour i = 0..7
```

Les dimensions historiques étaient `8 patterns × 5⁸`, soit `390 625` buckets par pattern et environ `3 125 000` buckets au total.

## Implémentation de référence

```cpp
std::uint32_t extract_index(Bitboard bm, Bitboard bk,
                            Bitboard wm, Bitboard wk,
                            const Pattern& p) noexcept {
    std::uint32_t idx = 0;
    for (std::size_t i = 0; i < PATTERN_SIZE; ++i) {
        const Square sq = p.squares[i];
        const Bitboard bit = Bitboard{1} << (sq - 1);
        std::uint32_t cell = 0;
        if      (bm & bit) cell = 1;
        else if (bk & bit) cell = 2;
        else if (wm & bit) cell = 3;
        else if (wk & bit) cell = 4;
        idx += cell * POW5[i];
    }
    return idx;
}
```

avec :

```cpp
constexpr std::array<std::uint32_t, 9> POW5 = {
    1, 5, 25, 125, 625, 3125, 15625, 78125, 390625,
};
```

## Vecteurs représentatifs

Pour la première case du premier pattern :

- position vide → index `0` ;
- homme noir → index `1` ;
- dame noire → index `2` ;
- homme blanc → index `3` ;
- dame blanche → index `4`.

Les tests historiques vérifiaient aussi `5⁸ = 390625`, `8 × 390625 = 3125000`, ainsi que la borne `index < 390625` lorsque toutes les cases étaient remplies de dames blanches.

## Statut

Ce module standalone n'a jamais été entraîné. Il a été dépassé par la géométrie pattern v4 et demeure uniquement une référence d'encodage.
