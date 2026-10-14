
from rich.console import Console

from faceoff import messages
from faceoff.deface import Options, Outputs
from faceoff.reorient import Crop
from faceoff.template import Template


def test_console_reporter_prints_settings_steps_and_files(monkeypatch, tmp_path):
    console = Console(record=True, width=200)
    monkeypatch.setattr(messages, "console", console)
    monkeypatch.chdir(tmp_path)
    options = Options(threads=3, reface=True, template=Template(tmp_path / "template"))
    outputs = Outputs.for_input(tmp_path / "scan.nii.gz", [], options)

    reporter = messages.ConsoleReporter()
    reporter.begin(tmp_path / "scan.nii.gz", options, outputs)
    reporter.step("deface mask")
    reporter.cropped(Crop(axis=2, first=79, last=256, size=256))
    reporter.end()

    text = console.export_text()
    assert "ANTs: antsx/ants:2.6.5 in Docker (3 threads)" in text
    assert "Reface: yes" in text and "SyN: no" in text
    assert "next hundred years" in text  # the --reface quote
    assert "Completed: deface mask in" in text
    assert "Cropped to native slices 79-255 of 256 along voxel axis 2" in text
    for name in ("scan_defaced.nii.gz", "scan_tal_refaced.nii.gz", "scan_txn-to-tal_fsl.mat"):
        assert f"✓ {name}" in text
