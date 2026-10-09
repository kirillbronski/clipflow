"""Exercise the actual entry bindings and menu commands for all three services."""
import sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = ['source', 'source/_internal']
import clipflow as module

root = module.ctk.CTk()
app = module.App(root)
app.auto_download.set(False)
app.schedule_quality_check = lambda *args: None
errors = []
root.report_callback_exception = lambda *args: errors.append(args)
urls = {'YouTube': 'https://youtu.be/test', 'Instagram': 'https://instagram.com/reel/test/',
        'GetCourse': 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=1'}
try:
    root.update()
    for service, url in urls.items():
        print('TEST',service,flush=True)
        app.tabs.set(service)
        app.activate_tab()
        root.update()
        entry = app.contexts[service]['url_entry']
        root.clipboard_clear()
        root.clipboard_append(url)
        root.update()
        app.contexts[service]['paste_button'].invoke()
        assert entry.get() == url, (service, 'button', entry.get())
        entry.select_range(0, 'end')
        entry._entry.event_generate('<<Paste>>')
        assert entry.get() == url, (service, 'virtual paste')
        entry.focus_force()
        root.update()
        print('KEY',service,flush=True)
        entry.select_range(0, 'end')
        entry._entry.event_generate(f'<{module.MODIFIER}-KeyPress-v>')
        root.update()
        assert entry.get() == url, (service, 'shortcut', entry.get())
        print('MENU',service,flush=True)
        entry.delete(0, 'end')
        # Drive the real menu's Paste command without AppKit's modal tracking loop.
        def choose_paste(menu, *args):
            menu.invoke(0)
        with patch.object(module.tk.Menu, 'tk_popup', choose_paste):
            entry._entry.event_generate('<Button-3>', x=10, y=10, rootx=200, rooty=200)
        root.update()
        assert entry.get() == url, (service, 'context menu', entry.get())
        if module.IS_MAC:
            assert entry._entry.bind('<Button-2>')
            assert entry._entry.bind('<Control-Button-1>')
        entry.select_range(0, 'end')
        entry.edit_shortcut(SimpleNamespace(keysym='Cyrillic_em', keycode=86))
        assert entry.get() == url, (service, 'Russian layout', entry.get(), root.clipboard_get())
    # A callback remains bound to its own service, regardless of active aliases.
    app.contexts['YouTube']['paste_button'].invoke()
    assert app.contexts['YouTube']['url'].get() == urls['GetCourse']
    # Successful start clears only that task's unchanged input; failures/new text stay.
    app.active_run = object()
    app.active_job = {'service': 'Instagram'}
    context = app.contexts['Instagram']
    context['url'].set(urls['Instagram'])
    app.events.put(('download_started', urls['Instagram'], app.active_run))
    app._poll_updates()
    assert context['url'].get() == ''
    context['url'].set('https://instagram.com/reel/new/')
    app.events.put(('download_started', urls['Instagram'], app.active_run))
    app._poll_updates()
    assert context['url'].get().endswith('/new/')
    assert not errors, errors
    print('PASS clipboard: three services, button, keyboard, popup command, RU layout, safe input clearing')
finally:
    root.destroy()
