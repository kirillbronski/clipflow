import sys, queue, threading
sys.path[:0] = ['source', 'source/_internal']
from clipflow import App, ctk
from download_events import coalesce_updates

root = ctk.CTk()
app = App(root)
app.auto_download.set(False)
app.schedule_quality_check = lambda *args: None
errors = []
root.report_callback_exception = lambda *args: errors.append(args)
root.update()
root.after_cancel(app._poll_after)
app.launch_next = lambda: None
app.url.set('https://youtu.be/first')
app.start(auto_start=False)
app.url.set('https://youtu.be/second')
app.start(auto_start=False)
first, second = app.pending_jobs
first_run, second_run = object(), object()
app.active_job, app.active_rows, app.active_run = first, [0], first_run
app.set_busy(True)
app.events.put(('queue', [{'title': 'Private video'}], first_run))
app.events.put(('error', 'Sign in required', first_run))
app.poll()
root.after_cancel(app._poll_after)
assert app.rows[0][1].get() == 'Не удалось скачать'
app.active_job, app.active_rows, app.active_run = second, [1], second_run
app.active_row = 1
app.set_busy(True)
changes = []
app.rows[1][1].trace_add('write', lambda *args: changes.append(app.rows[1][1].get()))
app.events.put(('queue', [{'title': 'Public video'}], second_run))
app.events.put(('row', (0, 'Public video', 'Скачивание…', 'active'), second_run))
# Delayed failure from the prior attempt must not affect the active job.
app.events.put(('error', 'Old error', first_run))
for i in range(2000):
    app.events.put(('eta', (0, 9), second_run))
    app.events.put(('progress', (0, i / 20, 2.7, 1), second_run))
app.poll()
root.after_cancel(app._poll_after)
assert len(changes) == 2, changes
assert app.rows[0][1].get() == 'Не удалось скачать'
assert app.rows[1][1].get().startswith('100%'), app.rows[1][1].get()
assert app.rows[1][2]._label.cget('text') == app.rows[1][1].get()
assert app.busy and app.active_row == 1
# Telemetry must never rebuild row controls/menus or move row geometry.
root.update_idletasks()
label = app.rows[1][2]
geometry = (label.winfo_width(), app.row_cards[1].winfo_height(), app.row_pause_controls[1].winfo_x(), app.row_cancel_controls[1].winfo_x())
layout_calls = []
originals = {}
for method in ('refresh_row_controls', 'refresh_auth_controls', 'refresh_list', 'localize_ui'):
    original = originals[method] = getattr(app, method)
    def counted(*args, _method=method, _original=original, **kwargs):
        layout_calls.append(_method)
        return _original(*args, **kwargs)
    setattr(app, method, counted)
for number in range(30):
    app.events.put(('eta', (0, number * 91), second_run))
    app.events.put(('progress', (0, number, number * 3.3, 1), second_run))
    app.poll()
    root.after_cancel(app._poll_after)
    root.update_idletasks()
    assert (label.winfo_width(), app.row_cards[1].winfo_height(), app.row_pause_controls[1].winfo_x(), app.row_cancel_controls[1].winfo_x()) == geometry
assert not layout_calls, layout_calls
for method, original in originals.items():
    setattr(app, method, original)
app.language = 'en'
app.localize_ui()
app.events.put(('progress', (0, 50, 2, 1), second_run))
app.poll(); root.after_cancel(app._poll_after)
assert 'MB/s' in label._label.cget('text')
app.language = 'ru'; app.localize_ui()
app.events.put(('row', (0, None, 'Обработка файла…', 'active'), second_run))
app.poll()
root.after_cancel(app._poll_after)
assert app.rows[1][1].get() == 'Обработка файла…'
app.events.put(('row', (0, None, 'Скачано', 'done'), second_run))
app.events.put(('done', '1 из 1 видео', second_run))
app.poll()
root.after_cancel(app._poll_after)
assert app.rows[1][1].get() == 'Скачано'
assert app.rows[1][2]._label.cget('text') == 'Скачано'
assert not app.busy and not errors
assert 'Не удалось скачать' not in changes
# Do not coalesce progress across a finished or failed row.
sequence = [('progress', (0, 99, 1, 1)), ('row', (0, None, 'Скачано', 'done')), ('progress', (1, 0, 0, 2))]
assert coalesce_updates(sequence) == sequence
root.destroy()
print('PASS: private first video, 4000 telemetry events on second, stale error isolated, processing, final success, rendered labels')
