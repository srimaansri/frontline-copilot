# Databricks notebook source
# MAGIC %md
# MAGIC # Probe: what can a serverless notebook install and download?
# MAGIC
# MAGIC Free Edition limits outbound internet access to an unpublished list of trusted
# MAGIC domains. The pipelines need Presidio, a spaCy model (hosted on GitHub) and the
# MAGIC `tiktoken` encoding file (hosted on an Azure blob). This notebook tries each one and
# MAGIC returns the results as JSON, so the answer is recorded and not guessed.
# MAGIC
# MAGIC It changes nothing in the workspace.

# COMMAND ----------

import importlib.metadata
import json
import subprocess
import sys
import urllib.request

results: dict[str, object] = {"python": sys.version.split()[0]}


def installed(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


results["preinstalled"] = {
    name: installed(name)
    for name in (
        "pydantic",
        "pydantic-settings",
        "numpy",
        "pandas",
        "mlflow",
        "databricks-sdk",
        "spacy",
        "presidio-analyzer",
        "tiktoken",
        "pyyaml",
    )
}

# COMMAND ----------


def reachable(url: str) -> str:
    try:
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "probe"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return f"ok {response.status}"
    except Exception as error:
        return f"blocked: {type(error).__name__}: {str(error)[:120]}"


results["reachable"] = {
    "pypi.org": reachable("https://pypi.org/simple/pip/"),
    "github.com": reachable("https://github.com/explosion/spacy-models/releases"),
    "objects.githubusercontent.com (release downloads)": reachable(
        "https://github.com/explosion/spacy-models/releases/download/"
        "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    ),
    "openaipublic.blob.core.windows.net (tiktoken)": reachable(
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
    ),
}

# COMMAND ----------


def pip_install(*requirements: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", *requirements],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return "ok"
    return "failed: " + completed.stderr.strip()[-400:]


MODEL_WHEEL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl"
)
results["pip"] = {
    "presidio-analyzer==2.2.366 spacy==3.8.18": pip_install(
        "presidio-analyzer==2.2.366", "spacy==3.8.18"
    ),
    "tiktoken": pip_install("tiktoken"),
    "en_core_web_md wheel from GitHub": pip_install(MODEL_WHEEL),
}
results["after_install"] = {
    name: installed(name)
    for name in ("pydantic", "numpy", "spacy", "presidio-analyzer", "tiktoken", "en_core_web_md")
}

# COMMAND ----------

try:
    import tiktoken

    results["tiktoken_encoding"] = (
        f"ok, {len(tiktoken.get_encoding('cl100k_base').encode('hello world'))} tokens"
    )
except Exception as error:
    results["tiktoken_encoding"] = f"failed: {type(error).__name__}: {str(error)[:200]}"

try:
    import spacy

    nlp = spacy.load("en_core_web_md")
    results["spacy_model_load"] = f"ok, pipeline {nlp.pipe_names}"
except Exception as error:
    results["spacy_model_load"] = f"failed: {type(error).__name__}: {str(error)[:200]}"

# COMMAND ----------

dbutils.notebook.exit(json.dumps(results))
