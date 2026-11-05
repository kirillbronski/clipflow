"""Media checks shared by pipeline and window tests."""

import json
import subprocess
from pathlib import Path


class NoAuth:
    def options_for(self, profile, url):
        return {}


def probe(path, tools):
    data = json.loads(
        subprocess.check_output(
            [tools[1], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
            text=True,
            encoding='utf-8',
        )
    )
    assert Path(data['format']['filename']) == path
    return data
