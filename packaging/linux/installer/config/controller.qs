function Controller() {
    if (!installer.isInstaller()) return;
    if (installer.isCommandLineInstance()) {
        // QtIFW checks --root before installationStarted. Never guess another root.
        var target = installer.value("ClipFlowUpgradeTarget");
        if (target) this.replacePrevious(target);
    } else {
        var self = this;
        installer.installationStarted.connect(function() {
            self.replacePrevious(installer.value("TargetDir"));
        });
    }
}

Controller.prototype.replacePrevious = function(target) {
    var maintenance = target + "/maintenancetool";
    if (!installer.fileExists(maintenance)) return;
    if (!installer.fileExists(target + "/clipflow-install.txt")) {
        installer.interrupt();
        throw new Error("This directory contains a different installation.");
    }
    var result = installer.execute(maintenance, ["--confirm-command", "purge"]);
    if (result[1] !== 0) {
        installer.interrupt();
        throw new Error("The previous ClipFlow installation could not be removed.");
    }
};
