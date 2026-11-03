# Offline Report Evaluation — Development Tools

These helpers belong to the source checkout and are not distributed in the PipelineForge plugin. Use a local corpus to replay real document structures against frozen expectations. Keep original documents, deidentification maps, provenance locators, and sample outputs outside packaged source. A deidentified subset must preserve the selected table layout, row/field order, source-reference structure, and unresolved identities; masking a logical label must not turn it into a confirmed physical identifier.

Read expectations independently from the original tables before running the extractor. Freeze document and oracle SHA256 values. Changing either requires reviewing and freezing a new baseline, rather than accepting the latest extractor output as the expected answer.

## Corpus Format

`manifest.json` has `version: 1`, a non-empty `cases` list, `scope`, `excluded_scope`, and `business_formula_gold_status`. Each case has a unique alphanumeric/underscore/hyphen `id`, corpus-relative `input` and `expected` paths, their `input_sha256` and `expected_sha256`, `oracle_status`, and `human_business_approved`. Use `not_human_approved` until business logic has independent approval; the evaluator never grants approval.

Each expected JSON contains:

```json
{
  "sources": [{"storage": "hbase", "location": "db_001.table_001", "identity_status": "confirmed"}],
  "targets": [{"storage": "clickhouse", "location": "db_002.table_002"}],
  "field_keys": ["field_001", "field_002"],
  "source_fields": ["db_001.table_001.field_001", ""]
}
```

`identity_status` must match the documented identity, including `needs_confirmation` for logical labels. Preserve blank source fields. The baseline uses redacted/unconfirmed business rules, so its extracted contract must remain blocked for full code generation.

## Replay

From the source repository root:

```text
python scripts/devtools/report_evaluation/evaluate_report_samples.py --corpus <local-corpus> --out <separate-output-directory>
```

Use `--source-root <frozen-source-snapshot>` to compare the same corpus with an earlier implementation. The helper verifies input/oracle hashes and rejects paths outside the corpus. It extracts each DOCX, compares source inventory and identity status, physical targets, ordered output fields, and declared source-field text, then writes `evaluation.json`.

The schema replay projects the frozen field list from an injected source. A derived negative case removes one declared input field. `false_allows` counts accepted missing-field mutations; `false_blocks` counts rejected valid schema replays. These are structural checks derived from real documents, not observed business defects or a production accuracy estimate. Formula values, live model workflows, production connections, and deployment require separate evidence.

## Version 2: Document-To-Write Replay

Version 1 remains compatible. Version 2 uses `inputs: [{"path": "case/input.docx", "sha256": "<SHA256>"}]` per case and supports mixed DOCX/Markdown inputs in one extraction. Each case also declares `expected`, `expected_sha256`, and `expected_document_outcome` (`blocked` or `allowed`). Optional `workflow` / `workflow_sha256` identify a separately frozen normalization fixture. All paths remain inside the corpus; evaluation output must be outside it.

The expected JSON contains `sources`, `targets`, `document_ready_for_codegen`, and ordered `fields`. Each field records `target_field`, `source_field`, `source_desc`, `source_table`, `calculation_logic`, and `field_type`. Preserve raw text and line breaks in these independent oracles. Comparison retains exact ordered target identifiers and normalizes prose whitespace according to the extraction convention. Source inventory checks cover explicit inventory tables; inferred sources require separate reviewed expectations and are not promoted to approved inventory by this evaluation.

An optional direct-copy workflow declares `version: 1`, `kind: document_declared_direct_copy`, `fixture_only: true`, explicit `bindings` of target/source fields, a bounded `execution_contract`, synthetic `source_data`, and fixed `params`. It permits injected sources and append-only writes to `fixture.result`. `offline_output` in the independent expected JSON freezes ordered `columns`, `rows`, and fake `write_events` (`table`, `rows`, `columns`). Compute expected values independently; never execute the candidate DSL to manufacture its expected answer.

Replay stages are:

1. Verify hashes for every input, oracle, and workflow specification.
2. Extract once into the original three-file handoff; compare facts and exercise the actual document planning gate.
3. For a declared workflow, bind its selected fields to actual extracted evidence and create a separate, explicitly labeled evaluation handoff. Original business readiness and artifacts remain unchanged.
4. Build the real report plan, scaffold trusted templates, compile generated Python, and run project, observability, and generated-safety validation.
5. Execute generated source/process/storage components with injected rows, blocked socket connections, and fake writes. Compare both processing results and the ordered rows/columns handed to the writer.
6. Recheck frozen member hashes and continue independent cases after a case failure. Report the failing stage and per-stage timings.

The report distinguishes requested, executed, and passing workflows, structural differences, document false allows, fixture plan/scaffold false blocks, integrity failures, and runtime/output failures. Format variants share the original-document identity and do not count as independent real documents. A complete direct-copy fixture does not confirm the full business report, unresolved formulas, or a live model workflow.

## Evidence-Bound Rule Conversion

Version 2 also accepts `kind: document_rule_candidate`. Author and freeze the document reference and expected values before writing this candidate. Record `candidate_origin: assistant_session_candidate` when the current assistant session authors it; this is a local session replay, not a measured provider/model accuracy rate. Preserve meaningful deidentified formula text, rule versions, thresholds, inclusivity, zero/null behavior, date scope, and grouping grain. If redaction hides a version label or upstream binding, record that dependency as pending.

The expected JSON adds a `conversion` object:

