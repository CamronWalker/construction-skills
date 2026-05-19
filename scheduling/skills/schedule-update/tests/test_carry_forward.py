"""Tests for the carry_forward module's Procore-related behavior
(added 2026-05). Existing tests for transition_items/transition_attachments
without Procore concerns live elsewhere if they exist."""

import pathlib
import sys
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import carry_forward as cf  # noqa: E402


class TransitionAttachmentsProcoreTests(unittest.TestCase):
    """share_to_procore preservation + bootstrap rules."""

    def test_preserves_share_to_procore_true_when_file_carries_forward(self):
        last_week = [
            {'filename': 'Schedule View 2026-05-07.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': True},
        ]
        fresh = ['Schedule View 2026-05-14.pdf']  # same template, new date
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_preserves_share_to_procore_false_when_file_carries_forward(self):
        last_week = [
            {'filename': 'SmartPM Summary 2026-05-07.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': False},
        ]
        fresh = ['SmartPM Summary 2026-05-14.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['share_to_procore'])

    def test_new_file_with_View_name_bootstraps_to_true(self):
        last_week = []
        fresh = ['3-Week Look-Ahead View.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_new_file_with_update_request_xlsm_bootstraps_to_true(self):
        last_week = []
        fresh = ['W1177 Update Request 2026-05-14.xlsm']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_new_file_matching_no_pattern_bootstraps_to_false(self):
        last_week = []
        fresh = ['Internal Notes.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['share_to_procore'])

    def test_bootstrap_match_is_case_insensitive(self):
        last_week = []
        fresh = ['weekly view.pdf', 'WEEKLY UPDATE REQUEST.xlsm']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        share = {r['filename']: r['share_to_procore'] for r in result}
        self.assertTrue(share['weekly view.pdf'])
        self.assertTrue(share['WEEKLY UPDATE REQUEST.xlsm'])

    def test_dropped_files_carry_share_to_procore_through_archive(self):
        # File from last week not in fresh list goes to status=removed.
        # share_to_procore should still be preserved on the dropped item.
        last_week = [
            {'filename': 'Old View.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': True},
        ]
        fresh = []
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'removed')
        self.assertTrue(result[0]['share_to_procore'])


if __name__ == '__main__':
    unittest.main()
