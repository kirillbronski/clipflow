function Component() {}

function quotedExec(path) {
    if (/[\r\n\x00]/.test(path)) throw new Error("Invalid installation path");
    return '"' + path.replace(/[\\"`$]/g, '\\$&').replace(/\\/g, '\\\\').replace(/%/g, '%%') + '"';
}

Component.prototype.createOperations = function() {
    component.createOperations();
    var home = installer.value("HomeDir");
    var xdg = installer.environmentVariable("XDG_DATA_HOME");
    var data = xdg && xdg.charAt(0) === "/" ? xdg : home + "/.local/share";
    var target = installer.value("TargetDir");
    var entries = data + "/applications";
    var iconRoot = data + "/icons/hicolor";
    var iconCacheCommand = 'command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$1" || true';
    component.addOperation("Execute", "/bin/true", "UNDOEXECUTE", "/bin/sh", "-c", iconCacheCommand, "clipflow", iconRoot);
    var cacheCommand = 'command -v update-desktop-database >/dev/null && update-desktop-database "$1" || true';
    // Undo this first registered operation last, after removing the menu entries.
    component.addOperation("Execute", "/bin/true", "UNDOEXECUTE", "/bin/sh", "-c", cacheCommand, "clipflow", entries);
    component.addOperation("Mkdir", entries);
    component.addOperation("Mkdir", data + "/icons/hicolor/256x256/apps");
    component.addOperation("Copy", target + "/clipflow.png", data + "/icons/hicolor/256x256/apps/clipflow.png");
    component.addOperation("Mkdir", iconRoot + "/scalable/apps");
    component.addOperation("Copy", target + "/clipflow-uninstall.svg", iconRoot + "/scalable/apps/clipflow-uninstall.svg");
    component.addOperation("CreateDesktopEntry", entries + "/clipflow.desktop",
        "Type=Application\nName=ClipFlow\nComment=Download your videos\nComment[ru]=Скачивание видео\nExec=" +
        quotedExec(target + "/ClipFlow") + "\nIcon=clipflow\nTerminal=false\nCategories=AudioVideo;Network;\nStartupWMClass=ClipFlow\n");
    component.addOperation("CreateDesktopEntry", entries + "/clipflow-uninstall.desktop",
        "Type=Application\nName=Uninstall ClipFlow\nName[ru]=Удалить ClipFlow\nExec=" +
        quotedExec(target + "/maintenancetool") + "\nIcon=clipflow-uninstall\nTerminal=false\nCategories=Settings;\n");
    component.addOperation("Execute", "/bin/sh", "-c", iconCacheCommand, "clipflow", iconRoot, "UNDOEXECUTE", "/bin/true");
    // Absence of the optional cache updater must not fail installation or rollback.
    component.addOperation("Execute", "/bin/sh", "-c", cacheCommand, "clipflow", entries, "UNDOEXECUTE", "/bin/true");
};
