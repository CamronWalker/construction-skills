"""Tests for the carry_forward module's Procore-related behavior
(added 2026-05) and reconcile_items prev_idx contract (added with the
cloud-editor closeout)."""

import pathlib
import sys
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import carry_forward as cf  # noqa: E402


class ReconcileItemsPrevIdxTests(unittest.TestCase):
    """reconcile_items now returns (this_week_rows, last_week_baseline)
    where rows carry prev_idx instead of previous_text."""

    def test_returns_two_tuples(self):
        rows, baseline = cf.reconcile_items([], [], today_iso='2026-05-22')
        self.assertEqual(rows, [])
        self.assertEqual(baseline, [])

    def test_unchanged_text_carries_prev_idx_to_baseline_slot(self):
        last_week = [
            {'text': 'Steel up.', 'checked': True, 'status': 'active',
             'date_archived': ''},
            {'text': 'Trim out.', 'checked': True, 'status': 'active',
             'date_archived': ''},
        ]
        rows, baseline = cf.reconcile_items(
            last_week, ['Steel up.', 'Trim out.'], today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0]['prev_idx'], 0)
        self.assertEqual(rows[1]['prev_idx'], 1)
        # baseline mirrors last_week shape (no prev_idx in baseline rows).
        self.assertEqual(len(baseline), 2)
        self.assertEqual(baseline[0]['text'], 'Steel up.')
        self.assertNotIn('prev_idx', baseline[0])

    def test_edited_text_still_points_to_prev_via_fuzzy_match(self):
        last_week = [
            {'text': 'MEP coordination behind two weeks.', 'checked': True,
             'status': 'active', 'date_archived': ''},
        ]
        this_week = ['MEP coordination behind three weeks — see RFI 0142.']
        rows, baseline = cf.reconcile_items(
            last_week, this_week, today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0]['prev_idx'], 0)
        # baseline preserves the original text for the editor to diff against
        self.assertEqual(
            baseline[0]['text'], 'MEP coordination behind two weeks.',
        )

    def test_unmatched_this_week_text_is_new_with_null_prev_idx(self):
        last_week = []
        rows, baseline = cf.reconcile_items(
            last_week, ['Fresh item this week.'], today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])

    def test_dropped_last_week_item_carries_prev_idx_in_removed_row(self):
        last_week = [
            {'text': 'Was a red flag.', 'checked': True, 'status': 'active',
             'date_archived': ''},
        ]
        rows, baseline = cf.reconcile_items(
            last_week, [], today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertFalse(rows[0]['checked'])
        self.assertEqual(rows[0]['prev_idx'], 0)

    def test_resurrected_removed_item_is_new_with_null_prev_idx(self):
        last_week = [
            {'text': 'Resolved last week.', 'checked': False,
             'status': 'removed', 'date_archived': ''},
        ]
        rows, baseline = cf.reconcile_items(
            last_week, ['Resolved last week.'], today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        # Came back from removed/archived — no diff link.
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])

    def test_no_previous_text_field_in_output(self):
        """previous_text is gone — the editor walks prev_idx instead."""
        last_week = [
            {'text': 'Old.', 'checked': True, 'status': 'active',
             'date_archived': ''},
        ]
        rows, baseline = cf.reconcile_items(
            last_week, ['Old, with edit.'], today_iso='2026-05-22',
        )
        for row in rows:
            self.assertNotIn('previous_text', row)
        for row in baseline:
            self.assertNotIn('previous_text', row)


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


