"""Offer Agent: generates approved employment contracts from a hiring
approval, candidate CV, optional passport, and user overrides.

This package implements only the deterministic, rule-governed mechanics of
the workflow (template selection, salary math, reference generation,
filename/conflict handling, DOCX population, PDF conversion, and audit
logging). Free-text extraction from source documents and priority/conflict
resolution across sources is a language-understanding task performed by the
calling agent (see .claude/skills/offer-agent/SKILL.md) — this package never
guesses or infers field values on its own.
"""
