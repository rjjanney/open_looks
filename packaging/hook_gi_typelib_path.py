import os

# PyGObject searches GI_TYPELIB_PATH for .typelib files at runtime.
# The path baked into the bundled gi matches the build machine (Ubuntu:
# /usr/lib/x86_64-linux-gnu/girepository-1.0), so on Fedora/RHEL the
# WebKit2 typelib isn't found. Prepend all common distro paths so the
# bundle works cross-distro without requiring GI_TYPELIB_PATH from the
# user's environment.
_TYPELIB_DIRS = [
    "/usr/lib64/girepository-1.0",                      # Fedora / RHEL / openSUSE
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",       # Ubuntu / Debian x86-64
    "/usr/lib/aarch64-linux-gnu/girepository-1.0",      # Ubuntu / Debian arm64
    "/usr/lib/girepository-1.0",                        # generic fallback
]

existing = os.environ.get("GI_TYPELIB_PATH", "")
extra = ":".join(d for d in _TYPELIB_DIRS if os.path.isdir(d))
os.environ["GI_TYPELIB_PATH"] = ":".join(filter(None, [extra, existing]))
