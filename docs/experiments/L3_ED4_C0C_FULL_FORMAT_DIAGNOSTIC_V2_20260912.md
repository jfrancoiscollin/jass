# ED4 C0C full format diagnostic V2

V2 preserves V1 and V1--V6, the frozen 726 descriptors in order, six zero-byte
objects, the 216/15 recovery partition, and the 2100/2700-second ceilings. It
is a same-code bounded rehearsal only.

It additionally classifies only these existing leaf position/FEN validation
failures: malformed fingerprint syntax, invalid STM, out-of-range bitboard,
overlapping fingerprint pieces, malformed FEN, FEN colour-field or piece-field
errors, empty or invalid square tokens, invalid ranges, out-of-range or duplicate
squares, and cross-colour overlap. Each is emitted as a stable subcode without
input text, positions, identities, targets, union, readiness, or verdict.
Unknown validation errors and all catalog, authentication, runtime, descriptor,
deadline, or recovery errors still fail the entire diagnostic closed.
