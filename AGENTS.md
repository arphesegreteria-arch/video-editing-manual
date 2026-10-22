# Bridge implementation rules

- Public bridge commands must be generic, reusable primitives. Never encode a project name, timeline name, edit timestamp, CTA wording, asset path, or one-off editorial assumption in a command name or its implementation.
- Put edit-specific information in explicit, validated command parameters or a versioned plan; never in bridge code.
- Scope every operation at runtime through the workstation configuration, registry ownership, explicit caller input, and read-back verification.
- Safe writes must duplicate before editing, never save automatically, roll back a newly created target on failure, and report read-back evidence.
- CTA creation is always opt-in and explicit. Caption tools must honor an explicit cutoff and never create or alter a CTA by implication.
- PC_PERSONALE and PC_SEGRETERIA remain separate deployments; nothing propagates between them automatically.
