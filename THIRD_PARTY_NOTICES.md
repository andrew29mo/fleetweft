# Third-party tools and source status

Fleetweft authored source currently has no selected license. No LICENSE file is
included and no open-source licensing claim is made. The GitHub repository is
Private; no project license has been selected for the MVP either.

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
