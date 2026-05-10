# Licensing

Jass is **dual-licensed**.

## 1. Open-source: GNU Affero General Public License v3.0 or later

The default licence under which Jass is distributed is the [GNU Affero
General Public License, version 3](LICENSE) (or, at your option, any
later version published by the Free Software Foundation).

In short:

- You may freely **use, study, modify, redistribute and run** Jass for
  any purpose.
- If you **convey** (distribute) a work that contains Jass, or a
  derivative of Jass, in source or object form, you must do so under
  the AGPL v3 too — including making the corresponding source code
  available to the recipients.
- If you **make Jass (or a derivative) available to users over a
  network** (for example, by hosting it as part of a web app), you
  must also make the corresponding source code available to those
  users.  This is the AGPL "network use" clause that closes the SaaS
  loophole left open by the plain GPL.
- The full legal text is in [LICENSE](LICENSE).

If those terms work for your use case, you're done — just keep the
notices, the licence text and the source-code-availability obligation.

## 2. Commercial licence

If the AGPL conditions don't fit your situation — for example because
you want to integrate Jass into a closed-source product, or to ship a
binary inside a non-AGPL application without exposing its source —
**a commercial licence is available** for that use.

The commercial licence:

- removes the "share alike" obligations of the AGPL,
- comes with a personal grant from the copyright holder,
- is negotiated case by case.

To obtain one, please get in touch with the copyright holder
**Jean-François Collin**.  Open an issue on the project's tracker (or
use the contact email listed on the GitHub profile) describing your
intended use; you will be sent the standard commercial-licence draft
in reply.

## How this is possible

Dual-licensing is only legally possible when the same party owns the
entire copyright on the work.  Jass is a **clean-room** implementation
written from scratch by the copyright holder; no GPL/AGPL code from
any other engine has been read or copied into it (the README spells
this out).  This means the copyright holder is free to relicense the
codebase under any additional terms they choose, including a
commercial licence.

That ownership is preserved going forward by the **Contributor
Licence Agreement** required from every external contributor — see
[CONTRIBUTING.md](CONTRIBUTING.md).  Without that mechanism, the
ability to relicense Jass commercially would be lost the day someone
else's patch landed in the tree, and the dual-licence model would
collapse.

## Files

| File              | Role |
|-------------------|------|
| [LICENSE](LICENSE)               | Full text of AGPL v3 (the OSS licence). |
| [LICENSING.md](LICENSING.md)     | This file — high-level explanation. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution rules and the CLA. |

Each source file carries an `SPDX-License-Identifier:
AGPL-3.0-or-later` header pointing at the OSS licence.  The commercial
licence is obtained out of band; the SPDX identifier reflects the
default public licence only.