- `document_sha256`: ordered input hashes, verified against the case inputs.
- `business_approved: false`, `full_report_ready: false`: fixture evaluation cannot grant approval.
- `evidence`: target-to-SHA256 map. Use `requirement_conversion.evidence_digest` on independently reviewed field records with `target_field`, `field_name`, `source_field`, `source_desc`, `source_table`, `calculation_logic`, and `field_type`. The digest normalizes whitespace only; names and formula details remain case-sensitive.
- `rules`: objects with `id`, `target_field`, and `outcome` (`fragment` or `pending`). `pending_ids` lists unresolved dependencies; keep upstream, version, rounding-policy, and business-approval gaps explicit.
- `output_fields`: ordered fixture output fields. For a supported fragment, `fixture_inputs` freezes `source_data` and `params`, and `contract_checks` independently declares each semantic property. Each check has a string/integer `path` into the contract and `equals`, or `unordered_equals` for an order-insensitive list of conjunctive filters. Record the exact expression operands, grouping/aggregation, date/status filters, source columns, and output projection. Include every semantic step property; do not derive the assertions or expected values by executing the candidate.
- For an unresolved rule, set `output_fields: []`, `contract_checks: []`, and record its factual `pending_spec` instead of an executable contract. Preserve ambiguous operands and unsupported cap/round/tier details without choosing an unconfirmed interpretation.

The candidate declares `version: 1`, `kind`, `fixture_only: true`, `candidate_origin`, the same document hashes, both false approval flags, `bindings: [{"target_field": "field_001", "evidence_sha256": "<SHA256>"}]`, the reviewed `rules`, `pending_ids`, and `output_fields`. A fragment additionally declares the frozen `source_data`/`params` and its separately authored `execution_contract`; a pending candidate carries only the factual `pending_spec`. Never copy `contract_checks` or expected outputs into the candidate.

Without a reviewed `graph`, the audit retains bounded linear fixtures with one injected column-only source. Every step consumes its predecessor. With a reviewed `graph`, it also audits bounded multi-source fixtures using existing unary operations and joins. Both shapes require a single `offline_result` output consuming the final step, append-only ClickHouse fake writes to `fixture.result`, and contract version 1 without write coercion. Unchecked steps/properties, changed input rows, dropped pending dependencies, incorrect rule bindings, or changed formula details fail before planning. Filter order may differ; Boolean and numeric literals remain distinct.

For multi-source conversion, the reference adds `source_bindings`, mapping every source alias to a non-empty list of reviewed field identifiers in `evidence`, and `graph`, an ordered list of routing objects. The candidate must declare the same `source_bindings`; the frozen reference owns the dependency graph. For example:

```json
{
  "source_bindings": {"population": ["field_001"], "detail": ["field_002"]},
  "graph": [
    {"input": "source.population"},
    {"input": "source.detail"},
    {"left": "step.0", "right": "step.1"},
    {"input": "step.2"}
  ]
}
```

`source.<alias>` names an injected source; `step.<zero-based-index>` names an earlier reviewed step. Unary steps use `input`; joins use `left` and `right`. Step IDs may be renamed consistently. Cycles, forward references, reused IDs, unknown/unused sources, and steps outside the final output's dependency chain fail the audit. Include exact join direction, complete composite keys (`on` or `left_on`/`right_on`), operand origin for colliding column names, suffixes/cardinality when declared, and aggregation order/functions in `contract_checks`. This is reviewed fixture routing, not a new production DSL or automatic prose-to-graph parser.

Do not infer join cardinality, deduplicate duplicate keys, drop null keys, or fill unmatched values without evidence. Record unknown raw-source/key bindings, grain, calendars, null-key policy and business approval in `pending_ids`. A fragment with controlled synthetic inputs may exercise the explicit documented rule while preserving those gaps; a request depending on an unresolved policy remains pending with factual details in `pending_spec`. Pending candidates cannot carry executable contracts or source bindings. Distinguish variants of the same document from independent evidence, and independently compute expected left-join coverage and formula values before authoring the candidate.

Replay adds `conversion_audit` before normalization. A supported fragment must pass that audit and the full existing plan/scaffold/runtime/write checks. A correctly preserved pending rule returns `workflow.status: pending` without creating an evaluation handoff, plan, project, or write. The original document remains blocked. `workflow_evaluated`, `workflow_executed`, `workflow_passed`, and `workflow_pending` are separate counts; pending preservation is a passing case but is never counted as executed or as a passing runtime workflow. `conversion_checked`/`conversion_failures` report conversion coverage and failures. Existing version 1 corpora and version 2 direct-copy fixtures keep their behavior.

These assertions check the reviewed properties and finite synthetic examples, not arbitrary semantic equivalence. Keep requirements with conflicting operands, unknown period calendars or raw-source bindings, and unsupported rounding/classification pending. Business approval, production value parity, and repeatable provider/model evaluation remain separate evidence.

## Execution Timing

Successful executed workflows add `execution_seconds` for `dependency_import`, `project_import`, `input_build`, `source`, `process`, `storage`, and `result_capture`. The storage phase uses fake writes; capture includes snapshots used to compare process and write payloads. Existing `stage_seconds.execute_and_compare` also includes orchestration, comparison and artifact output, so these phase values need not sum exactly to that stage. Failed executions report only completed phases; pending rules have no execution phases. Timings do not change value/write checks or relax module isolation and network blocking.

Compare a fresh process's first call separately from repeated warm calls at fixed synthetic scales. A fresh process does not imply cold OS caches. Verify exact row/column/write payloads before comparing timings. Optimize only a reproducible hotspot; dependency startup or evaluation snapshot cost is not production formula throughput, and noisy timings do not establish a speedup.
