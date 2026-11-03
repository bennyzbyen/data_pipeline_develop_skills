#!/usr/bin/env python3
"""Bounded multi-source conversion, join invariants and execution timing regressions."""
from __future__ import annotations

from pipeline_test_support import SOURCE_ROOT, EVALUATION_TOOLS

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = SOURCE_ROOT.resolve()
sys.path[:0] = [str(ROOT / 'skills/report-codegen/scripts'), str(ROOT / 'skills/data-doc-to-dev-md/scripts')]
from build_report_codegen_plan import build_plan
sys.path.insert(0, str(EVALUATION_TOOLS))
from requirement_conversion import evidence_digest, validate_conversion
from scaffold_report_project import scaffold
import report_sample_workflow as workflow


def fixture(aggregate=True):
    """All rules/cardinality here are synthetic declarations, never business defaults."""
    fields = [{'target_field': name, 'field_name': name, 'source_field': source, 'source_desc': table,
               'source_table': table, 'field_type': '', 'calculation_logic': logic}
              for name, source, table, logic in (
                ('store', 'store', 'fixture.population', 'copy'), ('period', 'period', 'fixture.population', 'copy'),
                ('base_amount', 'amount', 'fixture.population', 'copy'), ('detail_amount', 'amount', 'fixture.detail', 'sum by store and period'),
                ('target', 'target', 'fixture.detail', 'max by store and period'),
                ('rate', '', 'internal', 'left join on store+period; detail amount / target; missing or zero target stays null'))]
    sources = {'population': {'kind': 'injected', 'columns': ['store', 'period', 'amount']},
               'detail': {'kind': 'injected', 'columns': ['store', 'period', 'amount', 'target']}}
    condition = [{'column': 'period', 'operator': 'eq', 'value_from': 'params.period'},
                 {'column': 'store', 'operator': 'notnull'}, {'column': 'period', 'operator': 'notnull'}]
    steps = [{'id': 'population_scope', 'op': 'filter', 'input': 'population', 'conditions': copy.deepcopy(condition)},
             {'id': 'detail_scope', 'op': 'filter', 'input': 'detail', 'conditions': copy.deepcopy(condition)}]
    graph = [{'input': 'source.population'}, {'input': 'source.detail'}]
    if aggregate:
        steps.append({'id': 'summary', 'op': 'aggregate', 'input': 'detail_scope', 'group_by': ['store', 'period'],
                      'aggregations': {'amount': {'column': 'amount', 'agg': 'sum'}, 'target': {'column': 'target', 'agg': 'max'}}})
        graph.append({'input': 'step.1'})
    right = len(steps) - 1
    steps.extend([{'id': 'joined', 'op': 'join', 'left': 'population_scope', 'right': steps[right]['id'],
                   'on': ['store', 'period'], 'how': 'left', 'validate': 'one_to_one', 'suffixes': ['_base', '_detail']},
                  {'id': 'derived', 'op': 'derive', 'input': 'joined', 'columns': {'rate': {
                      'op': 'divide', 'operands': [{'column': 'amount_detail'}, {'column': 'target'}]}}},
                  {'id': 'projected', 'op': 'project', 'input': 'derived', 'columns': ['store', 'period', 'rate']}])
    graph.extend([{'left': 'step.0', 'right': 'step.' + str(right)}, {'input': 'step.' + str(right + 1)}, {'input': 'step.' + str(right + 2)}])
    data = {'population': [{'store': 'A', 'period': 'P1', 'amount': 100}, {'store': 'A', 'period': 'P2', 'amount': 200},
                           {'store': 'B', 'period': 'P1', 'amount': 400}],
            'detail': [{'store': 'A', 'period': 'P1', 'amount': 2, 'target': 2},
                       {'store': 'A', 'period': 'P1', 'amount': 4, 'target': 2},
                       {'store': 'A', 'period': 'P2', 'amount': 8, 'target': 2},
                       {'store': 'C', 'period': 'P1', 'amount': 22, 'target': 1}]}
    if not aggregate:
        data['detail'].pop(1)
    output = ['store', 'period', 'rate']
    contract = {'version': 1, 'sources': sources, 'steps': steps,
                'outputs': {'offline_result': {'input': 'projected', 'columns': output}},
                'writes': {'offline_result': {'kind': 'clickhouse', 'mode': 'append', 'table': 'fixture.result'}}}
    source_bindings = {'population': ['store', 'period', 'base_amount'], 'detail': ['detail_amount', 'target']}
    reference = {'document_sha256': ['a' * 64], 'business_approved': False, 'full_report_ready': False,
                 'evidence': {field['target_field']: evidence_digest(field) for field in fields},
                 'rules': [{'id': 'joined_rate', 'target_field': 'rate', 'outcome': 'fragment'}],
                 'pending_ids': ['BUSINESS_APPROVAL'], 'output_fields': output, 'graph': graph,
                 'source_bindings': source_bindings, 'fixture_inputs': {'source_data': copy.deepcopy(data), 'params': {'period': 'P1', 'current_date': '2024-02-01'}},
                 'contract_checks': []}
    for source, spec in sources.items():
        reference['contract_checks'].append({'path': ['sources', source, 'columns'], 'equals': list(spec['columns'])})
    for index, step in enumerate(steps):
        for key, value in step.items():
            if key not in {'id', 'input', 'left', 'right'}:
                reference['contract_checks'].append({'path': ['steps', index, key],
                    'unordered_equals' if key == 'conditions' else 'equals': copy.deepcopy(value)})
    reference['contract_checks'].append({'path': ['outputs', 'offline_result', 'columns'], 'equals': output})
    candidate = {key: copy.deepcopy(reference[key]) for key in ('document_sha256', 'business_approved', 'full_report_ready', 'rules', 'pending_ids', 'output_fields', 'source_bindings')}
    candidate.update(version=1, kind='document_rule_candidate', fixture_only=True, candidate_origin='assistant_session_candidate',
                     bindings=[{'target_field': name, 'evidence_sha256': digest} for name, digest in reference['evidence'].items()],
                     execution_contract=contract, source_data=data, params=copy.deepcopy(reference['fixture_inputs']['params']))
    rows = [['A', 'P1', 3.0 if aggregate else 1.0], ['B', 'P1', None]]
    oracle = {'columns': output, 'rows': rows, 'write_events': [{'table': 'fixture.result', 'rows': 2, 'columns': output}]}
    return fields, candidate, reference, oracle


