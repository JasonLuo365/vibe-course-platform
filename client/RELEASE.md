# Student client release checklist

The official client is distributed from the immutable GitHub tag rather than
PyPI:

```powershell
uvx --from "git+https://github.com/JasonLuo365/vibe-course-marketplace.git@v0.1.2#subdirectory=packages/vibe-submit" vibe-submit --help
```

Before each classroom release:

1. Run the client tests.
2. Verify the immutable Git tag from a clean machine.
3. Generate a bootstrap script after the production HTTPS URL is available:

```powershell
.\ops\render-bootstrap.ps1 `
  -MarketplaceUrl 'https://github.com/JasonLuo365/vibe-course-marketplace.git' `
  -ServerUrl 'https://vibe.planlabopc.com' `
  -Version '0.1.2' `
  -OutputPath '.\release\bootstrap.ps1'
```

Do not put student tokens in the generated script. Send each token privately.
