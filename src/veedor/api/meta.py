from importlib.metadata import PackageNotFoundError, version

try:
    VERSION = version("veedor")
except PackageNotFoundError:  # running from a source tree without an installed distribution
    VERSION = "0.0.0"
