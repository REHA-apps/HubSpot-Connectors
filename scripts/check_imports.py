import ast
import os
import pkgutil
import sys


def get_stdlib_modules():
    return set(sys.builtin_module_names) | {
        m.name
        for m in pkgutil.iter_modules()
        if m.module_finder and "lib" in str(m.module_finder).lower()
    }


def get_imports(directory):
    imports = set()
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=path)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    imports.add(alias.name.split(".")[0])
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    imports.add(node.module.split(".")[0])
                except Exception as e:
                    print(f"Error parsing {path}: {e}")
    return imports


if __name__ == "__main__":
    app_dir = r"c:\Users\elaiy\Desktop\Integrations\crm-connectors\app"
    all_imports = get_imports(app_dir)
    stdlib = get_stdlib_modules()

    # dependencies from pyproject.toml (mapping import names)
    # package name -> import name
    # slack-sdk -> slack_sdk
    # python-dotenv -> dotenv
    # python-multipart -> multipart
    # pydantic-settings -> pydantic_settings

    dependencies = {
        "fastapi",
        "httpx",
        "pydantic",
        "pydantic_settings",
        "dotenv",
        "supabase",
        "uvicorn",
        "slack_sdk",
        "stripe",
        "aiohttp",
        "multipart",
        "starlette",  # FastAPI transitive dep, sometimes imported directly
    }

    internal = {"app"}

    external_found = []
    for imp in sorted(all_imports):
        if imp in stdlib:
            continue
        if imp in dependencies:
            continue
        if imp in internal:
            continue
        external_found.append(imp)

    print(f"Potential missing or extra dependencies: {external_found}")
