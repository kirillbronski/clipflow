"""Exercise the cross-platform UI without signing in or downloading user content."""
import traceback


def run(App, ctk):
    root = ctk.CTk()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(''.join(traceback.format_exception(*args)))
    app = App(root)
    app.auto_download.set(False)
    app.schedule_quality_check = lambda *args: None

    def check():
        try:
            app.update_brand_icon()
            app.url.set('https://www.youtube.com/watch?v=BaW_jenozKc')
            app.start(auto_start=False)
            assert len(app.pending_jobs) == 1
            app.start(auto_start=False)
            assert len(app.pending_jobs) == 1, 'Duplicate queued task'
            app.url.set('https://www.youtube.com/watch?v=jNQXAC9IVRw')
            app.start(auto_start=False)
            assert len(app.pending_jobs) == 2
            app.tabs.set('GetCourse')
            app.activate_tab()
            app.update_brand_icon()
            app.url.set('https://example.getcourse.ru/pl/teach/control/lesson/view?id=1')
            app.start(auto_start=False)
            assert len(app.pending_jobs) == 3
            app.language = 'en'
            app.localize_ui()
            assert app.getcourse_scope_box._text_label.cget('text') == 'All lesson videos'
            app.language = 'ru'
            app.localize_ui()
            app.tabs.set('Instagram')
            app.activate_tab()
            assert app.mode.get() == 'Видео и фото'
            assert app.instagram_description_switch.winfo_manager() == 'grid'
            app.url.set('https://instagram.com/reel/ClipFlowTest/')
            app.save_instagram_description.set(True)
            app.instagram_description_format.set('MD')
            app.start(auto_start=False)
            assert app.pending_jobs[-1]['author_folder']
            assert app.pending_jobs[-1]['post_folder']
            app.instagram_post_folder.set(False)
            assert app.pending_jobs[-1]['post_folder'], 'Queued post folder choice must be immutable'
            app.instagram_author_folder.set(False)
            assert app.pending_jobs[-1]['author_folder'], 'Queued folder choice must be immutable'
            assert app.pending_jobs[-1]['save_description']
            assert app.pending_jobs[-1]['description_format'] == 'MD'
            assert app.pending_jobs[-1]['service'] == 'Instagram'
            app.instagram_description_format.set('TXT')
            app.start(auto_start=False)
            assert app.pending_jobs[-1]['description_format'] == 'TXT'
            assert len(app.pending_jobs) == 5
            app.set_list_mode(True)
            app.set_list_mode(False)
            app.set_filter('Все')
            app.show_settings()
            app.show_about()
            app.add_links_dialog()
            for child in root.winfo_children():
                if isinstance(child, ctk.CTkToplevel):
                    child.destroy()
            app.tabs.set('YouTube')
            app.activate_tab()
            root.clipboard_clear()
            root.clipboard_append('https://youtu.be/jNQXAC9IVRw')
            app.url_entry.delete(0, 'end')
            app.url_entry.paste_text()
            assert app.url_entry.get() == 'https://youtu.be/jNQXAC9IVRw'
            app.clear_download_list()
            assert not app.rows and not app.pending_jobs
            root.update_idletasks()
            if errors:
                raise AssertionError('\n'.join(errors))
            print('PASS cross-platform UI: three services, Instagram description snapshots, tabs, icons, queue, duplicate prevention, filters, language, dialogs, native clipboard, clearing', flush=True)
        except Exception:
            errors.append(traceback.format_exc())
            print('FAIL', errors[-1], flush=True)
        finally:
            root.destroy()

    root.after(500, check)
    root.mainloop()
    return 1 if errors else 0
