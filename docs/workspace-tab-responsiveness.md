# Workspace tab responsiveness

Tab selection captured navigation context by serializing full loaded CAD meshes
on the UI thread, on departure and arrival. Updating the hidden section chooser
could also re-enter selection and repeat these captures. The C1/Saunders/vise
profile contains 3,707,460 numeric vertex entries. Three initial serializations
took 0.8281, 0.8058 and 0.7938 seconds each on this machine.

Loaded MachineProfile metadata is now recursively immutable, detached from the
input dictionary, and canonically serialized once during profile construction.
Navigation hashes reuse that serialization while freshly capturing setup,
tooling and view state. Mutable adapters continue fresh serialization. The final
canonical bytes are identical to the historical encoding, so bookmark identities
remain compatible. Changing geometry requires loading a replacement profile;
the cached metadata cannot silently diverge through supported public mutation.

The hidden chooser callback ignores a section already being selected. A tab
click therefore has one navigation arrival rather than recursively selecting it.

Under concurrent source tests, legacy serialization took 1.6507 seconds; cached
assembly/hash took 0.0524, 0.0460, 0.0205, 0.0197 and 0.0211 seconds. The old/new
hashes matched exactly. These are context-processing measurements, not end-to-end
native click latency or a guarantee that every source of UI delay is resolved.

Source validation: 56 focused model, profile-loading and Kivy navigation checks
passed in 123.75 seconds (one existing locale deprecation). Tests cover input
alias isolation, immutable cached metadata, canonical legacy bookmark identity,
mutable-adapter edit detection, one navigation arrival per tab click, scene and
program navigation, and rejection of changed setup/tool geometry. Ruff lint and
format, whitespace checks and both architecture contracts passed.
