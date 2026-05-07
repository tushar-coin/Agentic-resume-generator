import re

template = "{{PROJECT_BULLETS}}"
bullets_replacement = "\\resumeItemListStart\n\\resumeItem{test}\n\\resumeItemListEnd"

print("Original replacement:")
print(repr(bullets_replacement))

# WRONG - re.sub interprets backslashes in replacement
result_wrong = re.sub(r"{{PROJECT_BULLETS}}", bullets_replacement, template)
print("\n❌ re.sub (BROKEN):")
print(repr(result_wrong))

# CORRECT - use str.replace or re.escape
result_correct = template.replace("{{PROJECT_BULLETS}}", bullets_replacement)
print("\n✓ str.replace (CORRECT):")
print(repr(result_correct))
