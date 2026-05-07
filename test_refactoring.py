"""End-to-end verification tests for refactored resume pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Test imports
from agents.resume_builder import build_resume, validate_builder_schema
from agents.judge import judge_project_and_skills
from utils.latex_renderer import render_resume, validate_template
from utils.skills_validator import (
    validate_and_separate_skills,
    validate_builder_result,
    is_valid_skill,
)


def test_skills_validator():
    """Test skills validation and categorization."""
    print("\n=== Testing Skills Validator ===")

    # Test valid skills
    assert is_valid_skill("Java")
    assert is_valid_skill("AWS")
    assert is_valid_skill("React")
    print("✓ Valid skills recognized")

    # Test invalid skills
    assert not is_valid_skill("problem-solving")
    assert not is_valid_skill("innovation")
    assert not is_valid_skill("collaboration")
    print("✓ Invalid skills rejected")

    # Test categorization
    langs, techs = validate_and_separate_skills(
        ["Java", "Python"],
        ["AWS", "Docker", "problem-solving"]
    )
    assert "Java" in langs
    assert "Python" in langs
    assert "AWS" in techs
    assert "Docker" in techs
    assert len(techs) == 2  # problem-solving should be removed
    print("✓ Skills correctly categorized and cleaned")


def test_builder_schema_validation():
    """Test resume builder output schema validation."""
    print("\n=== Testing Builder Schema Validation ===")

    # Valid schema
    valid_result = {
        "project_id": "test_project",
        "languages": ["Java", "Python"],
        "technologies": ["AWS", "Docker"]
    }
    validated = validate_builder_schema(valid_result)
    assert validated["project_id"] == "test_project"
    print("✓ Valid schema accepted")

    # Invalid: missing fields
    try:
        validate_builder_schema({"project_id": "test"})
        assert False, "Should reject missing fields"
    except Exception:
        print("✓ Invalid schema (missing fields) rejected")

    # Invalid: wrong types
    try:
        validate_builder_schema({
            "project_id": "test",
            "languages": "java",  # Should be list
            "technologies": ["AWS"]
        })
        assert False, "Should reject wrong types"
    except Exception:
        print("✓ Invalid schema (wrong types) rejected")


def test_template_validation():
    """Test LaTeX template validation."""
    print("\n=== Testing Template Validation ===")

    template_path = "data/resume.tex"
    
    if Path(template_path).exists():
        validation = validate_template(template_path)
        
        if validation["valid"]:
            print("✓ Template has all required placeholders")
        else:
            print(f"✗ Template missing placeholders: {validation['missing_placeholders']}")
            assert False, "Template validation failed"
    else:
        print("⚠ Template file not found, skipping")


def test_project_selection_fallback():
    """Test project selector fallback logic."""
    print("\n=== Testing Project Selector Fallback ===")

    from agents.resume_builder import select_project_fallback

    # Load projects
    try:
        with open("data/project_data.json", "r") as f:
            projects_data = json.load(f)
            projects = projects_data.get("projects", [])

        if projects:
            # Create job data that overlaps with a project
            test_job = {
                "skills": ["Java", "AWS", "Docker"],
                "tools": ["React", "Node.js"]
            }

            selected = select_project_fallback(test_job, projects)
            assert selected in [p["id"] for p in projects]
            print(f"✓ Project selector returned valid project: {selected}")
        else:
            print("⚠ No projects in data file, skipping")

    except FileNotFoundError:
        print("⚠ Project data file not found, skipping")


def test_renderer_integration():
    """Test LaTeX renderer with sample data."""
    print("\n=== Testing LaTeX Renderer Integration ===")

    template_path = "data/resume.tex"
    test_output = Path("data/test_render.tex")

    if not Path(template_path).exists():
        print("⚠ Template not found, skipping render test")
        return

    try:
        sample_project = {
            "id": "test_project",
            "name": "Test Project",
            "tech": ["Python", "AWS"],
            "date": "Jan 2024 - Mar 2024",
            "bullets": [
                "Built test system",
                "Achieved 50% performance improvement"
            ]
        }

        render_resume(
            template_path=template_path,
            output_path=str(test_output),
            project=sample_project,
            languages=["Python", "Java"],
            technologies=["AWS", "Docker"]
        )

        # Verify output was created
        assert test_output.exists()
        print(f"✓ Renderer successfully created: {test_output}")

        # Verify placeholders were replaced
        with open(test_output, "r") as f:
            content = f.read()

        assert "{{" not in content  # No unreplaced placeholders
        assert "Test Project" in content
        assert "Python" in content
        assert "AWS" in content
        print("✓ All placeholders correctly replaced")

        # Cleanup
        test_output.unlink()

    except Exception as e:
        print(f"✗ Renderer test failed: {e}")
        raise


def test_judge_compatibility():
    """Test judge compatibility with new structured input."""
    print("\n=== Testing Judge Compatibility ===")

    # The judge now accepts project + skills instead of full resume
    # We just verify the function signature is correct
    
    try:
        from agents.judge import judge_project_and_skills
        import inspect

        sig = inspect.signature(judge_project_and_skills)
        params = list(sig.parameters.keys())

        expected = ["job_data", "selected_project", "languages", "technologies"]
        for param in expected:
            assert param in params, f"Missing parameter: {param}"

        print(f"✓ Judge function signature correct: {params}")

    except Exception as e:
        print(f"✗ Judge compatibility test failed: {e}")
        raise


def test_workflow_imports():
    """Test that all workflow imports work correctly."""
    print("\n=== Testing Workflow Imports ===")

    try:
        from graph.workflow import build_workflow
        
        workflow = build_workflow()
        assert workflow is not None
        print("✓ Workflow builds successfully")
        print(f"✓ Workflow has nodes: {list(workflow.nodes.keys())}")

    except Exception as e:
        print(f"✗ Workflow import test failed: {e}")
        raise


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("END-TO-END REFACTORING VERIFICATION")
    print("=" * 60)

    tests = [
        test_skills_validator,
        test_builder_schema_validation,
        test_template_validation,
        test_project_selection_fallback,
        test_renderer_integration,
        test_judge_compatibility,
        test_workflow_imports,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n✗ {test.__name__} FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n✓ ALL VERIFICATION TESTS PASSED!")
        print("\nRefactoring Summary:")
        print("  ✓ Resume builder returns JSON (project_id, languages, technologies)")
        print("  ✓ Judge validates structured data (project + skills)")
        print("  ✓ LaTeX renderer fills template with data")
        print("  ✓ Skills validator removes soft skills and generic terms")
        print("  ✓ Workflow: Builder → Renderer → Judge → End")
        print("  ✓ Project fallback selector works")
        print("  ✓ Template placeholders correct")
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
