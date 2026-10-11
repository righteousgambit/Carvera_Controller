# Verified desktop updates

Build and install are separate operations. `scripts/build_adaptive_macos.py`
stages source, creates a package source manifest and signs/verifies its artifact;
it does not install or connect a machine. Preserve the exact Git revision,
`build-request.json` and an independent `built-verification.json` before installing.
The verification receipt must identify the built bundle, requested version and
source revision, zero mismatches, and successful strict signature verification.
The build root must also contain `artifact/source-manifest.json`.

`scripts/install_verified_macos.py` updates an existing controller bundle without
launching it. Supply five explicit paths: build `--root`, installed `--target`,
and distinct sibling `.app` paths for `--recovery`, `--staging` and `--failed`.
Recovery/staging/failure destinations must be absent. Quit the installed app
through its UI first; the installer also refuses a detected running target.

Before copying, the installer independently verifies source hashes, contained
manifest members, bundle identity, source/plist version and strict signature.
It validates the existing target signature and checks free installation-volume
capacity against conservative copied-file size plus a 1 GiB reserve. Staging
is independently verified before the old target moves to recovery. Installed
source hashes and signature are verified again after the swap.

A staging failure leaves the old target in place and preserves staging. An
ordinary post-swap verification failure preserves the failed new bundle and
restores the old bundle, checking its signature. The attempt writes
`artifact-verification.json`; completed attempts and existing recovery/forensic
paths are never overwritten. Inspect the receipt and filesystem before retrying.
This is controlled-failure recovery, not a guarantee against power loss or a
second filesystem failure during rollback.

Operator profiles, calibration/setup custody and other local stores are outside
this installation transaction. Capture their hashes/backups separately and read
back after native UI review. A successful installed receipt does not prove
permission, connection, camera freshness, workflow correctness or machining.
Keep those acceptance gates separate and retain a working recovery build.

The regression suite covers low-space refusal before copy, manifest containment,
receipt/source mismatch, a running target, staging failure, post-swap rollback,
retained recovery and refusal to repeat a completed update. Tests use temporary
fake bundles and mocked signature/copy commands; actual signature and source
verification require a real built artifact and installed readback.


Packaging shell preflight (2026-10-05): `msgfmt` and `codesign` must resolve
before creating the output directory or staging source. Missing-tool failures
identify the required prepared PATH; they do not install dependencies or invoke
the packager. Nine build-preflight tests pass. The DESKTOP185 first build attempt
failed at locale compilation because its shell omitted Homebrew's tool path;
the original log and staged source remain in its build root, and the retry uses
an explicit prepared PATH. This preflight source followup postdates the frozen
DESKTOP185 controller source.


Failed native-helper startup can be investigated with
`scripts/diagnose_macos_helper_startup.py --root FAILED_BUILD --output FRESH_OUTPUT`.
It accepts only a retained failed, uninstalled first qualification with matching
attempt and helper hashes. It copies and ad-hoc signs only the contained native
helper, verifies unchanged instructions, and leaves the original package alone.
The output retains its exact harness, stage observations and sampler evidence.
It is diagnostic-only and cannot satisfy installer preflight.

`--sample-after` sets the observation delay; `--request-after` can explicitly
withhold input while retaining the child's stdin to make stack capture possible.
The latter induces an input wait and must never be interpreted as the original
startup failure. Sampling can perturb timing; a fresh signature is not evidence
of a cold OS cache. A successful later diagnostic never changes a failed first
qualification. Preserve sampler failures and distinguish an exit code from an
actual captured stack.
