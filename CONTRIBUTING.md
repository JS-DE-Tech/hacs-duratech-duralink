# Contributing

Thank you for helping build the Duratech DuraLink integration.

## Development Principles

- Use the documentation in `docs/` as the source of truth.
- Keep all future commands routed through Coordinator -> CommandManager -> PowerController -> Protocol -> TCP client.
- Do not let entities call the TCP client directly.
- Do not add direct Shelly API support. Shelly devices must be represented as Home Assistant switch entities.
- Do not implement KNX runtime behavior until the architecture is ready for it.
- Preserve the mandatory Light OFF invariant documented in `docs/architecture.md`.

## Quality

- Keep changes small and focused.
- Use async Home Assistant patterns.
- Add tests for runtime behavior when implementation begins.
- Run Home Assistant validation tools before release.
