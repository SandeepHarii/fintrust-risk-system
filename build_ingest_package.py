
from pathlib import Path
from shutil import copy2, copytree, rmtree
from zipfile import ZIP_DEFLATED, ZipFile
import hashlib

ROOT = Path.cwd()

BUILD_SOURCE = ROOT / "ingest-build"
SOURCE_PACKAGE = ROOT / "fintrust"
STAGING = ROOT / "ingest-package"
OUTPUT_ZIP = ROOT / "fintrust-prod-ingest-candidate.zip"

DEPENDENCY_DIRS = [
    "boto3",
    "botocore",
    "dateutil",
    "jmespath",
    "s3transfer",
    "urllib3",
    "pyarrow",
]

METADATA_DIRS = [
    "boto3-1.43.111.dist-info",
    "botocore-1.43.111.dist-info",
    "jmespath-1.1.0.dist-info",
    "python_dateutil-2.9.0.post0.dist-info",
    "s3transfer-0.19.2.dist-info",
    "urllib3-2.8.0.dist-info",
    "pyarrow-20.0.0.dist-info",
]

IGNORED_NAMES = {
    "__pycache__",
    "tests",
    "test",
}

MAX_UNCOMPRESSED_SIZE = 250 * 1024 * 1024


def copy_package(source: Path, destination: Path) -> None:
    copytree(
        source,
        destination,
        ignore=lambda directory, names: [
            name
            for name in names
            if name in IGNORED_NAMES
            or name.endswith((".pyc", ".pyo"))
            or name == ".env"
        ],
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


if not SOURCE_PACKAGE.is_dir():
    raise SystemExit("ERROR: fintrust source directory not found.")

if not BUILD_SOURCE.is_dir():
    raise SystemExit("ERROR: ingest-build directory not found.")

# Verify all dependency directories.
for name in DEPENDENCY_DIRS + METADATA_DIRS:
    if not (BUILD_SOURCE / name).is_dir():
        raise SystemExit(
            f"ERROR: Required dependency missing: {name}"
        )

if not (BUILD_SOURCE / "six.py").is_file():
    raise SystemExit("ERROR: six.py missing.")

# Verify the Python 3.12 Linux x86_64 PyArrow extension.
pyarrow_native = (
    BUILD_SOURCE
    / "pyarrow"
    / "lib.cpython-312-x86_64-linux-gnu.so"
)

if not pyarrow_native.is_file():
    raise SystemExit(
        "ERROR: Python 3.12 Linux x86_64 PyArrow extension missing."
    )

# Verify additional native PyArrow libraries.
required_native = [
    "_compute.cpython-312-x86_64-linux-gnu.so",
    "_dataset.cpython-312-x86_64-linux-gnu.so",
]

for name in required_native:
    if not (BUILD_SOURCE / "pyarrow" / name).is_file():
        raise SystemExit(
            f"ERROR: Required PyArrow extension missing: {name}"
        )

# Build in a separate staging directory.
if STAGING.exists():
    rmtree(STAGING)

STAGING.mkdir()

# Copy current application source.
copy_package(
    SOURCE_PACKAGE,
    STAGING / "fintrust",
)

# Copy compatible Linux dependencies.
for name in DEPENDENCY_DIRS:
    copy_package(
        BUILD_SOURCE / name,
        STAGING / name,
    )

# Copy package metadata.
for name in METADATA_DIRS:
    copy_package(
        BUILD_SOURCE / name,
        STAGING / name,
    )

copy2(
    BUILD_SOURCE / "six.py",
    STAGING / "six.py",
)

# Create a fresh candidate ZIP.
if OUTPUT_ZIP.exists():
    OUTPUT_ZIP.unlink()

with ZipFile(
    OUTPUT_ZIP,
    "w",
    ZIP_DEFLATED,
    compresslevel=6,
) as archive:
    for path in STAGING.rglob("*"):
        if path.is_file():
            archive.write(
                path,
                path.relative_to(STAGING).as_posix(),
            )

# Verify package contents.
with ZipFile(OUTPUT_ZIP, "r") as archive:
    names = set(archive.namelist())

    bad_file = archive.testzip()

    if bad_file:
        raise SystemExit(
            f"ERROR: ZIP integrity failed: {bad_file}"
        )

    required_files = [
        "fintrust/__init__.py",
        "fintrust/ingest.py",
        "fintrust/validators.py",
        "pyarrow/__init__.py",
        "pyarrow/lib.cpython-312-x86_64-linux-gnu.so",
        "pyarrow/_compute.cpython-312-x86_64-linux-gnu.so",
        "pyarrow/_dataset.cpython-312-x86_64-linux-gnu.so",
        "boto3/__init__.py",
        "botocore/__init__.py",
        "six.py",
    ]

    for name in required_files:
        if name not in names:
            raise SystemExit(
                f"ERROR: Required file missing: {name}"
            )

    # Ensure no tests, caches or secrets were included.
    unwanted = [
        name
        for name in names
        if "__pycache__/" in name
        or name.endswith((".pyc", ".pyo"))
        or name.startswith("tests/")
        or name == ".env"
    ]

    if unwanted:
        raise SystemExit(
            "ERROR: Unwanted files found:\n"
            + "\n".join(unwanted[:20])
        )

    # Verify exact source-file contents.
    for filename in ["ingest.py", "validators.py"]:
        source_bytes = (
            SOURCE_PACKAGE / filename
        ).read_bytes()

        packaged_bytes = archive.read(
            f"fintrust/{filename}"
        )

        if source_bytes != packaged_bytes:
            raise SystemExit(
                f"ERROR: Packaged {filename} differs from source."
            )

    uncompressed_size = sum(
        item.file_size
        for item in archive.infolist()
    )

    if uncompressed_size > MAX_UNCOMPRESSED_SIZE:
        raise SystemExit(
            "ERROR: Package exceeds Lambda's 250 MB "
            "uncompressed ZIP limit."
        )

    native_extensions = [
        name
        for name in names
        if name.startswith("pyarrow/")
        and name.endswith(".so")
    ]

# Final build report.
print("\nBUILD SUCCESSFUL")
print(f"Candidate ZIP: {OUTPUT_ZIP.name}")
print(
    f"Compressed size: "
    f"{OUTPUT_ZIP.stat().st_size / (1024 * 1024):.2f} MB"
)
print(
    f"Uncompressed size: "
    f"{uncompressed_size / (1024 * 1024):.2f} MB"
)
print(f"Total files: {len(names)}")
print(f"PyArrow native extensions: {len(native_extensions)}")
print("Current ingest.py: verified")
print("Current validators.py: verified")
print("Python 3.12 x86_64 compatibility: verified")
print("ZIP integrity: passed")
print("Unwanted files: none")
print(f"ingest.py SHA256: {sha256_file(SOURCE_PACKAGE / 'ingest.py')}")
print(
    f"validators.py SHA256: "
    f"{sha256_file(SOURCE_PACKAGE / 'validators.py')}"
)