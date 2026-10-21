# Third-party tools and source status

Fleetweft-authored code and documentation are licensed under the [MIT License](LICENSE),
Copyright (c) 2026 Andrew Yuan. The repository remains Private. This license does
not relicense external tools, libraries, operating-system packages or reference
projects; their original terms continue to apply.

Runtime uses the Python standard library only. Python retains its PSF license;
the SQLite engine distributed with Python has its own public-domain dedication.
The installed wheel contains Fleetweft modules, not a bundled Python interpreter.

Development build tools used for the retained run: build 1.3.0 (MIT), setuptools
80.9.0 (MIT), wheel 0.45.1 (MIT), packaging 26.3 (Apache-2.0 OR BSD-2-Clause), and
pyproject_hooks 1.3.3 (MIT). They are not vendored into the runtime package.

System OpenSSL is an external runtime dependency for artifact signing/verification.
The macOS test host uses LibreSSL through the same command interface. Neither is
vendored, and Fleetweft does not implement its own cryptographic primitives.

Linux, systemd, iproute2, nftables, Colima and Lima are external deployment or test
infrastructure and retain their respective licenses. No VM image, tool binary,
package cache, downloaded third-party source, private certificate or key is
committed here.

Reference links in docs/RESEARCH.md informed protocol choices; no Mender,
hawkBit, Greengrass, TUF or Shiftstead implementation is vendored in this project.

## License scope check

The wheel distributes Fleetweft's own Python modules, distribution metadata and
its MIT license. Generated first-party sample app payloads also retain the full
MIT notice as Python comments before signing; arbitrary caller-supplied apps keep
their own licensing requirements. No third-party implementation, model, dataset, interpreter,
cryptographic binary or OS/VM image is bundled. The declared Python runtime
package dependency list is empty. Installed build-tool metadata was checked for
these versions; no dependency source or license notice was removed or replaced.
This distribution boundary presents no identified dependency-license conflict
with licensing Fleetweft itself under MIT. Bundling external binaries or libraries
in a future distribution requires a separate review of their actual notices.

Primary references checked:

- [MIT license text](https://opensource.org/license/mit).
- [Python history and licenses](https://docs.python.org/3/license.html).
- [SQLite public-domain dedication](https://sqlite.org/copyright.html).
- [OpenSSL license by release](https://openssl-library.org/source/license/index.html):
  OpenSSL 3.x uses Apache-2.0; earlier releases have their original OpenSSL/SSLeay
  terms. The invoked system binary is external, not redistributed here.
- [LibreSSL portable licensing notices](https://github.com/libressl/portable/blob/master/COPYING):
  the macOS command is external; component notices are not replaced by MIT.

Linux, systemd, iproute2, nftables, Colima and Lima are deployed/tested as separately
installed tools. No claim is made that their licenses are MIT or that this check
licenses an entire VM image. Historical review records stating “no selected
license” describe those earlier commits and remain historical evidence.
