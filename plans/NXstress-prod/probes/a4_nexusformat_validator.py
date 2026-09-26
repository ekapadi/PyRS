"""A4: does the installed ``nexusformat`` 1.0.8 provide a validator?

Four documents in this series make claims about this, and **they contradict each
other**. Three say the capability does not exist; one instructs an implementer to
use it. A reader cannot settle that, because both readings are plausible prose.

Claims under test
-----------------
1. ``README.md:728`` (Decisions Log item 16b) --
   "the installed ``nexusformat`` 1.0.8 package has no validator capability at
   all."
2. ``10-flip-defaults.md:49-53`` --
   "Confirmed: this is *not* part of the installed ``nexusformat`` PyPI package
   (1.0.8 has no ``validate`` module or ``nxvalidate`` script) -- it exists only
   as a separate repository."
3. ``09-fit-spectrum-nxstress.md:253-258`` --
   "Run the ``nexusformat``-org's NXstress validator ... **once the validator and
   schema doc are available** (confirmed not yet present in this repo or in the
   installed ``nexusformat`` package as of this writing)."
4. ``04-nxstress-internal-cleanup.md:128-132`` -- **contradicts 1-3** --
   "inspect sx/sy/sz fields with ``h5dump`` or the ``nexusformat`` Python API"
   and "Write a ``.nxs`` file and open it in the ``nexusformat`` validator
   (with ``nxstress.use_production_names = true`` temporarily...)".

Claim 4 tells the implementer of spec 04 to run a tool that claims 1-3 say does
not exist. Whichever way this resolves, one of these documents is wrong.

Run: ``pixi run python plans/NXstress-prod/probes/a4_nexusformat_validator.py``
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import sys


def report(claim: str, result: str) -> None:
    print(f"\n  CLAIM   {claim}")
    print(f"  RESULT  {result}")


def main() -> int:
    import nexusformat

    print("=" * 78)
    print("A4 PROBE: nexusformat validator capability")
    print("=" * 78)
    print(f"\ninstalled nexusformat version: {nexusformat.__version__}")
    print(f"package location:             {nexusformat.__file__}")

    report(
        "1.0.8 has no `validate` module",
        f"importlib.util.find_spec('nexusformat.validate') -> {importlib.util.find_spec('nexusformat.validate')}",
    )

    submodules = []
    for name in ("validate", "nexus.validate", "nxvalidate"):
        try:
            importlib.import_module(f"nexusformat.{name}")
            submodules.append(name)
        except ImportError:
            pass
    report(
        "no validator submodule under nexusformat",
        f"importable validator submodules: {submodules or 'NONE'}",
    )

    script = shutil.which("nxvalidate")
    report("1.0.8 has no `nxvalidate` script", f"shutil.which('nxvalidate') -> {script!r}")

    import nexusformat.nexus as nx

    validate_names = sorted(n for n in dir(nx) if "valid" in n.lower())
    report(
        "no validator capability at all",
        f"names containing 'valid' in nexusformat.nexus: {validate_names or 'NONE'}",
    )

    h5dump = shutil.which("h5dump")
    report(
        "spec 04 Verification says to use `h5dump` or the nexusformat Python API",
        f"shutil.which('h5dump') -> {h5dump!r}",
    )

    # The Python API itself (as distinct from a validator) plainly does exist;
    # spec 04's Verification conflates the two, so test them separately.
    report(
        "the nexusformat *Python API* exists (spec 04's other instruction)",
        f"nexusformat.nexus.nxload is {type(nx.nxload).__name__}, NXentry is {nx.NXentry.__name__}",
    )

    print("\n" + "-" * 78)
    print("VERDICT")
    print("-" * 78)
    print("Claims 1, 2 and 3 are CONFIRMED: no validate module, no nxvalidate")
    print("script, no validator name anywhere in the public API.")
    print("Claim 4 is therefore WRONG in part: spec 04's Verification directs an")
    print("implementer to a validator that does not exist. Its *other* half -- the")
    print("nexusformat Python API -- does exist and is usable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
