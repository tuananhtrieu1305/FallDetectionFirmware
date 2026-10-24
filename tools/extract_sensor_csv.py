import argparse
import csv
import io
import json
import math
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path

HEADER = "timestamp_us,ax,ay,az,gx,gy,gz,pressure_pa," "seq,pressure_timestamp_us,flags"

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def payload_after(line, marker):
    pos = line.find(marker)
    return line[pos:] if pos >= 0 else None


def extract(log_text):
    lines = ANSI.sub("", log_text).replace("\r", "").split("\n")

    active = False

    metadata = None
    header_found = False

    data = []

    expected_count = None
    trigger_seq = None
    end = None

    for full in lines:
        line = full.strip()

        if "FDCSV_BEGIN," in line:
            start = payload_after(line, "FDCSV_BEGIN,")

            parts = start.split(",")

            if len(parts) != 4 or parts[1] != "1":
                raise ValueError("Invalid FDCSV_BEGIN protocol")

            active = True
            metadata = None
            header_found = False
            data = []
            end = None

            expected_count = int(parts[2])
            trigger_seq = int(parts[3])

            continue

        if not active:
            continue

        if "FDCSV_ABORT," in line:
            raise ValueError("Device reported FDCSV_ABORT")

        if "FDMETA," in line:
            raw = payload_after(line, "FDMETA,")

            metadata = json.loads(raw[len("FDMETA,") :])

            continue

        if "FDCSV_END," in line:
            raw = payload_after(line, "FDCSV_END,")

            parts = raw.split(",")

            if len(parts) != 3:
                raise ValueError("Malformed FDCSV_END")

            end = (int(parts[1]), int(parts[2], 16))

            break

        if not header_found:
            if HEADER in line:
                header_found = True

            continue

        if re.match(r"^[0-9]+,", line):
            data.append(line)

    if not active or end is None or not header_found or metadata is None:
        raise ValueError("Incomplete transfer: missing BEGIN/META/header/END")

    if expected_count != 4000 or trigger_seq != 4500:
        raise ValueError("Unexpected synthetic event size/trigger")

    if end[0] != expected_count or len(data) != expected_count:
        raise ValueError(
            "Wrong row count: "
            f"received={len(data)}, "
            f"expected={expected_count}, "
            f"end={end[0]}"
        )

    raw_csv = HEADER + "\n" + "\n".join(data) + "\n"

    crc = zlib.crc32(raw_csv.encode("ascii")) & 0xFFFFFFFF

    if crc != end[1]:
        raise ValueError(f"CRC mismatch: " f"PC={crc:08X} " f"ESP32={end[1]:08X}")

    rows = list(csv.DictReader(io.StringIO(raw_csv)))

    if len(rows) != expected_count:
        raise ValueError("CSV parser rejected row count")

    last_ts = -1
    marker_count = 0
    valid_pressure_count = 0

    for i, row in enumerate(rows):

        if None in row or len(row) != 11:
            raise ValueError(f"Malformed CSV row {i}")

        seq = int(row["seq"])
        ts = int(row["timestamp_us"])
        flags = int(row["flags"])

        if seq != trigger_seq - 3000 + i or ts <= last_ts:
            raise ValueError(f"Invalid sequence/timestamp at row {i}")

        last_ts = ts

        for key in ("ax", "ay", "az", "gx", "gy", "gz"):
            if not math.isfinite(float(row[key])):
                raise ValueError(f"Nonfinite {key} at row {i}")

        if flags & 1:
            valid_pressure_count += 1

            if not row["pressure_pa"] or not row["pressure_timestamp_us"]:
                raise ValueError(f"Missing valid pressure at row {i}")

            age = ts - int(row["pressure_timestamp_us"])

            if age < 0 or age > 200000:
                raise ValueError(f"Pressure age violation at row {i}")

            pressure = float(row["pressure_pa"])

            if not 30000 < pressure < 120000:
                raise ValueError(f"Pressure value violation at row {i}")

        elif row["pressure_pa"] or row["pressure_timestamp_us"]:
            raise ValueError(f"Invalid pressure should be blank at row {i}")

        if flags & 2:
            marker_count += 1

            if i != 3000:
                raise ValueError("Event marker not at first POST sample")

        if flags & ~3:
            raise ValueError(f"Unknown flags at row {i}")

    if marker_count != 1:
        raise ValueError(f"Expected one event marker, found {marker_count}")

    if metadata.get("schema_version") != "sensor-v1":
        raise ValueError("Unexpected schema version")

    if metadata.get("trigger_type") != "synthetic_test":
        raise ValueError("Cannot label synthetic capture as real fall")

    if metadata.get("trigger_seq") != trigger_seq:
        raise ValueError("Trigger mismatch in metadata")

    if metadata.get("pre_samples") != 3000 or metadata.get("post_samples") != 1000:
        raise ValueError("PRE/POST metadata mismatch")

    metadata["export_validation"] = {
        "status": "PASS",
        "csv_rows": len(rows),
        "csv_crc32": f"{crc:08X}",
        "seq_first": int(rows[0]["seq"]),
        "seq_last": int(rows[-1]["seq"]),
        "timestamp_first_us": int(rows[0]["timestamp_us"]),
        "timestamp_last_us": int(rows[-1]["timestamp_us"]),
        "pressure_valid_rows": valid_pressure_count,
    }

    return raw_csv, metadata


def main():

    parser = argparse.ArgumentParser(
        description=("Extract sensor-v1 CSV and metadata " "from ESP-IDF Monitor logs.")
    )

    parser.add_argument("log", type=Path)

    parser.add_argument("--out-dir", type=Path, default=Path("captures"))

    args = parser.parse_args()

    try:
        raw_csv, meta = extract(args.log.read_text(encoding="utf-8", errors="replace"))

        args.out_dir.mkdir(parents=True, exist_ok=True)

        tag = datetime.now().strftime("%Y%m%d_%H%M%S")

        csv_path = args.out_dir / (f"fall_event_synthetic_{tag}.csv")

        json_path = args.out_dir / (f"fall_event_synthetic_{tag}.metadata.json")

        csv_path.write_text(raw_csv, encoding="utf-8", newline="\n")

        json_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        print(
            "PASS: "
            f"{meta['export_validation']['csv_rows']} rows, "
            "CRC32="
            f"{meta['export_validation']['csv_crc32']}"
        )

        print(f"CSV: {csv_path}")
        print(f"METADATA: {json_path}")

    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:

        print(f"FAIL: {exc}", file=sys.stderr)

        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
