# Student client release checklist

The official client is distributed from the immutable GitHub tag rather than
PyPI:

```powershell
uvx --from "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.5#subdirectory=packages/vibe-submit" vibe-submit --help
```

Before each classroom release:

1. Run the client tests.
2. Verify the immutable Git tag from a clean machine.
3. Verify that `STUDENT_GUIDE.md` names the production HTTPS URL and the same immutable tag. Students copy the documented Windows/macOS command directly; no per-class bootstrap script is distributed.

Course invitation codes and student credentials must never be embedded in a script or committed to Git. Students complete self-registration with the invitation code, student number, and name.