class MultiSourceAudit(unittest.TestCase):
    def reject(self, fields, candidate, reference, message):
        before = copy.deepcopy((fields, candidate, reference))
        result = validate_conversion(fields, candidate, reference)
        self.assertEqual('failed', result['status'], result)
        self.assertTrue(any(message in error for error in result['errors']), result)
        self.assertEqual(before, (fields, candidate, reference))

    def test_valid_two_source_join_and_aggregate_chain(self):
        for aggregate in (False, True):
            fields, candidate, reference, _ = fixture(aggregate)
            self.assertEqual('passed', validate_conversion(fields, candidate, reference)['status'])

    def test_wrong_or_missing_source_evidence_binding(self):
        for change in ('swap', 'drop', 'invent'):
            fields, candidate, reference, _ = fixture()
            if change == 'swap':
                candidate['source_bindings']['detail'], candidate['source_bindings']['population'] = candidate['source_bindings']['population'], candidate['source_bindings']['detail']
            elif change == 'drop':
                candidate.pop('source_bindings')
            else:
                candidate['source_bindings']['detail'].append('unreviewed_field')
            self.reject(fields, candidate, reference, 'source evidence')

    def test_missing_period_wrong_direction_or_unapproved_cardinality(self):
        for key, value in (('on', ['store']), ('how', 'inner'), ('validate', 'many_to_many'), ('suffixes', ['_detail', '_base'])):
            fields, candidate, reference, _ = fixture()
            candidate['execution_contract']['steps'][3][key] = value
            self.reject(fields, candidate, reference, 'contract rule differs')

    def test_swapped_join_sides_or_aggregation_bypass(self):
        for key, value in (('left', 'summary'), ('right', 'detail_scope')):
            fields, candidate, reference, _ = fixture()
            candidate['execution_contract']['steps'][3][key] = value
            self.reject(fields, candidate, reference, 'bypasses')

    def test_wrong_same_named_operand_is_rejected(self):
        fields, candidate, reference, _ = fixture()
        candidate['execution_contract']['steps'][4]['columns']['rate']['operands'][0]['column'] = 'amount_base'
        self.reject(fields, candidate, reference, 'columns')

    def test_wrong_aggregation_order_or_function_is_rejected(self):
        fields, candidate, reference, _ = fixture()
        candidate['execution_contract']['steps'][2]['aggregations']['amount']['agg'] = 'nunique'
        self.reject(fields, candidate, reference, 'aggregations')

    def test_filters_and_output_cannot_bypass_reviewed_steps(self):
        for output in (False, True):
            fields, candidate, reference, _ = fixture()
            if output:
                candidate['execution_contract']['outputs']['offline_result']['input'] = 'joined'
            else:
                candidate['execution_contract']['steps'][2]['input'] = 'detail'
            self.reject(fields, candidate, reference, 'bypasses')

    def test_consistent_step_renaming_is_allowed(self):
        fields, candidate, reference, _ = fixture()
        rename = {step['id']: 'new_' + step['id'] for step in candidate['execution_contract']['steps']}
        for step in candidate['execution_contract']['steps']:
            for key in ('id', 'input', 'left', 'right'):
                if key in step:
                    step[key] = rename.get(step[key], step[key])
        candidate['execution_contract']['outputs']['offline_result']['input'] = 'new_projected'
        self.assertEqual('passed', validate_conversion(fields, candidate, reference)['status'])

    def test_cyclic_future_or_dead_reviewed_dependencies_are_rejected(self):
        for endpoint in ('step.3', 'step.2', 'source.detail'):
            fields, candidate, reference, _ = fixture()
            reference['graph'][2]['input'] = endpoint
            self.reject(fields, candidate, reference, 'invalid conversion' if endpoint.startswith('step.') else 'bypasses')

    def test_unknown_source_and_invalid_id_are_rejected(self):
        for change in ('source', 'id'):
            fields, candidate, reference, _ = fixture()
            if change == 'source':
                reference['graph'][1]['input'] = 'source.unknown'
            else:
                candidate['execution_contract']['steps'][2]['id'] = 'population'
            self.reject(fields, candidate, reference, 'unknown source' if change == 'source' else 'invalid or reused')

    def test_union_cannot_be_misrepresented_as_a_unary_dependency(self):
        fields, candidate, reference, _ = fixture()
        candidate['execution_contract']['steps'][0]['op'] = 'union'
        self.reject(fields, candidate, reference, 'unsupported routing operation')


