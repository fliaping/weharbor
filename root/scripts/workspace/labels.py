"""Contact labels through identity-bound accessible dialogs, never a shadow DB."""
import re

from desktop import DesktopError


LABEL_WRITES = {'contact-create-label', 'contact-set-labels',
                'contact-rename-label', 'contact-delete-label'}


class Labels:
    def __init__(self, desktop):
        self.d = desktop
        self.owned = []

    def _dialog(self, titles, binding=None):
        d = self.d
        candidates = []
        for node in d.nodes():
            if not d._visible(node) or node.get_role_name() != 'dialog':
                continue
            names = {n.get_name().strip() for n in d._subtree(node) if d._visible(n)}
            if node.get_name().strip() not in titles:
                continue
            if binding is not None:
                ids = [binding['username'], binding.get('alias')]
                exact = any(v and names.intersection({v, '微信号：' + v, 'WeChat ID: ' + v}) for v in ids)
                if not exact or not names.intersection(binding['names']):
                    continue
            candidates.append(node)
        if len(candidates) != 1:
            raise DesktopError('LABEL_DIALOG_IDENTITY_UNVERIFIED')
        return candidates[0]

    def picker(self, binding, reopen=False):
        d = self.d
        titles = {'设置标签', 'Set Labels', 'Set labels'}
        d._account(binding['account'])
        # Only a dialog with its own exact contact identity can be reused.
        try:
            current = self._dialog(titles, binding)
        except DesktopError:
            current = None
        if current is not None:
            if current not in self.owned:
                raise DesktopError('EXISTING_LABEL_DIALOG: preserve the user draft')
            if not reopen:
                return current
            d._activate(d._one(d._subtree(current), ['取消', 'Cancel'], ['button', 'push button']))
            self._wait_closed(titles, binding)
        panel = d._settings(binding)
        d._activate(d._one(d._subtree(panel), ['标签', 'Tags', 'Labels'], ['button', 'push button']))
        opened = d._wait(lambda: self._dialog(titles, binding))
        self.owned.append(opened)
        return opened

    def _wait_closed(self, titles, binding=None):
        def closed():
            # Do not confuse a second, wrong-contact dialog with closure.
            for node in self.d.nodes():
                if self.d._visible(node) and node.get_role_name() == 'dialog':
                    if node.get_name().strip() in titles:
                        raise DesktopError('LABEL_DIALOG_DID_NOT_CLOSE')
            return True
        return self.d._wait(closed)

    def manager(self, binding, reopen=False):
        d = self.d
        titles = {'管理标签', 'Manage Labels', 'Manage labels'}
        d._account(binding['account'])
        try:
            current = self._dialog(titles)
        except DesktopError:
            current = None
        if current is not None:
            if current not in self.owned:
                raise DesktopError('EXISTING_LABEL_DIALOG: preserve the user draft')
            if not reopen:
                return current
            d._activate(d._one(d._subtree(current), ['关闭', 'Close'], ['button', 'push button']))
            self._wait_closed(titles)
        picker = self.picker(binding)
        d._activate(d._one(d._subtree(picker), list(titles), ['button', 'push button']))
        opened = d._wait(lambda: self._dialog(titles))
        self.owned.append(opened)
        return opened

    def close(self):
        # Only close dialogs opened by this operation, never a user dialog.
        for node in reversed(self.owned):
            if node in self.d.nodes() and self.d._visible(node):
                names = ['取消', 'Cancel'] if node.get_name().strip() in {'设置标签', 'Set Labels', 'Set labels'} else ['关闭', 'Close']
                self.d._activate(self.d._one(self.d._subtree(node), names, ['button', 'push button']))
                self._wait_closed({node.get_name().strip()})
        self.owned.clear()

    def rows(self, panel, picker=False):
        """Require a complete, unique list; virtualized or partial views fail."""
        d = self.d
        container = d._one(d._subtree(panel), ['标签列表', 'Label List', 'Label list'], ['list', 'table', 'tree table'])
        rows = [n for n in d._subtree(container) if n.get_role_name() in ['list item', 'table row']]
        totals = []
        for node in d._subtree(panel):
            if d._visible(node):
                match = re.fullmatch(r'(?:标签总数[：:]|Total labels:)\s*([0-9]+)', node.get_name().strip())
                if match:
                    totals.append(int(match[1]))
        # Qt lists may expose only the rows currently on screen. A declared
        # total (or a complete accessible table) is mandatory, even when empty.
        if not totals and container.get_role_name() in ['table', 'tree table']:
            try:
                totals = [container.get_table_iface().get_n_rows()]
            except (AttributeError, RuntimeError):
                pass
        if not totals or len(set(totals)) != 1 or totals[0] != len(rows) or any(not d._visible(n) for n in rows):
            raise DesktopError('LABEL_LIST_INCOMPLETE')
        result = {}
        for row in rows:
            if picker:
                control = d._one(d._subtree(row), [row.get_name().strip()], ['check box'])
            else:
                control = row
            name = row.get_name().strip()
            if not name or name in result:
                raise DesktopError('LABEL_NAMES_AMBIGUOUS')
            result[name] = control
        return result

    def selected(self, panel):
        return {name for name, control in self.rows(panel, picker=True).items()
                if control.get_state_set().contains(self.d.a.StateType.CHECKED)}

    def snapshot(self, binding, operation):
        d = self.d
        d._controls(binding)
        if operation == 'contact-set-labels':
            panel = self.picker(binding, reopen=True)
            available = self.rows(panel, picker=True)
            value = {'labels': sorted(available), 'selected': sorted(self.selected(panel))}
        else:
            panel = self.manager(binding, reopen=True)
            value = {'labels': sorted(self.rows(panel))}
        d._account(binding['account'])
        return value

    def list(self, binding):
        return {'account': binding['account'], **self.snapshot(binding, 'contact-list-labels'),
                'verified': True, 'source': 'wechat-accessibility', 'complete': True}

    def set(self, binding, parameters, before_change):
        d = self.d
        panel = self.picker(binding)
        controls = self.rows(panel, picker=True)
        desired = set(parameters['labels'])
        if desired - controls.keys():
            raise DesktopError('LABEL_NOT_FOUND: create the exact labels first')
        current = self.selected(panel)
        if current == desired:
            return {'verified': True, 'unchanged': True, 'labels': sorted(desired)}
        save = d._one(d._subtree(panel), ['保存', '完成', 'Save', 'Done'], ['button', 'push button'])
        d._account(binding['account'])
        d._controls(binding)
        before_change()  # Some versions persist each checkbox immediately.
        for name in sorted(current ^ desired):
            d._account(binding['account'])
            d._controls(binding)
            if self._dialog({'设置标签', 'Set Labels', 'Set labels'}, binding) != panel:
                raise DesktopError('LABEL_DIALOG_CHANGED')
            if self.selected(panel) != current:
                raise DesktopError('LABEL_SELECTION_CHANGED')
            d._activate(controls[name])
            current.symmetric_difference_update({name})
            if self.selected(panel) != current:
                raise DesktopError('LABEL_TOGGLE_READBACK_FAILED')
        d._activate(save)
        persisted = self.picker(binding, reopen=True)
        if self.selected(persisted) != desired:
            raise DesktopError('LABEL_SAVE_READBACK_FAILED')
        return {'verified': True, 'labels': sorted(desired), 'meaning': 'complete contact label selection read after reopening'}

    def write(self, binding, operation, parameters, before_change):
        if operation == 'contact-set-labels':
            return self.set(binding, parameters, before_change)
        d = self.d
        panel = self.manager(binding)
        original = set(self.rows(panel))
        name = parameters['name']
        if operation == 'contact-create-label':
            if name in original:
                return {'verified': True, 'unchanged': True, 'labels': sorted(original)}
            d._activate(d._one(d._subtree(panel), ['新建标签', 'New Label', 'Create Label'], ['button', 'push button']))
            dialog = d._wait(lambda: self._dialog({'新建标签', 'New Label', 'Create Label'}))
            expected = original | {name}
            text = name
        else:
            if name not in original:
                raise DesktopError('LABEL_NOT_FOUND')
            row = self.rows(panel)[name]
            if operation == 'contact-rename-label':
                text = parameters['new_name']
                if text == name:
                    return {'verified': True, 'unchanged': True, 'labels': sorted(original)}
                if text in original:
                    raise DesktopError('LABEL_NAME_ALREADY_EXISTS')
                d._activate(d._one(d._subtree(row), ['重命名', 'Rename'], ['button', 'push button']))
                dialog = d._wait(lambda: self._dialog({'重命名标签', 'Rename Label'}))
                expected = original - {name} | {text}
            else:
                d._activate(d._one(d._subtree(row), ['删除', 'Delete'], ['button', 'push button']))
                dialog = d._wait(lambda: self._dialog({'删除标签', 'Delete Label'}))
                text = None
                expected = original - {name}
            # A generic confirmation cannot authorize deleting another label.
            names = {n.get_name().strip() for n in d._subtree(dialog) if d._visible(n)}
            if name not in names:
                raise DesktopError('LABEL_CONFIRMATION_IDENTITY_UNVERIFIED')
        if text is not None:
            field = d._field(dialog, ['标签名称', 'Label Name', 'Label name'])
            if operation == 'contact-rename-label' and field.get_text_iface().get_text(0, -1) != name:
                raise DesktopError('LABEL_RENAME_IDENTITY_UNVERIFIED')
            if operation == 'contact-create-label' and field.get_text_iface().get_text(0, -1):
                raise DesktopError('EXISTING_LABEL_DRAFT')
            d._foreground(field)
            if not field.get_component_iface().grab_focus():
                raise DesktopError('LABEL_FIELD_FOCUS_FAILED')
        save_names = ['删除', 'Delete'] if text is None else ['保存', '完成', 'Save', 'Done']
        save = d._one(d._subtree(dialog), save_names, ['button', 'push button'])
        d._account(binding['account'])
        d._controls(binding)
        if set(self.rows(panel)) != original:
            raise DesktopError('LABEL_LIST_CHANGED')
        before_change()
        if text is not None:
            if not field.get_editable_text_iface().set_text_contents(text) or field.get_text_iface().get_text(0, -1) != text:
                raise DesktopError('LABEL_INPUT_UNCERTAIN')
        d._activate(save)
        self._wait_closed({'删除标签', 'Delete Label'} if text is None else {'新建标签', 'New Label', 'Create Label', '重命名标签', 'Rename Label'})
        persisted = set(self.rows(self.manager(binding, reopen=True)))
        if persisted != expected:
            raise DesktopError('LABEL_SAVE_READBACK_FAILED')
        return {'verified': True, 'labels': sorted(persisted), 'meaning': 'complete label list read after reopening; deleting a label does not delete contacts'}
