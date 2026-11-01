"""Build a handoff ZIP from an explicit allowlist; no personal captures."""
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
FILES = ['README.md', 'predict.py', 'package.py', 'requirements.txt', 'model.json',
         'manifest.json', 'validation.json', 'labels.csv', 'ghi_chu.txt',
         'examples/sensor_sample_4000.csv', 'examples/sensor_sample_4000.metadata.json',
         'example_results/predictions.csv', 'example_results/alarms.csv',
         'example_results/summary.json', 'example_results/plot.png']


def build():
    destination = HERE / 'dist/fall_detection_pc.zip'
    for name in FILES:
        if not (HERE / name).is_file():
            raise FileNotFoundError(name)
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(HERE / name, 'fall_detection_pc/' + name)
    return destination


if __name__ == '__main__':
    print(build())
