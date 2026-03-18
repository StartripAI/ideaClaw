# Contributing to IdeaClaw

Thank you for contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/StartripAI/ideaClaw.git
cd ideaClaw
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Code Style

- Python 3.11+, PEP 8
- Type hints on all public functions
- Docstrings on all classes and public methods
- `from __future__ import annotations` in every module

## Adding a Quality Profile

1. Create `ideaclaw/quality/profiles/{domain}/{scene}.yaml`
2. Follow the format in [docs/profile-guide.md](docs/profile-guide.md)
3. Add auto-detection keywords to `ideaclaw/quality/loader.py` (optional)
4. Run `ideaclaw profiles --domain {domain}` to verify

## Adding a Pack Template

1. Create `ideaclaw/pack/templates/{type}.md.j2`
2. Register in `ideaclaw/pack/schema.py`
3. Available template variables: `idea`, `conclusion`, `reasoning`, `counterarguments`, `uncertainties`, `action_items`, `sources`, `claims`, `trust`, `date`, `run_id`, `version`, `profile_id`

## Testing

```bash
# Syntax check
python -c "import ast, pathlib; [ast.parse(f.read_text()) for f in pathlib.Path('ideaclaw').rglob('*.py')]"

# Import test
python -c "from ideaclaw.quality import load_profile; print(load_profile('cs_ml.icml').name)"

# CLI smoke test
ideaclaw profiles --domain general
```

## Pull Request Process

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Ensure syntax and imports pass
5. Submit PR with description of changes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
