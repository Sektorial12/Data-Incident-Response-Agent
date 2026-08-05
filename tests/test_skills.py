"""Tests for the DataHub skills loader."""

from src.skills.loader import augment_prompt, load_skill_guidance


class TestSkillsLoader:
    def test_load_lineage_skill_returns_content(self):
        guidance = load_skill_guidance("datahub-lineage")
        assert len(guidance) > 0
        assert "lineage" in guidance.lower() or "DataHub" in guidance

    def test_load_quality_skill_returns_content(self):
        guidance = load_skill_guidance("datahub-quality")
        assert len(guidance) > 0
        assert "quality" in guidance.lower() or "assertion" in guidance.lower()

    def test_load_enrich_skill_returns_content(self):
        guidance = load_skill_guidance("datahub-enrich")
        assert len(guidance) > 0
        assert "enrich" in guidance.lower() or "metadata" in guidance.lower()

    def test_unknown_skill_returns_empty(self):
        guidance = load_skill_guidance("nonexistent-skill")
        assert guidance == ""

    def test_augment_prompt_appends_guidance(self):
        base = "You are a test agent."
        augmented = augment_prompt(base, "datahub-lineage")
        assert augmented.startswith(base)
        assert "Skill Guidance" in augmented
        assert len(augmented) > len(base)

    def test_augment_prompt_unknown_skill_returns_base(self):
        base = "You are a test agent."
        augmented = augment_prompt(base, "nonexistent")
        assert augmented == base