class GeneratedJoin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        for aggregate in (False, True):
            fields, candidate, reference, _ = fixture(aggregate)
            facts = workflow.fixture_facts(fields, candidate, validate_conversion(fields, candidate, reference))
            plan = build_plan(facts)
            path = cls.root / (str(aggregate) + '.json')
            workflow.write_json(path, plan)
            scaffold(path, cls.root / str(aggregate))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def replay(self, candidate, aggregate=True):
        return workflow.execute_generated(self.root / str(aggregate), candidate)[0]

    def test_preserves_population_unmatched_rows_and_same_named_field_origin(self):
        _, candidate, _, oracle = fixture()
        actual = self.replay(candidate)
        self.assertEqual(oracle['rows'], actual['rows'])
        self.assertEqual([oracle['rows']], actual['written_rows'])
        self.assertEqual(oracle['columns'], actual['columns'])

    def test_other_periods_and_unrelated_stores_do_not_change_results(self):
        _, candidate, _, oracle = fixture()
        candidate['source_data']['detail'].extend([{'store': 'A', 'period': 'P9', 'amount': 1000, 'target': 1},
                                                 {'store': 'Z', 'period': 'P1', 'amount': 9999, 'target': 1}])
        self.assertEqual(oracle['rows'], self.replay(candidate)['rows'])

    def test_input_permutation_preserves_values_by_declared_output_keys(self):
        _, candidate, _, oracle = fixture()
        for rows in candidate['source_data'].values():
            rows.reverse()
        actual = self.replay(candidate)
        self.assertEqual(sorted(oracle['rows']), sorted(actual['rows']))
        self.assertEqual([actual['rows']], actual['written_rows'])

    def test_declared_null_key_exclusion_and_empty_right_side(self):
        _, candidate, _, _ = fixture()
        candidate['source_data']['population'].append({'store': None, 'period': 'P1', 'amount': 9})
        candidate['source_data']['detail'].append({'store': None, 'period': 'P1', 'amount': 9, 'target': 1})
        self.assertEqual([['A', 'P1', 3.0], ['B', 'P1', None]], self.replay(candidate)['rows'])
        candidate['source_data']['detail'] = []
        self.assertEqual([['A', 'P1', None], ['B', 'P1', None]], self.replay(candidate)['rows'])

    def test_declared_join_cardinality_rejects_duplicate_keys(self):
        for source in ('population', 'detail'):
            _, candidate, _, _ = fixture(False)
            candidate['source_data'][source].append(candidate['source_data'][source][0].copy())
            writer = workflow.FakeWriter()
            with patch.object(workflow, 'FakeWriter', return_value=writer):
                with self.assertRaisesRegex(Exception, 'not a one-to-one merge'):
                    self.replay(candidate, False)
            self.assertEqual([], writer.events)

    def test_division_zero_null_and_existing_modules_remain_isolated(self):
        _, candidate, _, _ = fixture()
        candidate['source_data']['detail'][0]['target'] = candidate['source_data']['detail'][1]['target'] = 0
        self.assertEqual([['A', 'P1', None], ['B', 'P1', None]], self.replay(candidate)['rows'])
        _, fresh, _, oracle = fixture()
        self.assertEqual(oracle['rows'], self.replay(fresh)['rows'])

    def test_timing_covers_import_input_process_storage_and_capture_without_changing_payload(self):
        _, candidate, _, oracle = fixture()
        before = copy.deepcopy(candidate)
        timings = {}
        actual, _ = workflow.execute_generated(self.root / 'True', candidate, timings)
        self.assertEqual({'dependency_import', 'project_import', 'input_build', 'source', 'process', 'storage', 'result_capture'}, set(timings))
        self.assertTrue(all(value >= 0 for value in timings.values()))
        self.assertEqual(oracle['rows'], actual['rows'])
        self.assertEqual(before, candidate)
