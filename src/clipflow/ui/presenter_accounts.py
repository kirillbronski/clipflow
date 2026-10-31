"""Signed-in accounts: polling the gateway and keeping presets on the active profiles."""

from dataclasses import replace

from PySide6.QtCore import QObject, QTimer

from clipflow.domain.models import JobState, Service

_ACTIVE = {JobState.PROBING, JobState.DOWNLOADING, JobState.PROCESSING}


class AccountsController(QObject):
    """Every method runs inside the presenter's command guard."""

    def __init__(self, presenter):
        super().__init__(presenter)
        self.presenter = presenter
        self.gateway = None
        self._snapshot = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(presenter._poll_auth)

    def attach(self, gateway):
        self.gateway = gateway
        self.presenter.executor.auth = gateway
        settings = self.presenter.settings
        gateway.activate_profile(
            Service.GETCOURSE, settings.presets[Service.GETCOURSE].auth_profile
        )
        self.presenter._poll_auth()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll(self):
        """On any account change: forget probes made as someone else and sync presets."""
        self.gateway.poll()
        snapshot = tuple(self.gateway.status(service) for service in Service)
        if snapshot == self._snapshot:
            return
        presenter = self.presenter
        presenter.clear_probe_cache()
        presets = dict(presenter.settings.presets)
        for status in snapshot:
            presets[status.service] = replace(
                presets[status.service],
                auth_profile=status.profile if status.connected else None,
            )
        if presets != dict(presenter.settings.presets):
            presenter._save_settings(replace(presenter.settings, presets=presets))
        self._snapshot = snapshot
        presenter.auth_changed.emit()

    def sign_in(self, service):
        return self.gateway.sign_in(service, self.presenter.settings.language)

    def logout(self, service):
        if self.gateway is None:
            return
        status = self.gateway.status(service)
        if status.profile is None:
            return
        presenter = self.presenter
        for job in presenter.repository.list():
            if job.request.options.auth_profile == status.profile and job.state in _ACTIVE:
                presenter.scheduler.pause(job.id)
        self.gateway.logout(status.profile)
        presenter._poll_auth()

    def configure_getcourse(self, url, method, **values):
        if self.gateway is None:
            return None
        profile = self.gateway.configure_getcourse(url, method, **values)
        self.presenter._poll_auth()
        return profile

    def import_getcourse(self, url):
        if self.gateway is None:
            return None
        profile = self.gateway.import_legacy_getcourse(url)
        self.presenter._poll_auth()
        return profile
