# Pipeline Export Fill Rules

## Evidence Priority

1. DataEngine/waterline technical document embedded Excel and Word tables.
2. DataEngine/waterline technical document paragraphs near the embedded table.
3. PRD tables and paragraphs.
4. User-confirmed overrides.
5. Production Excel examples, only for schema/style reference unless the user explicitly authorizes copying business values.

## Data Utilization

- Use unique `report_targets[*].data_utilization`.
- Ignore noisy `data_utilizations` rows extracted from unrelated field dictionaries unless they also appear in `report_targets`.
- If no description is available, leave `data_utilization_description` blank.

## Target & Catalog

- Use `report_targets` as the target list.
- Merge physical table evidence from `report_physical_targets` by exact physical table, target table suffix, or description.
- Use the `target_name` already present in `report_targets`; do not rename it to the physical table.
- Keep catalog owner/email/source fields blank unless explicitly present in the current project document or user input.
- If paragraph text claims a target count that conflicts with extracted target rows, keep extracted rows and add a question.

## Target Field

- Use `report_field_mappings`.
- For duplicate target dictionaries, prefer entries from the DataEngine/waterline document over PRD entries.
- Include only mappings whose target appears in `Target & Catalog`.
- Set:
  - `field_name` from target field/key.
  - `field_label` from Chinese/business label when available; otherwise use the field key.
  - `field_description` from calculation logic when available.
  - `field_type` using the schema mapping.
  - `field_sequence` from 0 in target-local order.
- Do not invent missing fields for targets without a field dictionary; add a question instead.

## Pipeline

- Use `report_schedules`.
- Set `enable = 1`, `is_octopus = 0`.
- Convert daily schedules like `每天早上9:00` or `每天 09:30` to `每1天 HH:mm`.
- Leave period schedules such as `PnW2D2 早上9:00` blank unless the user confirms the platform trigger syntax.
- Leave `task1_link_target_names` and `task1_mlp_params` blank when not explicitly confirmed.
- Use `pipeline_status_notification = FINISHED,FAILED` as the conservative default only when the document does not provide a value.

## Questions

Always write questions for:

- Conflicting target counts.
- Targets without field dictionaries.
- Period or pending schedules.
- Blank task-target links.
- Blank MLP params.
- Blank owner/email/catalog fields when the target appears to require catalog registration.
