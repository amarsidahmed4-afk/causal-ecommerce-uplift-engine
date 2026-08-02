"""
Pytest configuration. Must set environment variables here, before any test
module imports `config.settings` — Settings() reads os.environ at import
time, and as of v2.3 there is no insecure default API_KEY to fall back on.

conftest.py is collected by pytest before test modules in the same
directory, so this runs first as long as no other test file imports
config.settings at collection time outside of a test function.
"""
import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("API_KEY", "test-only-authoritative-key")
os.environ.setdefault("PUBLIC_API_KEY", "test-only-public-key")
