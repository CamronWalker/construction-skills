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
    """Bindings-only ctx, as project_row_to_context would emit it.

    Post-refactor, ctx carries ONLY bindings: project_name, smartpm_*,
    procore_*. Recipients, signer, graph_order, contractual_completion, and
    job_number are NOT in ctx — they come from explicit args / prev_draft /
    Procore.
    """
    return {
        'project_name': 'Test Temple Construction',
        'smartpm_url': '',
        'smartpm_trends_url': '',
        'smartpm_changelog_url': 'https://smartpm.example/changes',
        'smartpm_project_name': 'Test Temple',
        'procore_company_id': '11093',
        'procore_project_id': '',
        'procore_documents_folder_id': '',
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
        # Explicit args that no longer live in ctx:
        job_number='W9999',
        contractual_completion='2027-06-30',
        # Week-1 conversational sourcing (prev_draft is None by default):
        to_recipients=[{'name': 'Owner', 'email': 'owner@example.com'}],
        cc_recipients=[],
        signer_name='JANE DOE',
        signer_title='PROJECT MANAGER',
        signer_mobile='801-555-0100',
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

    def test_ctx_recipients_and_signer_are_ignored(self):
        # Post-refactor, ctx supplies ONLY bindings. Stray recipient / signer /
        # graph_order / contractual keys left in ctx (e.g. from an old parse)
        # must NOT leak into the seed — those come from args / prev_draft only.
        ctx = _minimal_ctx()
        ctx.update({
            'to_recipients': [{'name': 'STALE', 'email': 'stale@example.com'}],
            'cc_recipients': [{'name': 'STALECC', 'email': 'stalecc@x.com'}],
            'signer_name': 'STALE SIGNER',
            'signer_title': 'STALE TITLE',
            'signer_mobile': '000-000-0000',
            'graph_order': ['stale-graph'],
            'contractual_completion': '1999-01-01',
            'job_number': 'STALE',
        })
        seed = build_seed.build_seed_dict(**_kwargs(ctx=ctx))
        tw = seed['this_week']
        # Recipients/signer come from the week-1 args, not ctx.
        self.assertEqual(tw['to_recipients'],
                         [{'name': 'Owner', 'email': 'owner@example.com'}])
        self.assertEqual(tw['signer_name'], 'JANE DOE')
        self.assertEqual(tw['signer_title'], 'PROJECT MANAGER')
        self.assertEqual(tw['signer_mobile'], '801-555-0100')
        self.assertEqual(tw['graph_order'], build_seed.CANONICAL_GRAPH_ORDER)
        # job_number / contractual_completion come from explicit args.
        self.assertEqual(seed['project_info']['job_number'], 'W9999')
        self.assertEqual(seed['project_info']['contractual_completion'],
                         '2027-06-30')


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
        # Week-1 (prev_draft None) with no to_recipients arg → error.
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(
                **_kwargs(prev_draft=None, to_recipients=[]))
        self.assertIn('to_recipients', str(exc.exception))

    def test_missing_job_number_raises_clear_error(self):
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(**_kwargs(job_number=''))
        self.assertIn('job_number', str(exc.exception))

    def test_missing_contractual_completion_raises_clear_error(self):
        with self.assertRaises(build_seed.SeedBuildError) as exc:
            build_seed.build_seed_dict(**_kwargs(contractual_completion=''))
        self.assertIn('contractual_completion', str(exc.exception))

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


class BuildSeedRecipientSourcingTests(unittest.TestCase):
    """Recipients / signer / graph_order sourcing contract:
    prev_draft carry-forward wins; explicit args are the week-1 fallback;
    ctx no longer carries any of them."""

    def test_week1_args_populate_recipients_and_signer(self):
        seed = build_seed.build_seed_dict(**_kwargs(
            prev_draft=None,
            to_recipients=[{'name': 'Owner A', 'email': 'a@example.com'},
                           {'name': 'Owner B', 'email': 'b@example.com'}],
            cc_recipients=[{'name': 'CC One', 'email': 'cc@example.com'}],
            signer_name='ALEX SCHEDULER',
            signer_title='SR SCHEDULER',
            signer_mobile='801-555-9999',
        ))
        tw = seed['this_week']
        self.assertEqual(len(tw['to_recipients']), 2)
        self.assertEqual(tw['to_recipients'][0]['email'], 'a@example.com')
        self.assertEqual(tw['cc_recipients'],
                         [{'name': 'CC One', 'email': 'cc@example.com'}])
        self.assertEqual(tw['signer_name'], 'ALEX SCHEDULER')
        self.assertEqual(tw['signer_title'], 'SR SCHEDULER')
        self.assertEqual(tw['signer_mobile'], '801-555-9999')

    def test_prev_draft_recipients_and_signer_win_over_args(self):
        prev = json.loads(SAMPLE_DRAFT_PATH.read_text())
        seed = build_seed.build_seed_dict(**_kwargs(
            prev_draft=prev,
            # These args should be IGNORED because prev_draft carries them.
            to_recipients=[{'name': 'SHOULD NOT', 'email': 'no@x.com'}],
            cc_recipients=[{'name': 'NOPE', 'email': 'nope@x.com'}],
            signer_name='IGNORE ME',
            signer_title='IGNORE TITLE',
            signer_mobile='000-000-0000',
        ))
        tw = seed['this_week']
        self.assertEqual(tw['to_recipients'],
                         prev['this_week']['to_recipients'])
        self.assertEqual(tw['cc_recipients'],
                         prev['this_week']['cc_recipients'])
        self.assertEqual(tw['signer_name'],
                         prev['this_week']['signer_name'])
        self.assertEqual(tw['signer_title'],
                         prev['this_week']['signer_title'])
        self.assertEqual(tw['signer_mobile'],
                         prev['this_week']['signer_mobile'])

    def test_graph_order_uses_arg_when_no_prev_draft(self):
        custom = ['08-velocity', '09-spi-over-time']
        seed = build_seed.build_seed_dict(**_kwargs(
            prev_draft=None, graph_order=custom))
        self.assertEqual(seed['this_week']['graph_order'], custom)

    def test_graph_order_falls_back_to_canonical_when_no_arg_no_prev(self):
        seed = build_seed.build_seed_dict(**_kwargs(
            prev_draft=None, graph_order=None))
        self.assertEqual(seed['this_week']['graph_order'],
                         build_seed.CANONICAL_GRAPH_ORDER)

    def test_graph_order_from_prev_draft_wins_over_arg(self):
        prev = json.loads(SAMPLE_DRAFT_PATH.read_text())
        prev_order = prev['this_week']['graph_order']
        seed = build_seed.build_seed_dict(**_kwargs(
            prev_draft=prev, graph_order=['arg-should-be-ignored']))
        self.assertEqual(seed['this_week']['graph_order'], prev_order)

    def test_contractual_completion_arg_lands_in_project_info(self):
        seed = build_seed.build_seed_dict(**_kwargs(
            contractual_completion='2028-12-31'))
        self.assertEqual(seed['project_info']['contractual_completion'],
                         '2028-12-31')


if __name__ == '__main__':
    unittest.main()
