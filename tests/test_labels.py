"""Model complete Qt label dialogs and durable effects without a WeChat account."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import test_desktop_operations as fixtures
AccessibleNode = fixtures.AccessibleNode
from labels import Labels
import desktop
import operations


class LabelUI:
    def __init__(self, labels=('Friends', 'Work'), selected=('Friends',)):
        self.labels, self.selected = set(labels), set(selected)
        self.persisted = set(selected)
        self.events, self.windows = [], []
        self.binding = {'account': 'a', 'username': 'wxid_exact', 'names': ['Only Target'], 'alias': None}
        self.d = fixtures.AccessibleDriverTests().driver()
        self.d._controls = lambda binding: (None, None)
        self.d._wait = lambda find: find()
        self.d.nodes = lambda: list(self.windows)
        self.settings = AccessibleNode(role='panel', children=[self.button('Labels', self.open_picker)])
        self.d._settings = lambda binding: self.settings
        self.rejected_save = False
        self.total_offset = 0

    def button(self, name, action):
        return AccessibleNode(name, 'button', action=action)

    def close(self, node):
        if node in self.windows:
            self.windows.remove(node)

    def open_picker(self):
        self.selected = set(self.persisted)
        rows = []
        for name in sorted(self.labels):
            checkbox = AccessibleNode(name, 'check box', states=['show'] + (['checked'] if name in self.selected else []))
            def toggle(name=name, checkbox=checkbox):
                self.events.append('toggle:' + name)
                self.selected.symmetric_difference_update({name})
                checkbox.states.symmetric_difference_update({'checked'})
            checkbox.action = toggle
            rows.append(AccessibleNode(name, 'list item', children=[checkbox]))
        node = AccessibleNode('Set Labels', 'dialog')
        def save():
            self.events.append('save-selection')
            if not self.rejected_save:
                self.persisted = set(self.selected)
            self.close(node)
        node.children = [AccessibleNode('Only Target'), AccessibleNode('WeChat ID: wxid_exact'),
                         AccessibleNode('Total labels: ' + str(len(rows) + self.total_offset)),
                         AccessibleNode('Label List', 'list', children=rows),
                         self.button('Save', save), self.button('Cancel', lambda: self.close(node)),
                         self.button('Manage Labels', self.open_manager)]
        for child in node.children:
            child.parent = node
        self.windows.append(node)
        return node

    def open_manager(self):
        node = AccessibleNode('Manage Labels', 'dialog')
        def refresh():
            rows = []
            for name in sorted(self.labels):
                rows.append(AccessibleNode(name, 'list item', children=[
                    self.button('Rename', lambda name=name: self.edit('Rename Label', node, name)),
                    self.button('Delete', lambda name=name: self.edit('Delete Label', node, name))]))
            node.children = [AccessibleNode('Total labels: ' + str(len(rows) + self.total_offset)),
                             AccessibleNode('Label List', 'list', children=rows),
                             self.button('New Label', lambda: self.edit('New Label', node)),
                             self.button('Close', lambda: self.close(node))]
            for child in node.children:
                child.parent = node
        node.refresh = refresh
        refresh()
        self.windows.append(node)
        return node

    def edit(self, title, manager, name=''):
        field = AccessibleNode('Label Name', 'entry', states=['show', 'edit'], text=name)
        node = AccessibleNode(title, 'dialog')
        def save():
            self.events.append(title + ':' + field.text)
            if not self.rejected_save:
                self.labels.discard(name)
                if title != 'Delete Label':
                    self.labels.add(field.text)
            self.close(node)
            manager.refresh()
        node.children = [AccessibleNode(name), field, self.button('Delete' if title == 'Delete Label' else 'Save', save)]
        for child in node.children:
            child.parent = node
        self.windows.append(node)
        return node


class LabelDriverTests(unittest.TestCase):
    def test_complete_list_and_snapshots_close_only_owned_dialogs(self):
        ui = LabelUI()
        result = ui.d.label_snapshot(ui.binding, 'contact-list-labels')
        self.assertEqual(result, {'labels': ['Friends', 'Work']})
        self.assertEqual(ui.windows, [])
        self.assertEqual(ui.events, [])

    def test_partial_or_duplicate_lists_cannot_authorize_changes(self):
        ui = LabelUI()
        ui.total_offset = 1
        with self.assertRaisesRegex(desktop.DesktopError, 'INCOMPLETE'):
            ui.d.operation(ui.binding, 'contact-delete-label', {'name': 'Work'}, lambda: self.fail('must not submit'))
        self.assertEqual(ui.events, [])
        ui = LabelUI()
        driver = Labels(ui.d)
        manager = driver.manager(ui.binding)
        listing = next(n for n in manager.children if n.role == 'list')
        listing.children[1].name = listing.children[0].name
        with self.assertRaisesRegex(desktop.DesktopError, 'AMBIGUOUS'):
            driver.rows(manager)

    def test_existing_user_selection_is_preserved(self):
        ui = LabelUI()
        user_dialog = ui.open_picker()
        ui.selected = {'Work'}  # Unsaved user selection.
        with self.assertRaisesRegex(desktop.DesktopError, 'EXISTING_LABEL_DIALOG'):
            ui.d.label_snapshot(ui.binding, 'contact-set-labels')
        self.assertEqual(ui.windows, [user_dialog])
        self.assertEqual(ui.selected, {'Work'})
        self.assertEqual(ui.events, [])

    def test_wrong_contact_dialog_cannot_authorize_checkbox_changes(self):
        ui = LabelUI()
        real_open = ui.open_picker
        def wrong():
            node = real_open()
            node.children[1].name = 'WeChat ID: wxid_other'
        ui.settings.children[0].action = wrong
        with self.assertRaisesRegex(desktop.DesktopError, 'IDENTITY_UNVERIFIED'):
            ui.d.operation(ui.binding, 'contact-set-labels', {'labels': []}, lambda: self.fail('must not submit'))
        self.assertEqual(ui.events, [])

    def test_set_replaces_full_selection_and_empty_list_clears(self):
        ui = LabelUI()
        for desired in (['Work'], []):
            result = ui.d.operation(ui.binding, 'contact-set-labels', {'labels': desired}, lambda: ui.events.append('submitted'))
            self.assertEqual(result['labels'], desired)
            self.assertEqual(ui.persisted, set(desired))
            self.assertEqual(ui.windows, [])
        self.assertEqual(ui.events, ['submitted', 'toggle:Friends', 'toggle:Work', 'save-selection', 'submitted', 'toggle:Work', 'save-selection'])

    def test_missing_labels_and_same_selection_have_no_effect(self):
        ui = LabelUI()
        result = ui.d.operation(ui.binding, 'contact-set-labels', {'labels': ['Friends']}, lambda: self.fail('must not submit'))
        self.assertTrue(result['unchanged'])
        with self.assertRaisesRegex(desktop.DesktopError, 'LABEL_NOT_FOUND'):
            ui.d.operation(ui.binding, 'contact-set-labels', {'labels': ['Missing']}, lambda: self.fail('must not submit'))
        self.assertEqual(ui.events, [])

    def test_create_rename_delete_require_reopened_complete_readback(self):
        ui = LabelUI()
        steps = [('contact-create-label', {'name': 'New'}),
                 ('contact-rename-label', {'name': 'New', 'new_name': 'Renamed'}),
                 ('contact-delete-label', {'name': 'Renamed'})]
        for operation, parameters in steps:
            result = ui.d.operation(ui.binding, operation, parameters, lambda: ui.events.append('submitted'))
            self.assertTrue(result['verified'])
            self.assertEqual(set(result['labels']), ui.labels)
            self.assertEqual(ui.windows, [])
        self.assertEqual(ui.labels, {'Friends', 'Work'})
        self.assertEqual(ui.events, ['submitted', 'New Label:New', 'submitted', 'Rename Label:Renamed', 'submitted', 'Delete Label:Renamed'])

    def test_rejected_save_never_claims_completion(self):
        for operation, parameters in [('contact-create-label', {'name': 'New'}), ('contact-set-labels', {'labels': []})]:
            with self.subTest(operation=operation):
                ui = LabelUI()
                ui.rejected_save = True
                with self.assertRaisesRegex(desktop.DesktopError, 'READBACK_FAILED'):
                    ui.d.operation(ui.binding, operation, parameters, lambda: ui.events.append('submitted'))
                self.assertEqual(ui.events[0], 'submitted')

    def test_rename_cannot_merge_names_and_delete_confirmation_must_name_label(self):
        ui = LabelUI()
        with self.assertRaisesRegex(desktop.DesktopError, 'ALREADY_EXISTS'):
            ui.d.operation(ui.binding, 'contact-rename-label', {'name': 'Friends', 'new_name': 'Work'}, lambda: self.fail('must not submit'))
        ui = LabelUI()
        real_edit = ui.edit
        def wrong(title, manager, name=''):
            node = real_edit(title, manager, name)
            node.children[0].name = 'Different Label'
            return node
        ui.edit = wrong
        with self.assertRaisesRegex(desktop.DesktopError, 'CONFIRMATION_IDENTITY'):
            ui.d.operation(ui.binding, 'contact-delete-label', {'name': 'Work'}, lambda: self.fail('must not submit'))
        self.assertEqual(ui.events, [])

    def test_label_validation_rejects_ambiguous_or_non_string_inputs(self):
        for parameters in ({'labels': ['Work', 'Work']}, {'labels': [1]}, {'labels': [' padded ']}, {'labels': ['bad\nname']}, {'labels': ['x' * 65]}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                operations.validate('contact-set-labels', 'a', 'wxid', parameters, 'key')
        operations.validate('contact-set-labels', 'a', 'wxid', {'labels': []}, 'key')


class LabelReceiptTests(unittest.IsolatedAsyncioTestCase):
    prepare = fixtures.OperationTests.prepare
    message = fixtures.OperationTests.message

    async def asyncSetUp(self):
        await fixtures.OperationTests.asyncSetUp(self)
        self.ui = LabelUI()
        self.ops.desktop_factory = lambda: self.ui.d
        self.ui.d.ready = lambda binding: None
        # This isolated DB resolves the fixture username to this exact contact.
        self.ui.binding['username'] = 'wxid_exact'
        self.ops.binding = AsyncMock(return_value=self.ui.binding)

    async def test_label_change_after_prepare_cancels_without_mutation(self):
        item = await self.prepare('contact-delete-label', {'name': 'Work'})
        self.ui.labels.add('Concurrent addition')
        result = await self.ops.commit(item['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertIn('Work', self.ui.labels)
        self.assertEqual(self.ui.events, [])

    async def test_durable_label_commit_once_and_uncertain_save_never_repeats(self):
        item = await self.prepare('contact-create-label', {'name': 'New'})
        self.assertEqual(self.ui.events, [])
        result = await self.ops.commit(item['id'])
        self.assertEqual(result['status'], 'completed')
        await self.ops.commit(item['id'])
        self.assertEqual(self.ui.events, ['New Label:New'])
        self.assertIn('New', json.loads(result['receipt'])['labels'])
        second = await self.prepare('contact-create-label', {'name': 'Rejected'}, 'second')
        self.ui.rejected_save = True
        with self.assertRaises(desktop.DesktopError):
            await self.ops.commit(second['id'])
        self.assertEqual(self.ops.get(second['id'])['status'], 'uncertain')
        await self.ops.commit(second['id'])
        self.assertEqual(self.ui.events.count('New Label:Rejected'), 1)
