"""Tests for build_seed.build_seed_dict.

The Worker schema is the validator of record; these tests just confirm
build_seed_dict produces a structurally-complete seed from realistic inputs
and surfaces missing-input errors cleanly.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REFERENCES_DIR = Path(__file__).resolve().parent.parent / 'references'
sys.path.insert(0, str(REFERENCES_DIR))

import build_seed  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'
SAMPLE_DRAFT_PATH = FIXTURES_DIR / 'email-draft-sample.json'


def _minimal_ctx():
    return {
        'project_name': 'Test Temple Construction',
        'job_number': 'W9999',
        'contractual_completion': '2027-06-30',
        'projected_completion': '2027-07-15',
        'smartpm_url': '',
        'smartpm_trends_url': '',
        'smartpm_changelog_url': 'https://smartpm.example/changes',
        'smartpm_project_name': 'Test Temple',
        'signer_name': 'JANE DOE',
        'signer_title': 'PROJECT MANAGER',
        'signer_mobile': '801-555-0100',
        'procore_company_id': '11093',
        'procore_project_id': '',
        'procore_documents_folder_id': '',
        'graph_screenshots': [],
        'to_recipients': [{'name': 'Owner', 'email': 'owner@example.com'}],
        'cc_recipients': [],
        'to_recipients_str': 'Owner <owner@example.com>',
        'cc_recipients_str': '',
        'project_log': [],
    }


def _kwargs(**overrides):
    base = dict(
        ctx=_minimal_ctx(),
        prev_draft=None,
        today_iso='2026-05-28',
        projected_completion_iso='2027-07-15',
        days_metric_value=15,
        days_metric_direction='behind',
        gain_loss_value=3,
        gain_loss_direction='loss',
        gain_loss_narrative='SC slipped 3 days this week due to elevator delivery.',
        eot_recovery='Recovery plan unchanged.',
        logic_changes='No logic changes this week.',
        successes_html=['<div>Building slab pour complete.</div>'],
        red_flags_html=['<div>Material delivery slipping.</div>'],
        stalled_tasks_html=[],
        key_items_html=['<div>Confirm elevator submittal approval.</div>'],
        fresh_filenames=['Report 01 - Master Schedule 2026-05-28.pdf'],
    )
    base.update(overrides)
    return base


class BuildSeedShapeTests(unittest.TestCase):
    def test_returns_v2_top_level_keys(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        self.assertEqual(seed['version'], 2)
        self.assertEqual(seed['report_date'], '2026-05-28')
        self.assertIn('project_info', seed)
        self.assertIn('this_week', seed)
        self.assertIsNone(seed['last_week'])  # week-1 project

    def test_emits_smartpm_binding(self):
        # The Worker requires a smartpm binding on generate (validateSeed,
        # default requireSmartpm=True); a seed without it 422s. build_seed_dict
        # must emit it from ctx['smartpm_project_name'].
        seed = build_seed.build_seed_dict(**_kwargs())
        self.assertIn('smartpm', seed)
        self.assertEqual(seed['smartpm']['project_name'], 'Test Temple')

    def test_project_info_required_fields_populated(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        pi = seed['project_info']
        for field in ('project_name', 'job_number',
                      'contractual_completion', 'projected_completion'):
            self.assertIn(field, pi)
            self.assertTrue(pi[field], f'project_info.{field} should be non-empty')

    def test_this_week_has_every_required_field(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        tw = seed['this_week']
        required = [
            'subject', 'to_recipients', 'cc_recipients',
            'days_metric', 'gain_loss',
            'successes', 'red_flags', 'stalled_tasks',
            'key_items', 'key_items_archived',
            'eot_recovery', 'logic_changes', 'smartpm_changelog_url',
            'closing_paragraphs', 'closing_salutation',
            'signer_name', 'signer_title', 'signer_mobile',
            'attachments', 'skip_procore',
            'include_changes_report', 'changes_report_filename',
            'graph_order',
        ]
        for field in required:
            self.assertIn(field, tw, f'this_week missing required field: {field}')

    def test_discriminators_are_in_enum(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        self.assertIn(seed['this_week']['days_metric']['direction'],
                      ('behind', 'ahead'))
        self.assertIn(seed['this_week']['gain_loss']['direction'],
                      ('gain', 'loss'))

    def test_graph_order_defaults_to_canonical(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        self.assertEqual(seed['this_week']['graph_order'],
                         build_seed.CANONICAL_GRAPH_ORDER)

    def test_closing_paragraphs_default_to_questions(self):
        seed = build_seed.build_seed_dict(**_kwargs())
        cp = seed['this_week']['closing_paragraphs']
        self.assertTrue(len(cp) >= 1)
        self.assertEqual(cp[0]['label'], 'Questions')
        self.assertTrue(cp[0]['checked'])


class BuildSeedCarryForwardTests(unittest.TestCase):
    def test_last_week_is_prev_draft_this_week_verbatim(self):
        prev = json.loads(SAMPLE_DRAFT_PATH.read_text())
        seed = build_seed.build_seed_dict(**_kwargs(prev_draft=prev))
        self.assertEqual(seed['last_week'], prev['this_week'])

    def test_skip_procore_inherits_from_prev_week(self):
        prev = json.loads(SAMPLE_DRAFT_PATH.read_text())
        prev['this_week']['skip_procore'] = True
        seed = build_seed.build_seed_dict(**_kwargs(prev_draft=prev))
        self.assertTrue(seed['this_week']['skip_procore'])

    def test_graph_order_inherits_from_prev_week_when_present(self):
        prev = json.loads(SAMPLE_DRAFT_PATH.read_text())
        custom_order = ['08-velocity', '09-spi-over-time']
        prev['this_week']['graph_order'] = custom_order
        seed = build_seed.build_seed_dict(**_kwargs(prev_draft=prev))
        self.assertEqual(seed['this_week']['graph_order'], custom_order)


class BuildSeedErrorTests(unittest.TestCase):
    def test_missing_project_name_raises_clear_error(self):
        ctx = _minimal_ctx()
        ctx['project_name'] = ''
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(**_kwargs(ctx=ctx))
        self.assertIn('project_name', str(exc.exception))

    def test_missing_to_recipients_raises_clear_error(self):
        ctx = _minimal_ctx()
        ctx['to_recipients'] = []
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(**_kwargs(ctx=ctx))
        self.assertIn('to_recipients', str(exc.exception))

    def test_missing_smartpm_project_name_raises_clear_error(self):
        ctx = _minimal_ctx()
        ctx['smartpm_project_name'] = ''
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(**_kwargs(ctx=ctx))
        self.assertIn('smartpm_project_name', str(exc.exception))

    def test_invalid_days_metric_direction_raises(self):
        with self.assertRaises(ValueError):
            build_seed.build_seed_dict(**_kwargs(days_metric_direction='sideways'))

    def test_invalid_gain_loss_direction_raises(self):
        with self.assertRaises(ValueError):
            build_seed.build_seed_dict(**_kwargs(gain_loss_direction='neutral'))


if __name__ == '__main__':
    unittest.main()
