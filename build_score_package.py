
from pathlib import Path
from shutil import copy2, copytree, rmtree
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path.cwd()

BUILD_SOURCE = ROOT / "score-build"
SOURCE_PACKAGE = ROOT / "backend" / "fintrust"
STAGING = ROOT / "score-package"
OUTPUT_ZIP = ROOT / "fintrust-prod-score-candidate.zip"

DEPENDENCY_DIRS = [
    "boto3",
    "botocore",
    "dateutil",
    "jmespath",
    "s3transfer",
    "urllib3",
    "psycopg2",
    "psycopg2_binary.libs",
]

METADATA_DIRS = [
    "boto3-1.43.111.dist-info",
    "botocore-1.43.111.dist-info",
    "jmespath-1.1.0.dist-info",
    "psycopg2_binary-2.9.13.dist-info",
    "python_dateutil-2.9.0.post0.dist-info",
    "s3transfer-0.19.2.dist-info",
    "six-1.17.0.dist-info",
    "urllib3-2.8.0.dist-info",
]

IGNORE = {"__pycache__", "*.pyc", "*.pyo", "tests", "test"}


def copy_package(source: Path, destination: Path) -> None:
    copytree(
        source,
        destination,
        ignore=lambda directory, names: [
            name for name in names
            if name in IGNORE
            or name.endswith((".pyc", ".pyo"))
        ],
    )


if not SOURCE_PACKAGE.is_dir():
    raise SystemExit("ERROR: backend/fintrust source directory not found.")

if not BUILD_SOURCE.is_dir():
    raise SystemExit("ERROR: score-build directory not found.")

for name in DEPENDENCY_DIRS + METADATA_DIRS:
    if not (BUILD_SOURCE / name).is_dir():
        raise SystemExit(f"ERROR: Required build dependency missing: {name}")

native_extensions = list(
    (BUILD_SOURCE / "psycopg2").glob("_psycopg*.so")
)

if not native_extensions:
    raise SystemExit("ERROR: Linux psycopg2 native extension not found.")

if STAGING.exists():
    rmtree(STAGING)

STAGING.mkdir()

copy_package(SOURCE_PACKAGE, STAGING / "fintrust")

for name in DEPENDENCY_DIRS:
    copy_package(BUILD_SOURCE / name, STAGING / name)

for name in METADATA_DIRS:
    copy_package(BUILD_SOURCE / name, STAGING / name)

copy2(BUILD_SOURCE / "six.py", STAGING / "six.py")

if OUTPUT_ZIP.exists():
    OUTPUT_ZIP.unlink()

with ZipFile(OUTPUT_ZIP, "w", ZIP_DEFLATED, compresslevel=6) as archive:
    for path in STAGING.rglob("*"):
        if path.is_file():
            archive.write(path, path.relative_to(STAGING).as_posix())

with ZipFile(OUTPUT_ZIP, "r") as archive:
    names = set(archive.namelist())

    bad_file = archive.testzip()
    if bad_file:
        raise SystemExit(f"ERROR: ZIP integrity check failed: {bad_file}")

    required_files = [
        "fintrust/score.py",
        "fintrust/dynamo.py",
        "fintrust/db.py",
        "fintrust/config.py",
        "fintrust/__init__.py",
        "psycopg2/__init__.py",
        "six.py",
    ]

    for name in required_files:
        if name not in names:
            raise SystemExit(f"ERROR: Required file missing from ZIP: {name}")

    native_names = [
        name for name in names
        if name.startswith("psycopg2/_psycopg")
        and name.endswith(".so")
    ]

    if not native_names:
        raise SystemExit("ERROR: psycopg2 native extension missing from ZIP.")

    unwanted = [
        name for name in names
        if "__pycache__/" in name
        or name.endswith((".pyc", ".pyo"))
        or name.startswith("tests/")
        or name == ".env"
    ]

    if unwanted:
        raise SystemExit(
            "ERROR: Unwanted files found in ZIP:\n"
            + "\n".join(unwanted[:20])
        )

    for filename in ["score.py", "dynamo.py"]:
        source_bytes = (SOURCE_PACKAGE / filename).read_bytes()
        packaged_bytes = archive.read(f"fintrust/{filename}")

        if source_bytes != packaged_bytes:
            raise SystemExit(
                f"ERROR: Packaged fintrust/{filename} does not match source."
            )

print("BUILD SUCCESSFUL")
print(f"Candidate ZIP: {OUTPUT_ZIP.name}")
print(f"ZIP size: {OUTPUT_ZIP.stat().st_size / (1024 * 1024):.2f} MB")
print(f"Total files: {len(names)}")
print(f"Native PostgreSQL extension: {native_names[0]}")
print("Current score.py: verified")
print("Current dynamo.py: verified")
print("ZIP integrity: passed")
print("Unwanted files: none")
