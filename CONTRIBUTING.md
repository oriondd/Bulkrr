# Contributing to Bulkrr

Thanks for your interest in improving Bulkrr! This is an early-beta Windows desktop app for reviewing and bulk-adding titles to Radarr and Sonarr. Bug reports, documentation fixes, testing, and code contributions are welcome.

## Report a bug

Before opening an issue, check whether someone has already reported it. [Open an issue](https://github.com/oriondd/Bulkrr/issues) with:

- Bulkrr version and Windows version
- Whether the problem involves Radarr, Sonarr, or both
- Steps to reproduce, including sample titles when useful
- Expected behavior and actual behavior
- Screenshots or a short, **redacted** excerpt from the Activity Log

**Privacy:** Never share API keys, passwords, tokens, private server addresses, or personal library details you do not want public. Review screenshots and logs carefully before posting.

## Suggest a feature

[Open an issue](https://github.com/oriondd/Bulkrr/issues) describing the problem you want to solve, the behavior you propose, and how it would improve the Bulkrr workflow. For substantial changes, discuss the idea in an issue before investing time in a pull request.

## Contribute code

1. Fork the repository and create a branch for your change.
2. Use Python 3.12 and install dependencies from `requirements.txt` in a virtual environment.
3. Keep changes focused and explain why they are needed. Use readable formatting, descriptive names, and avoid unrelated refactoring.
4. Run `python -m py_compile bulkrr.py` to catch syntax errors. If you can, test the changed workflow on Windows against Radarr/Sonarr instances you control.
5. Open a pull request against `main` with a summary, testing notes, and screenshots for visible UI changes.

Example setup on Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python bulkrr.py
```

If your environment prevents PowerShell script activation, you can run `.venv\Scripts\python.exe` directly instead.

## Pull request checklist

- [ ] The change has a clear purpose and avoids unrelated edits
- [ ] Existing import, duplicate-detection, and review behavior is preserved or changes are clearly explained
- [ ] Syntax check passes
- [ ] Windows testing is described, or limitations are stated honestly
- [ ] No credentials, personal settings, logs, or private URLs are included
- [ ] Documentation is updated if behavior or installation changes

## Safety and compatibility

Bulkrr talks to Radarr and Sonarr APIs. Avoid destructive actions against users' libraries. In particular, do not change the existing **Replace / Search Again** behavior to delete media without explicit design discussion, safeguards, and clear user consent. Prefer safe defaults and preserve review-before-import behavior.

## License

By submitting a contribution, you agree that your contribution will be made available under the project's [MIT License](LICENSE). Please only submit code and assets you have the right to contribute.

Thanks for helping make Bulkrr better!

— DOM
