# Vibe Course Marketplace

This repository distributes the `vibe-submit` Codex plugin and its Python
client. The plugin installs its client directly from a fixed GitHub tag, so it
does not depend on PyPI being available.

## Version mapping

| Plugin version | Client version | Git tag |
| --- | --- | --- |
| 0.1.0 | 0.1.0 | `v0.1.0` |

Do not overwrite a tag that has been given to students. Publish a new version
and a new immutable tag for every classroom release.

## Validate the GitHub distribution

From a machine that has not previously installed the client:

```powershell
uvx --from "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.0#subdirectory=packages/vibe-submit" vibe-submit --help
```

PyPI may later be used as an additional package-distribution channel, but the
Marketplace configuration should continue to use the reviewed GitHub release.

