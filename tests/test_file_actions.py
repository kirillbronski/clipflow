import sys, pathlib, threading
sys.path[:0] = ['source', 'source/_internal']
import clipflow as app
from tempfile import TemporaryDirectory
with TemporaryDirectory() as directory:
    base=pathlib.Path(directory).resolve();app.CONFIG=base/'settings.json';app.PROFILE_FILE=base/'profile.dat'
    root=app.ctk.CTk();w=app.App(root)
    w.display_queue([{'title':'File','service':'YouTube'}],append=True)
    media=base/'Video.mp4';media.write_bytes(b'completed media')
    description=base/'Video.txt';description.write_text('Description 🎬')
    w.row_files[0]=[str(media),str(description)]
    w.confirm_delete_files([0]);root.update()
    dialog=next(c for c in root.winfo_children() if isinstance(c,app.ctk.CTkToplevel))
    assert media.exists()
    def find(widget,label):
        for child in widget.winfo_children():
            if isinstance(child,app.ctk.CTkButton) and child.cget('text')==label: return child
            result=find(child,label)
            if result: return result
    find(dialog,'Отмена').invoke();assert media.exists()
    w.remove_download_row(0);assert media.exists() and not w.rows
    w.display_queue([{'title':'File'}],append=True)
    assert 1 in w.rows
    w.row_files[1]=[str(media),str(description)];w.confirm_delete_files([1]);root.update()
    dialog=next(c for c in root.winfo_children() if isinstance(c,app.ctk.CTkToplevel))
    find(dialog,'Удалить').invoke();assert not media.exists() and not description.exists()
    assert w.rows[1][1].get()=='Файл удалён'
    w.clear_download_list();assert not w.rows
    root.destroy()
print('PASS: clearing rows keeps files; deletion requires explicit confirmation; cancel preserves file; row IDs remain unique')
