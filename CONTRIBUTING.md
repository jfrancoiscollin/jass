# Contributing to Jass

Thanks for your interest in contributing to Jass.  Before sending a
patch, please read the rules below — particularly the Contributor
Licence Agreement (CLA) section, which is **required** for every
contribution.

## Why a CLA

Jass is dual-licensed (AGPL v3 + a commercial licence — see
[LICENSING.md](LICENSING.md)).  This is only possible because the
copyright holder owns 100 % of the codebase: that's what gives the
right to relicense the same code under different terms.

If a contribution lands in the tree under a different licence, or
without an explicit grant to the copyright holder, the project loses
the right to keep relicensing — the dual-licensing model collapses
the moment someone else's code is in there.  The CLA below preserves
that right.

## The CLA

By submitting a contribution to this project (whether as a pull
request, a patch, an email, or any other form), you, the contributor,
agree to the following:

1. **You are entitled to make the contribution.**  You wrote the code
   yourself, or you have all necessary rights to submit it (employer
   permission included where relevant).
2. **You grant the copyright holder a perpetual, worldwide, non-
   exclusive, royalty-free licence** to use, reproduce, modify,
   display, perform, sublicence and distribute your contribution and
   any derivative works thereof, **including under terms different
   from those covering the project itself**, such as future versions
   of the AGPL or a commercial licence.
3. **You retain ownership** of your contribution.  Nothing in the CLA
   transfers your copyright; you can use your own contribution under
   any other licence on your end.
4. **No patent claims.**  If your contribution is covered by a patent
   you own or control, you grant the copyright holder and downstream
   users a royalty-free licence to that patent, limited to the
   contribution.
5. **As-is.**  The contribution is provided as is, without warranty.

In practice, opening a pull request signals your acceptance of these
terms.  If your patch needs an external authorisation (e.g. from your
employer), please mention it in the PR description.

## Workflow

1. Fork the repository and create a branch from `main`.
2. Make your change.  Keep commits focused; one logical change per
   commit.
3. Update or add tests in `tests/`.  The test runner is invoked with
   `./build/jass_tests` and must remain green.
4. Update the relevant docs (`docs/*.md`, `README.md`) if your patch
   changes a public behaviour.
5. Open a pull request with a short summary and a "Test plan"
   bullet-list, like the existing PRs.

## Build, test, lint

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/jass_tests
```

The build must be warning-free under GCC ≥ 11 / Clang ≥ 13 with
`-Wall -Wextra -Wpedantic` and the rest of the project's strict flags
(see [CMakeLists.txt](CMakeLists.txt)).

## Clean-room policy

Jass is a clean-room implementation — written from scratch without
reading the source of any other GPL/AGPL draughts engine (notably
Fabien Letouzey's *Scan*).  This is what allows Jass to distribute
under the dual-licence scheme described in
[LICENSING.md](LICENSING.md).

If you contribute, you implicitly confirm that the code you submit was
written by you, from public specifications and your own understanding,
without copying or paraphrasing source from any GPLed engine.  If you
have read another engine's source recently, please flag it in the PR
so the maintainer can decide how to proceed.

## Questions

Open an issue on the GitHub tracker.  For licensing-specific
questions (commercial licence, CLA wording), see
[LICENSING.md](LICENSING.md) for the contact path.