class ReconcileItemsV2RowShapeTests(unittest.TestCase):
    """v2: rows have no date_archived field. status='archived' is impossible
    in these four lists; lifecycle is active → removed → dropped."""

    def test_active_row_has_no_date_archived_key(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            ['Steel up.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'active')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_row_has_no_date_archived_key(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            [],  # nothing this week — last week's row drops
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_does_not_transition_to_archived_in_these_four_lists(self):
        # Last week's row was already 'removed'. This week it's still
        # absent. In v1 it would transition to 'archived'; in v2 it just
        # drops entirely from the result.
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': False, 'status': 'removed'}],
            [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])

    def test_edited_flag_set_when_text_changed(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'MEP behind two weeks.', 'checked': True, 'status': 'active'}],
            ['MEP behind three weeks — see RFI 0142.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0].get('edited'), True)
        self.assertEqual(rows[0]['prev_idx'], 0)

    def test_edited_flag_absent_or_false_when_text_unchanged(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            ['Steel up.'],
            today_iso='2026-05-22',
        )
        self.assertFalse(rows[0].get('edited', False))

    def test_new_row_has_no_edited_no_date_archived(self):
        rows, _ = cf.reconcile_items(
            [],
            ['Brand new item.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])
        self.assertNotIn('edited', rows[0])
        self.assertNotIn('date_archived', rows[0])


class ReconcileKeyItemsTests(unittest.TestCase):
    """v2: key_items has a sibling key_items_archived list.
    reconcile_key_items returns (this_week_rows, this_week_archived_rows,
    last_week_baseline). Items that fall out transition active → removed
    → archived (with date_archived). Archived rows older than 90 days
    drop entirely."""

    def test_active_carries_forward_to_active(self):
        last_key = [
            {'text': 'Owner walkthrough 2026-05-28.', 'checked': True, 'status': 'active'},
        ]
        rows, archived, baseline = cf.reconcile_key_items(
            last_key, [], ['Owner walkthrough 2026-05-28.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0]['prev_idx'], 0)
        self.assertEqual(archived, [])
        self.assertEqual(baseline[0]['text'], 'Owner walkthrough 2026-05-28.')

    def test_dropped_item_goes_to_removed(self):
        last_key = [
            {'text': 'Will not happen again.', 'checked': True, 'status': 'active'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            last_key, [], [],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertEqual(archived, [])

    def test_removed_last_week_archives_this_week(self):
        last_key = [
            {'text': 'Already removed last update.', 'checked': False, 'status': 'removed'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            last_key, [], [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]['status'], 'archived')
        self.assertEqual(archived[0].get('date_archived'), '2026-05-22')

    def test_archived_in_last_week_stays_archived_with_original_date(self):
        last_archived = [
            {'text': 'Archived two weeks ago.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-05-08'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]['date_archived'], '2026-05-08')

    def test_archived_past_90_days_prunes(self):
        last_archived = [
            {'text': 'Archived too long ago.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-01-01'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])
        self.assertEqual(archived, [])

    def test_resurrected_archived_item_becomes_new(self):
        last_archived = [
            {'text': 'Old key item resurrected.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-05-08'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, ['Old key item resurrected.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])
        self.assertEqual(archived, [])


class TransitionAttachmentsV2Tests(unittest.TestCase):
    """v2: attachments use 'name'/'procore' field names, optional 'ext'.
    No archived status; lifecycle is active → removed → dropped."""

    def test_active_row_uses_name_and_procore(self):
        last = [
            {'name': 'Report 01.pdf', 'checked': True, 'status': 'active',
             'procore': True},
        ]
        rows = cf.transition_attachments(last, ['Report 01.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Report 01.pdf')
        self.assertEqual(rows[0]['procore'], True)
        self.assertNotIn('filename', rows[0])
        self.assertNotIn('share_to_procore', rows[0])
        self.assertNotIn('date_archived', rows[0])

    def test_new_attachment_bootstrap_view_match_defaults_procore_true(self):
        rows = cf.transition_attachments([], ['Owner View Report.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'new')
        self.assertEqual(rows[0]['procore'], True)

    def test_new_attachment_bootstrap_unknown_defaults_procore_false(self):
        rows = cf.transition_attachments([], ['Internal Memo.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['procore'], False)

    def test_dropped_attachment_goes_to_removed_no_archived(self):
        last = [
            {'name': 'Old Report.pdf', 'checked': True, 'status': 'active',
             'procore': False},
        ]
        rows = cf.transition_attachments(last, [],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_last_week_drops_entirely(self):
        last = [
            {'name': 'Old Report.pdf', 'checked': False, 'status': 'removed',
             'procore': False},
        ]
        rows = cf.transition_attachments(last, [],
                                          today_iso='2026-05-22')
        self.assertEqual(rows, [])

    def test_ext_set_from_filename_extension(self):
        rows = cf.transition_attachments([], ['Update Request.xlsm'],
                                          today_iso='2026-05-22')
        self.assertEqual(rows[0].get('ext'), 'xlsm')


if __name__ == '__main__':
    unittest.main()
