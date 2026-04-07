"""
recorder.py — TSV file recorder for ambit dyeCO2 measurements.

File naming: data/YYYY-MM-DD_HH-MM-SS_<filename>.txt
Header row : # started=<ISO>, model=<model>, gain=<N>, atime=<N>, astep=<N>, led=<N>mA
Column row : timestamp\t<spec channels...>\tT\tP\tRH\tGas
"""

import os
from datetime import datetime
from pathlib import Path


class Recorder:
    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir)
        self._file = None
        self._spec_channels: list[str] = []
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start_recording(
        self,
        filename: str,
        model: str,
        gain: int,
        atime: int,
        astep: int,
        led: int,
        spec_channels: list[str],
    ) -> Path:
        """Open a new TSV file and write metadata + column headers."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        safe_name = filename.strip() or "DATA"
        stem = now.strftime("%Y-%m-%d_%H-%M-%S") + "_" + safe_name
        path = self._data_dir / (stem + ".txt")

        self._spec_channels = list(spec_channels)
        try:
            self._file = open(path, "w", encoding="utf-8", newline="\n")
            # Metadata comment line
            self._file.write(
                f"# started={now.isoformat(timespec='seconds')}, "
                f"model={model}, gain={gain}, atime={atime}, "
                f"astep={astep}, led={led}mA\n"
            )
            # Column headers
            cols = ["timestamp"] + self._spec_channels + ["T", "P", "RH", "Gas"]
            self._file.write("\t".join(cols) + "\n")
            self._file.flush()
        except OSError:
            if self._file is not None:
                self._file.close()
                self._file = None
            raise

        self._recording = True
        return path

    def write_row(
        self,
        timestamp: str,
        spec: dict | None,
        bme: dict | None,
    ) -> None:
        """Append one TSV data row. Missing values are written as empty strings."""
        if not self._recording or self._file is None:
            return

        spec = spec or {}
        bme = bme or {}

        spec_vals = [str(spec.get(ch, "")) for ch in self._spec_channels]
        bme_vals = [
            str(bme.get("T", "")),
            str(bme.get("P", "")),
            str(bme.get("RH", "")),
            str(bme.get("Gas", "")),
        ]
        row = [timestamp] + spec_vals + bme_vals
        self._file.write("\t".join(row) + "\n")
        self._file.flush()

    def stop_recording(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
        self._recording = False
        self._spec_channels = []
