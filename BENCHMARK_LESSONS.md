# Lessons captured from extraction-platform development

## IMPL-EXT-003a-fix1: regex parameter injection is unsafe

The original 003a refactor used a regex pattern to inject a 
`cache_dir: str = None` parameter into 12 function signatures. 
The regex pattern was:

    r"((?:async )?def " + func + r"\b\([^)]*)\):"

This pattern failed silently on:
- Multi-line function signatures
- Signatures using FastAPI's Depends() default values
- Signatures with -> ReturnType: annotations

Of 12 target functions, 9 went unmodified. The defect was not 
caught by 003a's behaviour-equivalence proofs because the proofs 
tested function imports and basic invocations, not the new 
parameter pathway.

## Rule for future bulk parameter-injection tickets

- For modifications affecting more than 5 functions: use AST-based 
  transformations (libcst, ast.NodeTransformer) rather than regex.
- For modifications affecting fewer functions: hand-edit each 
  signature.
- Verification must explicitly invoke each modified function with 
  the new parameter set, not merely import it.

## Cross-references
- IMPL-EXT-003a (the original defect)
- IMPL-EXT-003a-fix1 (the corrective ticket)
- IMPL-EXT-003b (the ticket that surfaced the defect)
