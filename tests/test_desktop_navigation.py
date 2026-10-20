"""Navigation must not mistake message/history text for a contact or alter drafts."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'root/scripts/workspace'))
from desktop import Desktop, DesktopError
import desktop_navigation as navigation


class Node:
    def __init__(self, role='filler', name='', children=(), value='', editable=False, showing=True, height=64):
        self.role, self.name, self.value = role, name, value
        self.children, self.parent = list(children), None
        self.states = ({'show'} if showing else set()) | ({'edit'} if editable else set())
        self.box = SimpleNamespace(x=100, y=100, width=320, height=height)
        for child in self.children:
            child.parent = self
    def get_role_name(self): return self.role
    def get_name(self): return self.name
    def get_parent(self): return self.parent
    def get_child_count(self): return len(self.children)
    def get_child_at_index(self, index): return self.children[index]
    def get_state_set(self): return self
    def contains(self, state): return state in self.states


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.search = Node('text', 'Search', editable=True)
        self.editor = Node('text', editable=True)
        self.main = Node('frame', children=[self.search, self.editor])
        self.target = Node('list item', 'Target')
        self.history = Node('list item', 'Target', height=34)
        self.popup_list = Node('list', children=[Node('list item', 'Contacts', height=32), self.target,
                                                Node('list item', 'Chat History', height=32), self.history])
        self.popup = Node(children=[self.popup_list])
        self.app = Node('application', children=[self.main, self.popup])
        self.d = object.__new__(Desktop)
        self.writes = []
        def write(node, value):
            self.writes.append((node, value)); node.value = value
            return True
        self.d.a = SimpleNamespace(StateType=SimpleNamespace(EDITABLE='edit', SHOWING='show'),
            CoordType=SimpleNamespace(SCREEN='screen'),
            Text=SimpleNamespace(get_text=lambda n, start, end: n.value),
            Component=SimpleNamespace(get_extents=lambda n, coord: n.box, grab_focus=lambda n: True),
            EditableText=SimpleNamespace(set_text_contents=write))
        self.d.nodes = lambda: self.d._subtree(self.app)
        self.d._account = Mock()
        self.d._foreground = Mock()
        self.d._controls = Mock(side_effect=DesktopError('CHAT_IDENTITY_UNVERIFIED'))
        self.d.ready = Mock(return_value=True)
        self.binding = {'account':'account', 'username':'wxid_target', 'names':['Target'], 'search_queries':['Target']}

    def test_only_contact_popup_rows_are_candidates(self):
        # A forged message and a real-looking row inside the main frame must
        # never become navigation controls; history results are excluded too.
        fake = Node('list', children=[Node('list item', 'Contacts', height=32), Node('list item', 'Target')])
        fake.parent = self.main; self.main.children.append(fake)
        self.assertEqual(navigation.candidates(self.d, self.d.nodes(), {'Target'}), [self.target])

    def test_navigation_verifies_exact_binding_without_writing_message_editor(self):
        with patch.object(navigation, 'click_control') as click, patch.object(navigation.time, 'sleep'):
            result = navigation.open_chat(self.d, self.binding)
        self.assertTrue(result['verified'])
        self.assertTrue(result['navigated'])
        self.d.ready.assert_called_once_with(self.binding)
        click.assert_called_once_with(self.d, self.target, self.main)
        self.assertEqual(self.writes, [(self.search, 'Target'), (self.search, '')])
        self.assertEqual(self.editor.value, '')

    def test_selected_target_does_not_open_search(self):
        self.d._controls.side_effect = None
        self.assertFalse(navigation.open_chat(self.d, self.binding)['navigated'])
        self.assertEqual(self.writes, [])

    def test_mark_read_persists_boundary_before_navigation_click(self):
        events = []
        with patch.object(navigation, 'click_control', side_effect=lambda *args: events.append('click')), patch.object(navigation.time, 'sleep'):
            result = self.d.operation(self.binding, 'chat-mark-read', {}, lambda: events.append('submitted'))
        self.assertTrue(result['verified'])
        self.assertEqual(events, ['submitted', 'click'])
        self.assertEqual(self.editor.value, '')

    def test_boundary_failure_does_not_click_or_leave_our_search(self):
        def fail():
            raise RuntimeError('receipt database unavailable')
        with patch.object(navigation, 'click_control') as click, patch.object(navigation.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'receipt database unavailable'):
                self.d.open_chat(self.binding, fail)
        click.assert_not_called()
        self.assertEqual(self.search.value, '')

    def test_existing_draft_or_search_blocks_all_mutation(self):
        for node, code in [(self.editor, 'EXISTING_DRAFT'), (self.search, 'SEARCH_INPUT_BUSY')]:
            node.value = 'user input'
            with self.assertRaisesRegex(DesktopError, code): navigation.open_chat(self.d, self.binding)
            self.assertEqual(node.value, 'user input')
            node.value = ''
        self.assertEqual(self.writes, [])

    def test_user_changes_search_during_navigation_is_preserved_without_click(self):
        def human_input(_): self.search.value = 'manual query'
        with patch.object(navigation, 'click_control') as click, patch.object(navigation.time, 'sleep', side_effect=human_input):
            with self.assertRaisesRegex(DesktopError, 'SEARCH_INPUT_CHANGED'):
                navigation.open_chat(self.d, self.binding)
        click.assert_not_called()
        self.assertEqual(self.search.value, 'manual query')
        self.assertEqual(self.writes, [(self.search, 'Target')])

    def test_hidden_unlock_does_not_block_but_visible_dialog_does(self):
        hidden = Node('button', 'Unlock', showing=False)
        self.assertEqual(navigation.guard(self.d, self.d.nodes()+[hidden]), self.main)
        for node, code in [(Node('button','Unlock'), 'WECHAT_LOCKED'), (Node('dialog'), 'WECHAT_DIALOG_OPEN')]:
            with self.assertRaisesRegex(DesktopError, code): navigation.guard(self.d, self.d.nodes()+[node])

    def test_readiness_requires_the_logged_in_search_control(self):
        self.assertEqual(self.d.status()['state'], 'ready')
        self.search.states.discard('show')
        self.assertEqual(self.d.status()['code'], 'CHAT_SEARCH_UNAVAILABLE')

    def test_error_after_attempted_editor_write_cannot_be_automatically_retried(self):
        self.d.open_chat = Mock()
        self.d._controls = Mock(return_value=(self.editor, None))
        self.d._submit = Mock(side_effect=DesktopError('WECHAT_DIALOG_OPEN'))
        with self.assertRaises(DesktopError) as caught:
            self.d.send(self.binding, 'authorized text', Mock())
        self.assertFalse(caught.exception.public()['retryable'])

    def test_action_expiring_during_navigation_does_not_write_a_message(self):
        self.d.open_chat = Mock()
        self.d._controls = Mock(return_value=(self.editor, None))
        self.binding['expires_at'] = 1
        with self.assertRaisesRegex(DesktopError, 'ACTION_EXPIRED'):
            self.d.send(self.binding, 'authorized text', Mock())
        self.assertEqual(self.writes, [])

    def test_duplicate_title_candidate_is_not_accepted_without_session_proof(self):
        second = Node('list item', 'Target'); second.parent = self.popup_list
        self.popup_list.children.insert(2, second)
        self.d.ready = Mock(side_effect=[DesktopError('CHAT_IDENTITY_UNVERIFIED'), True])
        with patch.object(navigation, 'click_control') as click, patch.object(navigation.time, 'sleep'):
            self.assertTrue(navigation.open_chat(self.d, self.binding)['verified'])
        self.assertEqual([c.args[1] for c in click.call_args_list], [self.target, second])
        self.assertTrue(all(node is self.search for node, _ in self.writes))
